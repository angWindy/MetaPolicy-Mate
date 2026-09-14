"""Regression test for the ingestion failure path.

The exact bug these tests guard against: ``IngestionPipeline.process_version``
used to call ``Repository.update_ingestion_job`` with a ``completed_at=...``
kwarg that the receiver signature did not accept. The resulting ``TypeError``
was swallowed by ``IngestionWorker._safe_process``, leaving ``ingestion_jobs``
in a non-terminal state with no ``error_message`` recorded. Versions stayed
stuck at ``received``/``parsing`` forever and the operator had no way to
diagnose them.

These tests assert that, after a parser exception:
  * the version row's ``processing_status`` is ``failed``,
  * the matching ``ingestion_job`` row's status is ``failed`` and its
    ``error_message`` matches the underlying exception,
  * the worker's ``_safe_process`` returns normally (never re-raises),
  * no stale ``started_at``/``completed_at`` kwargs leak through.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.worker import IngestionWorker
from src.rag.config import RAGSettings


def _build_pipeline(*, parser_should_raise: bool):
    import tempfile

    settings = RAGSettings()
    repository = MagicMock()

    # _read_quarantine_and_parse reads the file BEFORE calling the parser,
    # so the source file must actually exist on disk for the test to drive
    # the failure through the parser layer.
    tmp = tempfile.NamedTemporaryFile(prefix="p234-test-", suffix=".pdf", delete=False)
    tmp.write(b"%PDF-1.4 fake content for ingestion failure test\n")
    tmp.close()

    version = SimpleNamespace(
        id="version-abc",
        document_id="doc-xyz",
        processing_status="queued",
        source_path=tmp.name,
        source_filename="dummy.pdf",
    )
    document = SimpleNamespace(
        id="doc-xyz",
        access_level="internal",
        allowed_departments=["ALL"],
    )

    job = SimpleNamespace(id="job-123")

    repository.get_latest_job_for_version.return_value = job
    # pipeline._load_version calls repository.get_version(version_id) and
    # reads .processing_status / .source_path / .document_id / .id off it.
    # A SimpleNamespace is required (not MagicMock) so those attrs stay
    # real strings — MagicMock attrs return further Mocks which then break
    # the ProcessingStatus(version.processing_status) enum coercion below.
    repository.get_version.return_value = version

    def update_version_source(version_id, **kwargs):
        version.processing_status = kwargs.get("processing_status", version.processing_status)
        return None

    def update_ingestion_job(job_id, **kwargs):
        # This is the smoke detector: reject legacy bogus kwargs that
        # used to crash this call and silently strand rows.
        forbidden = {"started_at", "completed_at"}
        leaked = forbidden.intersection(kwargs)
        assert not leaked, (
            f"update_ingestion_job received unexpected kwargs {leaked}; "
            f"the signature only accepts {set(kwargs).difference(leaked)}."
        )
        for k, v in kwargs.items():
            setattr(job, k, v)
        return job

    repository.update_version_source.side_effect = update_version_source
    repository.update_ingestion_job.side_effect = update_ingestion_job

    # The parser raises on demand so the rest of process_version fails fast.
    # Note: parser.parse is sync (called from a non-async helper method).
    def parse_file(*_args, **_kwargs):
        if parser_should_raise:
            raise RuntimeError("startxref not found")
        return ([], [])

    settings_dict = settings.model_dump() if hasattr(settings, "model_dump") else settings.dict()
    pipeline = IngestionPipeline(
        settings=settings_dict,
        repository=repository,
        parser=MagicMock(parse=parse_file),
        storage=MagicMock(),
        embeddings=MagicMock(),
        vector_store=MagicMock(),
    )
    return pipeline, repository, version, job


def test_process_version_records_failure_on_parser_exception():
    pipeline, repository, version, job = _build_pipeline(parser_should_raise=True)

    result = asyncio.run(pipeline.process_version("version-abc"))

    assert version.processing_status == "failed"
    assert result.processing_status.value == "failed"
    assert job.status == "failed"
    assert "startxref not found" in job.error_message

    update_calls = repository.update_ingestion_job.call_args_list
    assert update_calls, "update_ingestion_job was never called"
    kwargs = update_calls[-1].kwargs
    assert "started_at" not in kwargs
    assert "completed_at" not in kwargs


def test_worker_safe_process_swallows_pipeline_exception():
    pipeline, repository, _version, _job = _build_pipeline(parser_should_raise=True)
    worker = IngestionWorker(pipeline, repository)

    # Should not raise — the worker contract is "never raises; failures
    # are recorded on the row".
    asyncio.run(worker._safe_process("version-abc"))

    # And the pipeline still recorded the failure on the row.
    repository.update_ingestion_job.assert_called()


def test_worker_safe_process_keeps_no_stuck_job_status():
    """The smoking-gun assertion: after _safe_process finishes, the job
    row is in a terminal state with a matching error_message. Before the
    fix, the bogus completed_at= kwarg raised inside the inner try/except
    and the job row was left at status='parsing' with no error_message.
    """
    pipeline, repository, _version, job = _build_pipeline(parser_should_raise=True)
    worker = IngestionWorker(pipeline, repository)

    asyncio.run(worker._safe_process("version-abc"))

    assert job.status in {"failed", "indexed"}, (
        f"ingestion_job is stuck in non-terminal state: status={job.status!r}"
    )
    assert job.error_message, "ingestion_job has no error_message after failure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

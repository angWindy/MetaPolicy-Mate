"""Single-process background worker that drains the ingestion queue.

Uses ``asyncio.create_task`` instead of an external broker so the MVP can
ship without Redis/Celery. The trade-off is documented in
``docs/architecture/ingestion-queue.md``: tasks do not survive an
application restart, so a version left in ``QUEUED`` after a crash needs
an operator-triggered resubmit (TODO for a future iteration).

The worker keeps a ``dict[version_id, asyncio.Task]`` so the admin
``/admin/documents/{version_id}/status`` endpoint can introspect a
running task if needed. Tasks are popped from the dict when they finish,
so memory stays bounded by the number of *in-flight* versions (usually 1
in normal operation).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.repository import Repository
    from src.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Fire-and-forget scheduler for :meth:`IngestionPipeline.process_version`."""

    def __init__(self, pipeline: IngestionPipeline, repository: Repository):
        self.pipeline = pipeline
        self.repository = repository
        self._tasks: dict[str, asyncio.Task] = {}
        self._closed = False

    def submit(self, version_id: str) -> asyncio.Task | None:
        """Schedule ``process_version`` in the background.

        Returns the underlying ``asyncio.Task`` so callers can await it in
        tests, but production code should treat the call as fire-and-forget.
        Returns ``None`` if the worker has been shut down.
        """
        if self._closed:
            logger.warning("ingest_submit_after_shutdown version_id=%s", version_id)
            return None

        loop = asyncio.get_running_loop()
        coro = self._safe_process(version_id)
        task = loop.create_task(coro, name=f"ingest-{version_id}")
        self._tasks[version_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(version_id, None))
        return task

    async def _safe_process(self, version_id: str) -> None:
        try:
            await self.pipeline.process_version(version_id)
        except asyncio.CancelledError:
            logger.info("ingest_cancelled version_id=%s", version_id)
            raise
        except Exception:  # noqa: BLE001 - already recorded on the row
            logger.exception("ingest_unhandled_exception version_id=%s", version_id)

    def is_running(self, version_id: str) -> bool:
        return version_id in self._tasks and not self._tasks[version_id].done()

    def running_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    async def shutdown(self) -> None:
        """Cancel every in-flight task. Await them so shutdown is clean."""
        self._closed = True
        tasks: list[Awaitable[None]] = []
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
                tasks.append(_drain(task))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def submit_async(self, version_id: str) -> Awaitable[None] | None:
        """Backwards-compatible helper kept so older call sites keep working.

        Existing code expects ``await worker.submit_async(version_id)``; the
        HTTP admin route now calls :meth:`submit` directly because the API
        handler returns before the task completes.
        """
        task = self.submit(version_id)
        if task is None:
            return None
        return _await_task(task)


async def _drain(task: asyncio.Task) -> None:
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        return


async def _await_task(task: asyncio.Task) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return
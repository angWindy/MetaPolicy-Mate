"""Governed checkpointing primitives for the retrieval workflow.

Checkpoints are deliberately treated as an audit/control plane, not as a cache
of retrieved documents.  The saver below removes document text, user context,
provider objects and other runtime values before they reach durable storage.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver


def query_digest(query: str | None) -> str:
    """Return a non-reversible query identifier for checkpoint metadata."""

    return hashlib.sha256((query or "").encode("utf-8")).hexdigest()


def _candidate_records(state: Mapping[str, Any]) -> tuple[list[str], dict[str, float]]:
    ids: list[str] = []
    scores: dict[str, float] = {}

    def add(candidate: Any) -> None:
        chunk_id = getattr(candidate, "chunk_id", None)
        if not chunk_id:
            return
        chunk_id = str(chunk_id)
        if chunk_id not in ids:
            ids.append(chunk_id)
        score = getattr(candidate, "rerank_score", None)
        if score is None:
            score = getattr(candidate, "fusion_score", None)
        if score is not None:
            scores[chunk_id] = float(score)

    for key in ("retrieval_result", "rerank_result"):
        result = state.get(key)
        for candidate in getattr(result, "candidates", []) or []:
            add(candidate)
    for candidate in state.get("final_contexts", []) or []:
        add(candidate)
    return ids, scores


def sanitize_checkpoint_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the bounded, non-content checkpoint contract.

    The returned mapping intentionally excludes ``query``, ``user``, settings,
    provider instances and all candidate content/metadata.  It is safe to
    inspect in tests and in an audit store.
    """

    ids, scores = _candidate_records(values)
    decision = values.get("evidence_decision")
    decision = getattr(decision, "value", decision)
    status = values.get("evidence_status")
    status = getattr(status, "value", status)
    original_query = values.get("original_query") or values.get("query")
    audit = values.get("human_audit", [])
    safe_audit = []
    for item in audit if isinstance(audit, list) else []:
        if not isinstance(item, Mapping):
            continue
        safe_audit.append(
            {
                "decision": str(item.get("decision", "")),
                "actor_id": str(item.get("actor_id", "")),
                "submitted_at": str(item.get("submitted_at", "")),
            }
        )
    guardrail_history = []
    for item in values.get("guardrail_history", []) if isinstance(values.get("guardrail_history", []), list) else []:
        if not isinstance(item, Mapping):
            continue
        guardrail_history.append(
            {
                "action": str(item.get("action", "")),
                "stage": str(item.get("stage", "")),
                "reason_codes": [str(code) for code in list(item.get("reason_codes", []))[:20]],
                "risk_score": float(item.get("risk_score", 0.0) or 0.0),
                "policy_version": str(item.get("policy_version", "")),
                "audit_id": str(item.get("audit_id", "")),
            }
        )
    result: dict[str, Any] = {
        "candidate_ids": ids,
        "candidate_scores": scores,
        "index_version": str(values.get("index_version") or ""),
        "query_hash": query_digest(str(original_query or "")),
        "evidence_decision": decision,
        "evidence_status": status,
        "attempts": int(values.get("attempts", 0) or 0),
        "max_attempts": int(values.get("max_attempts", 2) or 2),
        "human_audit": safe_audit,
        "human_decision": str(values.get("human_decision", "") or ""),
        "outcome": str(values.get("outcome", "") or ""),
        "escalation_required": bool(values.get("escalation_required", False)),
        "error_code": str(values.get("error_code", "") or ""),
        "guardrail_action": str(values.get("guardrail_action", "") or ""),
        "guardrail_stage": str(values.get("guardrail_stage", "") or ""),
        "guardrail_reason_codes": [str(code) for code in values.get("guardrail_reason_codes", [])[:20]],
        "guardrail_risk_score": float(values.get("guardrail_risk_score", 0.0) or 0.0),
        "guardrail_policy_version": str(values.get("guardrail_policy_version", "") or ""),
        "guardrail_audit_id": str(values.get("guardrail_audit_id", "") or ""),
        "guardrail_history": guardrail_history[-20:],
    }
    return result


def _safe_control_channels(values: Mapping[str, Any]) -> dict[str, Any]:
    """Retain graph routing markers; they contain no document/user content."""

    return {key: value for key, value in values.items() if key.startswith("branch:to:")}


def _safe_pending_writes(writes: Sequence[tuple[str, Any]]) -> list[tuple[str, Any]]:
    safe_channels = {
        "attempts",
        "max_attempts",
        "index_version",
        "query_hash",
        "evidence_status",
        "evidence_decision",
        "error_code",
        "escalation_required",
        "outcome",
        "human_decision",
        "human_audit",
        "retry_requested",
        "visited",
        "guardrail_action",
        "guardrail_stage",
        "guardrail_reason_codes",
        "guardrail_risk_score",
        "guardrail_policy_version",
        "guardrail_audit_id",
        "guardrail_history",
    }
    safe_writes = []
    for channel, value in writes:
        if not (
            channel in safe_channels
            or channel.startswith("branch:to:")
            or channel in {"__interrupt__", "__error__", "__error_task__"}
        ):
            continue
        if channel in {"evidence_status", "evidence_decision"}:
            value = getattr(value, "value", value)
        safe_writes.append((channel, value))
    return safe_writes


class GovernedInMemorySaver(InMemorySaver):
    """Development/test saver that strips content before storing checkpoints."""

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        safe_checkpoint = checkpoint.copy()
        summary = sanitize_checkpoint_values(checkpoint.get("channel_values", {}))
        safe_checkpoint["channel_values"] = {
            **_safe_control_channels(checkpoint.get("channel_values", {})),
            **summary,
        }
        safe_metadata = dict(metadata)
        safe_metadata["checkpoint_summary"] = summary
        return super().put(config, safe_checkpoint, safe_metadata, new_versions)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        entry = super().get_tuple(config)
        if entry is None:
            return None
        summary = entry.metadata.get("checkpoint_summary", {})
        checkpoint = entry.checkpoint.copy()
        checkpoint["channel_values"] = {
            **checkpoint.get("channel_values", {}),
            **summary,
        }
        return entry._replace(checkpoint=checkpoint)

    def list(self, config, *, filter=None, before=None, limit=None):
        for entry in super().list(config, filter=filter, before=before, limit=limit):
            summary = entry.metadata.get("checkpoint_summary", {})
            checkpoint = entry.checkpoint.copy()
            checkpoint["channel_values"] = {
                **checkpoint.get("channel_values", {}),
                **summary,
            }
            yield entry._replace(checkpoint=checkpoint)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        return super().put_writes(config, _safe_pending_writes(writes), task_id, task_path)

    def prune(self, thread_id: str, *, max_checkpoints: int, max_age_days: int = 30) -> int:
        """Delete old checkpoints while retaining a bounded recent history."""

        config = {"configurable": {"thread_id": thread_id}}
        entries = list(self.list(config))
        removed = 0
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        stale = []
        for index, entry in enumerate(entries):
            timestamp = entry.checkpoint.get("ts")
            try:
                created = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                created = datetime.now(UTC)
            if index >= max_checkpoints or created < cutoff:
                stale.append(entry)
        for entry in stale:
            checkpoint_id = entry.config["configurable"].get("checkpoint_id")
            namespace = entry.config["configurable"].get("checkpoint_ns", "")
            if not checkpoint_id:
                continue
            self.storage.get(thread_id, {}).get(namespace, {}).pop(checkpoint_id, None)
            self.writes.pop((thread_id, namespace, checkpoint_id), None)
            for key in list(self.blobs):
                if key[0] == thread_id and key[1] == namespace:
                    # A blob can be shared by a retained checkpoint.  Keeping it
                    # is harmless and avoids deleting a live channel version.
                    continue
            removed += 1
        return removed


class SanitizedCheckpointAdapter(BaseCheckpointSaver):
    """Adapter applying the same redaction to a production saver backend."""

    def __init__(self, backend: BaseCheckpointSaver) -> None:
        super().__init__(serde=backend.serde)
        self.backend = backend

    def put(self, config, checkpoint, metadata, new_versions):
        safe_checkpoint = checkpoint.copy()
        summary = sanitize_checkpoint_values(checkpoint.get("channel_values", {}))
        safe_checkpoint["channel_values"] = {
            **_safe_control_channels(checkpoint.get("channel_values", {})),
            **summary,
        }
        safe_metadata = dict(metadata)
        safe_metadata["checkpoint_summary"] = summary
        return self.backend.put(config, safe_checkpoint, safe_metadata, new_versions)

    async def aput(self, config, checkpoint, metadata, new_versions):
        safe_checkpoint = checkpoint.copy()
        summary = sanitize_checkpoint_values(checkpoint.get("channel_values", {}))
        safe_checkpoint["channel_values"] = {
            **_safe_control_channels(checkpoint.get("channel_values", {})),
            **summary,
        }
        safe_metadata = dict(metadata)
        safe_metadata["checkpoint_summary"] = summary
        if hasattr(self.backend, "aput"):
            return await self.backend.aput(config, safe_checkpoint, safe_metadata, new_versions)
        return self.put(config, safe_checkpoint, safe_metadata, new_versions)

    def get_tuple(self, config):
        entry = self.backend.get_tuple(config)
        if entry is None:
            return None
        summary = entry.metadata.get("checkpoint_summary", {})
        checkpoint = entry.checkpoint.copy()
        checkpoint["channel_values"] = {
            **checkpoint.get("channel_values", {}),
            **summary,
        }
        return entry._replace(checkpoint=checkpoint)

    async def aget_tuple(self, config):
        if hasattr(self.backend, "aget_tuple"):
            return await self.backend.aget_tuple(config)
        return self.get_tuple(config)

    def list(self, config, *, filter=None, before=None, limit=None):
        for entry in self.backend.list(config, filter=filter, before=before, limit=limit):
            summary = entry.metadata.get("checkpoint_summary", {})
            checkpoint = entry.checkpoint.copy()
            checkpoint["channel_values"] = {
                **checkpoint.get("channel_values", {}),
                **summary,
            }
            yield entry._replace(checkpoint=checkpoint)

    async def alist(self, config, *, filter=None, before=None, limit=None):
        if hasattr(self.backend, "alist"):
            async for item in self.backend.alist(config, filter=filter, before=before, limit=limit):
                yield item
        else:
            return

    def put_writes(self, config, writes, task_id, task_path=""):
        return self.backend.put_writes(config, _safe_pending_writes(writes), task_id, task_path)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        if hasattr(self.backend, "aput_writes"):
            return await self.backend.aput_writes(config, _safe_pending_writes(writes), task_id, task_path)
        return self.put_writes(config, writes, task_id, task_path)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.backend, name)


class AsyncPostgresCheckpointer:
    """Lazy production factory for ``langgraph-checkpoint-postgres``.

    PostgreSQL is intentionally optional for local development.  Calling this
    factory in production installs the official async saver and wraps it with
    the same checkpoint redaction contract.
    """

    @classmethod
    async def from_conn_string(cls, conn_string: str) -> SanitizedCheckpointAdapter:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:  # pragma: no cover - optional production dep
            raise RuntimeError("Install langgraph-checkpoint-postgres to enable production persistence.") from exc
        backend = AsyncPostgresSaver.from_conn_string(conn_string)
        if inspect.isawaitable(backend):
            backend = await backend
        if hasattr(backend, "setup"):
            setup = backend.setup()
            if inspect.isawaitable(setup):
                await setup
        return SanitizedCheckpointAdapter(backend)


class CheckpointRetentionPolicy:
    """Bounded retention policy for checkpoint history."""

    def __init__(self, *, max_checkpoints: int = 100, max_age_days: int = 30) -> None:
        if max_checkpoints < 1 or max_age_days < 1:
            raise ValueError("Retention limits must be positive.")
        self.max_checkpoints = max_checkpoints
        self.max_age_days = max_age_days

    def prune(self, saver: BaseCheckpointSaver, thread_id: str) -> int:
        if isinstance(saver, GovernedInMemorySaver):
            return saver.prune(
                thread_id,
                max_checkpoints=self.max_checkpoints,
                max_age_days=self.max_age_days,
            )
        return 0


__all__ = [
    "AsyncPostgresCheckpointer",
    "CheckpointRetentionPolicy",
    "GovernedInMemorySaver",
    "SanitizedCheckpointAdapter",
    "query_digest",
    "sanitize_checkpoint_values",
]

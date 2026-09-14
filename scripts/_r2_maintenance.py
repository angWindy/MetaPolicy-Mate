"""Sync (blocking) R2 helpers used by maintenance scripts.

The runtime path uses :class:`src.infrastructure.storage.r2_file_storage.R2FileStorage`
which only exposes ``upload`` / ``download`` / ``delete`` through the
``FileStorage`` Protocol. Maintenance scripts (migration, orphan
sweep) need extra verbs — ``head_object``, ``copy_object``,
``delete_objects`` (batch), ``list_objects_v2`` — so they live here
rather than on the runtime adapter.

Import this module only from CLI / migration scripts; never from the
request hot path.
"""

from __future__ import annotations

import logging
from typing import Iterable, Iterator

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


class R2Maintenance:
    """Thin wrapper around boto3 for the ops scripts."""

    def __init__(
        self,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> None:
        self._bucket_name = bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def head_object(
        self,
        object_key: str,
    ) -> dict[str, object] | None:
        """Return head_object result or ``None`` if 404.

        Used by the migration to check whether the canonical key
        already exists in the bucket (re-run idempotency) and by the
        sweep to confirm a key really is present before deleting.
        """
        try:
            return self._client.head_object(
                Bucket=self._bucket_name,
                Key=object_key,
            )
        except ClientError as exc:
            status_code = (
                exc.response.get("Error", {}).get("Code")
            )
            if status_code in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return None
            raise

    def list_objects(
        self,
        prefix: str = "",
        *,
        page_size: int = 1000,
    ) -> Iterator[dict[str, object]]:
        """Yield one entry per object under ``prefix`` (no recursion).

        Paginates internally; stops when the bucket is exhausted.
        Yields the dict form of each ``Contents`` entry so callers can
        pick the keys they need without touching the raw response.
        """
        paginator = self._client.get_paginator(
            "list_objects_v2"
        )
        for page in paginator.paginate(
            Bucket=self._bucket_name,
            Prefix=prefix,
            PaginationConfig={"PageSize": page_size},
        ):
            for entry in page.get("Contents", []):
                yield entry

    def list_all_keys(
        self,
        prefixes: Iterable[str] = (""),
    ) -> list[str]:
        """Return the deduplicated list of object keys across prefixes."""
        seen: set[str] = set()
        for prefix in prefixes:
            for entry in self.list_objects(prefix):
                key = entry.get("Key")
                if key:
                    seen.add(str(key))
        return sorted(seen)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def copy_object(
        self,
        source_key: str,
        dest_key: str,
    ) -> None:
        """Server-side copy (no download)."""
        self._client.copy_object(
            Bucket=self._bucket_name,
            Key=dest_key,
            CopySource={
                "Bucket": self._bucket_name,
                "Key": source_key,
            },
        )
        logger.info(
            "copied %s -> %s", source_key, dest_key
        )

    def delete_object(
        self,
        object_key: str,
    ) -> None:
        self._client.delete_object(
            Bucket=self._bucket_name,
            Key=object_key,
        )
        logger.info("deleted %s", object_key)

    def delete_objects(
        self,
        object_keys: Iterable[str],
    ) -> list[str]:
        """Batch delete (boto3 caps batches at 1000 keys).

        Returns the list of keys that boto3 reported as errors so the
        caller can decide whether to retry.
        """
        keys = list(object_keys)
        errors: list[str] = []
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            resp = self._client.delete_objects(
                Bucket=self._bucket_name,
                Delete={
                    "Objects": [
                        {"Key": k} for k in chunk
                    ],
                    "Quiet": True,
                },
            )
            for err in resp.get("Errors", []):
                errors.append(str(err.get("Key")))
        if errors:
            logger.warning(
                "delete_objects reported %d errors: %s",
                len(errors),
                errors[:10],
            )
        return errors
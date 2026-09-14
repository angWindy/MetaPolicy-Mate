from typing import Protocol


class FileStorage(
    Protocol
):
    async def upload(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        ...

    async def download(
        self,
        object_key: str,
    ) -> bytes:
        ...

    async def delete(
        self,
        object_key: str,
    ) -> None:
        ...

    async def delete_objects(
        self,
        object_keys: list[str],
    ) -> list[str]:
        """Bulk delete. Returns the list of keys that failed.

        Used by the cascade-delete handler when a document has more
        than one version — saves N round-trips against R2 by issuing
        a single ``DeleteObjects`` call (boto3 caps each call at 1000
        keys, but the implementations below handle larger lists by
        chunking internally).
        """
        ...

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
    ) -> None:
        """Server-side copy from source_key to dest_key within the same
        bucket. No download/uploads of bytes through the application.

        Used by the access-scope update handler to mirror an R2 object
        when a document moves between tenant segments
        (``public/documents/...`` → ``hust/documents/...``).
        """
        ...

    async def head_object(
        self,
        object_key: str,
    ) -> dict[str, object] | None:
        """Return object metadata or ``None`` if 404.

        Used for pre-flight checks before initiating a copy or move.
        """
        ...
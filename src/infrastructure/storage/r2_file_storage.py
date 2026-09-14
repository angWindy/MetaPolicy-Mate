import asyncio

import boto3

from src.application.common.interfaces.file_storage import (
    FileStorage,
)


class R2FileStorage(
    FileStorage
):
    def __init__(
        self,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> None:
        self._bucket_name = (
            bucket_name
        )

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=(
                access_key_id
            ),
            aws_secret_access_key=(
                secret_access_key
            ),
            region_name="auto",
        )

    async def upload(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket_name,
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )

    async def download(
        self,
        object_key: str,
    ) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket_name,
            Key=object_key,
        )

        body = response["Body"]

        return await asyncio.to_thread(
            body.read
        )

    async def delete(
        self,
        object_key: str,
    ) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket_name,
            Key=object_key,
        )

    async def delete_objects(
        self,
        object_keys: list[str],
    ) -> list[str]:
        """Bulk-delete using ``DeleteObjects`` (max 1000 per call).

        Returns the list of keys that boto3 reported as errors so
        callers can surface them as partial-failure warnings on the
        API response. Chunking at 1000 keys mirrors boto3's hard cap.
        """
        if not object_keys:
            return []

        errors: list[str] = []
        for chunk_start in range(
            0, len(object_keys), 1000
        ):
            chunk = object_keys[
                chunk_start : chunk_start + 1000
            ]
            response = await asyncio.to_thread(
                self._client.delete_objects,
                Bucket=self._bucket_name,
                Delete={
                    "Objects": [
                        {"Key": k} for k in chunk
                    ],
                    "Quiet": True,
                },
            )
            for err in response.get(
                "Errors", []
            ):
                errors.append(str(err.get("Key")))
        return errors

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
    ) -> None:
        """Server-side copy within the same bucket (no local download)."""
        await asyncio.to_thread(
            self._client.copy_object,
            Bucket=self._bucket_name,
            Key=dest_key,
            CopySource={
                "Bucket": self._bucket_name,
                "Key": source_key,
            },
        )

    async def head_object(
        self,
        object_key: str,
    ) -> dict[str, object] | None:
        """Return head metadata or ``None`` if the key does not exist."""
        from botocore.exceptions import ClientError

        try:
            return await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket_name,
                Key=object_key,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
import asyncio

from config import get_settings
from infrastructure.storage.r2_file_storage import (
    R2FileStorage,
)


async def main() -> None:
    settings = get_settings()

    storage = R2FileStorage(
        endpoint=settings.r2_endpoint,
        access_key_id=(
            settings.r2_access_key_id
        ),
        secret_access_key=(
            settings.r2_secret_access_key
        ),
        bucket_name=(
            settings.r2_bucket_name
        ),
    )

    object_key = (
        "tests/a0-02/"
        "r2-storage-test.txt"
    )

    await storage.upload(
        object_key=object_key,
        content=b"P234 A0-02 R2 test",
        content_type="text/plain",
    )

    print("Upload: PASS")
    print("Object key:", object_key)

    await storage.delete(
        object_key
    )

    print("Delete: PASS")
    print("R2 storage test PASS")


asyncio.run(main())
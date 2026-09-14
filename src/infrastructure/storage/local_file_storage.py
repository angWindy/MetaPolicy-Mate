from pathlib import Path

from src.application.common.interfaces.file_storage import (
    FileStorage,
)


class LocalFileStorage(
    FileStorage
):
    """Local filesystem-backed file storage. Used when R2 credentials
    are not configured (placeholder values in .env) or for offline/demo
    workflows. Files are stored under ``root_dir`` using the object key
    as relative path with subdirectory prefix preserved.
    """

    def __init__(
        self,
        root_dir: str | Path,
    ) -> None:
        self._root = (
            Path(root_dir).resolve()
        )
        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _resolve_path(
        self,
        object_key: str,
    ) -> Path:
        # Prevent path traversal: strip leading slashes & parent refs.
        safe = (
            object_key
            .lstrip("/")
            .replace("..", "")
        )
        return self._root / safe

    async def upload(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        path = self._resolve_path(
            object_key
        )
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_bytes(content)

    async def delete(
        self,
        object_key: str,
    ) -> None:
        path = self._resolve_path(
            object_key
        )
        if path.exists():
            path.unlink()

    async def delete_objects(
        self,
        object_keys: list[str],
    ) -> list[str]:
        """Local-fs analogue of the R2 bulk delete.

        Returns the keys whose ``unlink`` raised — callers can treat
        the list as the partial-failure surface for parity with the
        R2 implementation.
        """
        errors: list[str] = []
        for key in object_keys:
            path = self._resolve_path(key)
            try:
                if path.exists():
                    path.unlink()
            except Exception:  # noqa: BLE001
                errors.append(key)
        return errors

    async def download(
        self,
        object_key: str,
    ) -> bytes:
        path = self._resolve_path(
            object_key
        )
        if not path.exists():
            raise FileNotFoundError(
                f"Object not found: {object_key}"
            )
        return path.read_bytes()

    async def get_object(
        self,
        object_key: str,
    ) -> bytes:
        return await self.download(object_key)

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
    ) -> None:
        """Local copy (read + write through application)."""
        src = self._resolve_path(source_key)
        dst = self._resolve_path(dest_key)
        if not src.exists():
            raise FileNotFoundError(
                f"Source not found: {source_key}"
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    async def head_object(
        self,
        object_key: str,
    ) -> dict[str, object] | None:
        """Return metadata dict or ``None`` if the key does not exist."""
        path = self._resolve_path(object_key)
        if not path.exists():
            return None
        stat = path.stat()
        return {
            "ContentLength": stat.st_size,
            "LastModified": stat.st_mtime,
        }

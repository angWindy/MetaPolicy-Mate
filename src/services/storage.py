from pathlib import Path


class LocalDocumentStorage:
    """Isolate uploaded files until parsing succeeds, then promote them."""

    def __init__(self, raw_dir: Path, quarantine_dir: Path):
        self.raw_dir = raw_dir
        self.quarantine_dir = quarantine_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_number(document_number: str) -> str:
        return "".join(character if character.isalnum() or character in "-_." else "_" for character in document_number)

    def save_quarantine(
        self,
        *,
        document_number: str,
        version_number: int,
        filename: str,
        content: bytes,
    ) -> Path:
        directory = self.quarantine_dir / self._safe_number(document_number) / f"v{version_number}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / Path(filename).name
        path.write_bytes(content)
        return path

    def promote(
        self,
        quarantined_path: Path,
        *,
        document_number: str,
        version_number: int,
        filename: str,
    ) -> Path:
        directory = self.raw_dir / self._safe_number(document_number) / f"v{version_number}"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / Path(filename).name
        quarantined_path.replace(destination)
        return destination

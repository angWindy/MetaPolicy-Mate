#!/usr/bin/env python3
"""Consolidate data/raw/ into HUST/ + HUCE/ flat folders only.

Plan reference: approved "Cleanup + Admin UI + RAG Redesign" §1.3.

The current state has two competing layouts under ``data/raw/``:

* Flat per-school folders: ``HUST/*.pdf`` + ``HUCE/*.pdf`` (22 files).
* Structured per-doc folders: ``RAW-<SCHOOL>-*/v1/*.pdf`` (22 files).
* Quarantine mirror: ``data/quarantine/RAW-*/v1/*.pdf`` (also 22 files).

The structured folders are exact SHA-256 duplicates of the flat ones
(verified at the time of writing this script). The consolidation step
removes both the structured copies and the quarantine mirror, then
writes a backup manifest so the deletion is auditable.

Safety model:

* dry-run by default; ``--apply`` required to delete.
* Refuses to run unless **every** RAW PDF matches a flat PDF by
  checksum; otherwise exits non-zero with a list of mismatches.
* Manifest is always written (even on dry-run) for audit.

Usage::

    python scripts/consolidate_raw_pdfs.py            # dry-run
    python scripts/consolidate_raw_pdfs.py --apply    # actually delete
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("consolidate_raw_pdfs")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
QUAR_DIR = PROJECT_ROOT / "data" / "quarantine"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "_archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Stable flat-folder roots — only these two will remain after the run.
ALLOWED_SCHOOL_DIRS: frozenset[str] = frozenset({"HUST", "HUCE"})


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------


@dataclass
class ConsolidateManifest:
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = ""
    apply: bool = False
    flat_schools_found: list[str] = field(default_factory=list)
    flat_pdf_count: int = 0
    raw_pdf_count: int = 0
    quarantine_pdf_count: int = 0
    checksum_mismatches: list[dict[str, str]] = field(default_factory=list)
    missing_from_flat: list[str] = field(default_factory=list)
    raw_dirs_removed: list[str] = field(default_factory=list)
    quarantine_dirs_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _flat_index() -> dict[str, tuple[Path, str]]:
    """Map ``<school>/<file>.pdf`` -> (path, sha256) for the flat folders."""
    index: dict[str, tuple[Path, str]] = {}
    for school in ALLOWED_SCHOOL_DIRS:
        school_dir = RAW_DIR / school
        if not school_dir.is_dir():
            continue
        for pdf in sorted(school_dir.glob("*.pdf")):
            key = f"{school}/{pdf.name}"
            index[key] = (pdf, _sha256(pdf))
    return index


def _structured_index(root: Path) -> dict[str, tuple[Path, str]]:
    """Map ``<school>/<file>.pdf`` -> (path, sha256) for ``RAW-<SCHOOL>-*``.

    The folder name is ``RAW-<SCHOOL>-<slug>``; the school is token 1.
    """
    index: dict[str, tuple[Path, str]] = {}
    if not root.is_dir():
        return index
    for folder in sorted(root.glob("RAW-*")):
        if not folder.is_dir():
            continue
        parts = folder.name.split("-", 2)
        if len(parts) < 3:
            continue
        school = parts[1].upper()
        v1 = folder / "v1"
        if not v1.is_dir():
            continue
        for pdf in sorted(v1.glob("*.pdf")):
            key = f"{school}/{pdf.name}"
            index[key] = (pdf, _sha256(pdf))
    return index


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _verify(
    flat: dict[str, tuple[Path, str]],
    other: dict[str, tuple[Path, str]],
    label: str,
    manifest: ConsolidateManifest,
) -> bool:
    """Confirm every ``other`` entry matches a ``flat`` entry by checksum.

    Returns True on success. On failure the mismatches and missing
    entries are recorded on the manifest and the function returns False.
    """
    ok = True
    other_keys = set(other.keys())
    flat_keys = set(flat.keys())

    for key in sorted(other_keys - flat_keys):
        manifest.missing_from_flat.append(
            f"{label}:{key}"
        )
        ok = False
        log.error(
            "%s has '%s' but no matching FLAT entry", label, key,
        )

    for key in sorted(other_keys & flat_keys):
        f_path, f_sha = flat[key]
        o_path, o_sha = other[key]
        if f_sha != o_sha:
            manifest.checksum_mismatches.append({
                "key": key,
                "label": label,
                "flat_sha256": f_sha,
                "other_sha256": o_sha,
                "flat_path": str(f_path.relative_to(PROJECT_ROOT)),
                "other_path": str(o_path.relative_to(PROJECT_ROOT)),
            })
            ok = False
            log.error(
                "%s checksum mismatch for '%s'", label, key,
            )
    return ok


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Consolidate data/raw/ into HUST/ + HUCE/. "
            "Dry-run by default; pass --apply to commit."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete RAW-* and quarantine/RAW-* folders.",
    )
    parser.add_argument(
        "--manifest",
        default=str(ARCHIVE_DIR / "consolidate_manifest.json"),
        help="Path to the JSON manifest output.",
    )
    args = parser.parse_args()

    manifest = ConsolidateManifest(apply=args.apply)

    log.info(
        "Starting consolidate_raw_pdfs (apply=%s)", args.apply,
    )

    try:
        if not RAW_DIR.is_dir():
            raise SystemExit(f"data/raw/ missing: {RAW_DIR}")

        flat = _flat_index()
        manifest.flat_pdf_count = len(flat)
        manifest.flat_schools_found = sorted({
            k.split("/", 1)[0] for k in flat
        })

        raw_struct = _structured_index(RAW_DIR)
        manifest.raw_pdf_count = len(raw_struct)

        quaran = _structured_index(QUAR_DIR)
        manifest.quarantine_pdf_count = len(quaran)

        log.info(
            "Discovered: %d flat PDFs across %s, %d RAW-* PDFs, %d quarantine PDFs",
            manifest.flat_pdf_count,
            manifest.flat_schools_found,
            manifest.raw_pdf_count,
            manifest.quarantine_pdf_count,
        )

        # Refuse to delete if RAW-* has anything not in FLAT or
        # checksum-mismatched. (Consolidation must be loss-less.)
        ok_raw = _verify(flat, raw_struct, "raw", manifest)
        ok_q = _verify(flat, quaran, "quarantine", manifest)

        if not (ok_raw and ok_q):
            manifest.errors.append(
                "verification_failed: see checksum_mismatches / missing_from_flat"
            )
            log.error(
                "Refusing to consolidate: verification failed. "
                "Resolve mismatches and re-run."
            )
        else:
            log.info("Verification OK — every structured PDF matches a flat one")

        if ok_raw and ok_q and args.apply:
            # Delete RAW-* under data/raw/
            for folder in sorted(RAW_DIR.glob("RAW-*")):
                if not folder.is_dir():
                    continue
                # Remove its files then the folder (rmtree-ish via shutil).
                import shutil

                shutil.rmtree(folder)
                manifest.raw_dirs_removed.append(
                    str(folder.relative_to(PROJECT_ROOT))
                )
            log.info(
                "Removed %d RAW-* folders under data/raw/",
                len(manifest.raw_dirs_removed),
            )

            # Delete RAW-* under data/quarantine/
            for folder in sorted(QUAR_DIR.glob("RAW-*")):
                if not folder.is_dir():
                    continue
                import shutil

                shutil.rmtree(folder)
                manifest.quarantine_dirs_removed.append(
                    str(folder.relative_to(PROJECT_ROOT))
                )
            log.info(
                "Removed %d RAW-* folders under data/quarantine/",
                len(manifest.quarantine_dirs_removed),
            )
        elif not args.apply:
            log.info(
                "DRY RUN — would remove %d RAW-* + %d quarantine folders",
                len(raw_struct),
                len(quaran),
            )
    except Exception as exc:  # noqa: BLE001
        manifest.errors.append(f"{type(exc).__name__}: {exc}")
        log.exception("Consolidate failed")
    finally:
        manifest.finish()

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Manifest: %s", manifest_path)

    if manifest.errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

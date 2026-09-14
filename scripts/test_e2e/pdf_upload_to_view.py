"""End-to-end test: upload a PDF through the admin API, then GET it back.

Run while the backend is up::

    source /home/angwindy/miniconda3/etc/profile.d/conda.sh
    conda activate p234
    python scripts/test_e2e/pdf_upload_to_view.py

The test:

1. Logs in as admin@p234.demo.
2. POSTs /api/v1/regulatory-documents/upload with a real PDF from
   data/raw/HUST/HUST-10232.pdf.
3. Records the returned document_id and version_id.
4. GETs /api/v1/regulatory-documents/{document_id}/source and asserts:
   - status 200
   - Content-Type starts with "application/pdf"
   - body SHA256 matches the uploaded file's SHA256
5. Cleans up by deleting the document at the end (admin-only).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import date
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PDF = PROJECT_ROOT / "data" / "raw" / "HUST" / "10232.pdf"


async def _login(
    client: httpx.AsyncClient,
    base_url: str,
) -> str:
    response = await client.post(
        f"{base_url}/api/v1/auth/login",
        json={
            "email": "admin@p234.demo",
            "password": "P234@123",
            "device_id": "e2e-pdf-upload",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return payload["access_token"]


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help="Path to the PDF to upload",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not DELETE the document at the end.",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    pdf_bytes = args.pdf.read_bytes()
    sha_upload = hashlib.sha256(pdf_bytes).hexdigest()
    print(f"=== E2E PDF upload -> view ===")
    print(f"PDF: {args.pdf} ({len(pdf_bytes)} bytes, sha256={sha_upload[:12]}..)")
    print(f"API: {args.api_base}")
    print()

    async with httpx.AsyncClient(timeout=60.0) as client:
        token = await _login(client, args.api_base)
        headers = {"Authorization": f"Bearer {token}"}

        # 1) Upload.
        document_number = f"E2E-{date.today().isoformat()}-{sha_upload[:8]}"
        upload_response = await client.post(
            f"{args.api_base}/api/v1/regulatory-documents/upload",
            headers=headers,
            data={
                "document_number": document_number,
                "title": f"E2E test {args.pdf.stem}",
                "issued_by": "P234 E2E",
                "issued_date": date.today().isoformat(),
                "effective_date": date.today().isoformat(),
            },
            files={
                "file": (
                    args.pdf.name,
                    pdf_bytes,
                    "application/pdf",
                ),
            },
        )
        print(f"POST upload -> {upload_response.status_code}")
        if upload_response.status_code != 201:
            print(upload_response.text)
            return 1
        upload_body = upload_response.json()
        document_id = upload_body["id"]
        print(f"  document_id={document_id}")
        print(f"  title={upload_body.get('title')!r}")

        # 2) Retrieve.
        source_response = await client.get(
            f"{args.api_base}/api/v1/regulatory-documents/{document_id}/source",
            headers=headers,
        )
        print(f"GET source -> {source_response.status_code}")
        if source_response.status_code != 200:
            print(source_response.text)
            return 1
        content_type = source_response.headers.get("Content-Type", "")
        body = source_response.content
        sha_download = hashlib.sha256(body).hexdigest()
        print(
            f"  Content-Type={content_type} "
            f"len={len(body)} sha256={sha_download[:12]}.."
        )
        if not content_type.startswith("application/pdf"):
            print(
                f"FAIL: expected application/pdf, got {content_type!r}",
                file=sys.stderr,
            )
            return 1
        if sha_download != sha_upload:
            print(
                "FAIL: download body SHA does not match uploaded body",
                file=sys.stderr,
            )
            return 1
        print("  OK: round-trip matches uploaded PDF.")

        # 3) Optional cleanup.
        if not args.keep:
            delete_response = await client.delete(
                f"{args.api_base}/api/v1/regulatory-documents/{document_id}",
                headers=headers,
            )
            print(
                f"DELETE cleanup -> {delete_response.status_code}"
            )
            if delete_response.status_code not in (204, 404, 405):
                print(delete_response.text)
                return 1

    print()
    print("PASS: upload + view + (optional) delete succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""End-to-end PDF permission test.

Verifies that:
- ADMIN can upload a PDF and fetch it back via /source (200).
- LECTURER from a *different* school who is not on the allow-list gets
  403 when fetching the source.
- ADMIN can still fetch the source after a LECTURER's failed attempt.

Run while backend is up::

    source /home/angwindy/miniconda3/etc/profile.d/conda.sh
    conda activate p234
    python scripts/test_e2e/pdf_retrieve_permission.py
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
    client: httpx.AsyncClient, base_url: str, email: str, password: str
) -> str:
    response = await client.post(
        f"{base_url}/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": f"e2e-perm-{email.split('@')[0]}",
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _upload(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    pdf_path: Path,
    document_number: str,
) -> str:
    pdf_bytes = pdf_path.read_bytes()
    response = await client.post(
        f"{base_url}/api/v1/regulatory-documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "document_number": document_number,
            "title": f"E2E permission test {pdf_path.stem}",
            "issued_by": "P234 E2E",
            "issued_date": date.today().isoformat(),
            "effective_date": date.today().isoformat(),
        },
        files={
            "file": (
                pdf_path.name,
                pdf_bytes,
                "application/pdf",
            ),
        },
    )
    response.raise_for_status()
    document_id = response.json()["id"]
    # The default access_scope is PUBLIC, which lets any department read
    # the source. Force it to DEPARTMENT so the cross-school user is
    # denied via the document_department lookup.
    try:
        import psycopg  # noqa: PLC0415

        conn = psycopg.connect(
            "postgresql://neondb_owner:"
            "npg_AKDtQliGzj63"
            "@ep-proud-base-a70h0gom-pooler."
            "ap-southeast-2.aws.neon.tech/p234_uc_demo"
            "?sslmode=require",
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SET search_path TO public, rag_legacy"
            )
            cur.execute(
                "UPDATE documents SET access_scope = 'DEPARTMENT' "
                "WHERE id = %s::uuid",
                (document_id,),
            )
            # ADMIN and HUCE both belong to Administration; grant them
            # access via the document_departments mapping so the
            # cross-department test is meaningful.
            cur.execute(
                "INSERT INTO document_departments "
                "(document_id, department_id) VALUES "
                "(%s::uuid, '050813ff-d105-4b95-aab2-fe8c7e3a33f7') "
                "ON CONFLICT DO NOTHING",
                (document_id,),
            )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN: failed to restrict scope: {exc}")
    return document_id


async def _fetch_source(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    document_id: str,
) -> httpx.Response:
    return await client.get(
        f"{base_url}/api/v1/regulatory-documents/{document_id}/source",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _cleanup_db(document_id: str) -> None:
    """Best-effort DB cleanup so the test is idempotent."""
    try:
        import psycopg  # noqa: PLC0415

        conn = psycopg.connect(
            "postgresql://neondb_owner:"
            "npg_AKDtQliGzj63"
            "@ep-proud-base-a70h0gom-pooler."
            "ap-southeast-2.aws.neon.tech/p234_uc_demo"
            "?sslmode=require",
            connect_timeout=10,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SET search_path TO public, rag_legacy"
            )
            cur.execute(
                "DELETE FROM document_departments "
                "WHERE document_id = %s::uuid",
                (document_id,),
            )
            cur.execute(
                "DELETE FROM documents WHERE id = %s::uuid",
                (document_id,),
            )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN: cleanup failed: {exc}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    pdf_bytes = args.pdf.read_bytes()
    sha = hashlib.sha256(pdf_bytes).hexdigest()[:8]
    document_number = (
        f"PERM-{date.today().isoformat()}-{sha}"
    )

    print("=== E2E PDF permission ===")
    print(f"PDF: {args.pdf}")
    print(f"document_number={document_number}")
    print()

    async with httpx.AsyncClient(timeout=60.0) as client:
        admin_token = await _login(
            client,
            args.api_base,
            "admin@p234.demo",
            "P234@123",
        )
        hust_token = await _login(
            client,
            args.api_base,
            "hust@p234.demo",
            "P234@123",
        )
        huce_token = await _login(
            client,
            args.api_base,
            "huce@p234.demo",
            "P234@123",
        )

        # Upload as ADMIN (school_id=aaaa... from seed).
        document_id = await _upload(
            client,
            args.api_base,
            admin_token,
            args.pdf,
            document_number,
        )
        print(f"Uploaded document_id={document_id}")

        # 1) ADMIN (Administration dept) should fetch source 200.
        resp_admin = await _fetch_source(
            client, args.api_base, admin_token, document_id
        )
        print(f"ADMIN GET source -> {resp_admin.status_code}")
        if resp_admin.status_code != 200:
            print(resp_admin.text)
            if not args.keep:
                await _cleanup_db(document_id)
            return 1

        # 2) HUST-LECTURER (Academic Affairs dept) is in a *different*
        # department than ADMIN and should be denied (403) because the
        # document was forced to access_scope=DEPARTMENT above.
        resp_hust = await _fetch_source(
            client, args.api_base, hust_token, document_id
        )
        print(f"HUST-LECTURER GET source -> {resp_hust.status_code}")
        if resp_hust.status_code != 403:
            print(
                f"FAIL: expected 403 for HUST user, "
                f"got {resp_hust.status_code}",
                file=sys.stderr,
            )
            print(resp_hust.text)
            if not args.keep:
                await _cleanup_db(document_id)
            return 1

        # 3) HUCE-LECTURER shares ADMIN's Administration department, so
        # they should still be allowed (200). Confirms the 403 above is
        # truly department-scoped, not blanket rejection.
        resp_huce = await _fetch_source(
            client, args.api_base, huce_token, document_id
        )
        print(f"HUCE-LECTURER GET source -> {resp_huce.status_code}")
        if resp_huce.status_code != 200:
            print(
                f"FAIL: expected 200 for HUCE user, "
                f"got {resp_huce.status_code}",
                file=sys.stderr,
            )
            print(resp_huce.text)
            if not args.keep:
                await _cleanup_db(document_id)
            return 1

        # 4) ADMIN can still fetch after a denied attempt.
        resp_admin2 = await _fetch_source(
            client, args.api_base, admin_token, document_id
        )
        print(f"ADMIN GET source (again) -> {resp_admin2.status_code}")
        if resp_admin2.status_code != 200:
            print(resp_admin2.text)
            if not args.keep:
                await _cleanup_db(document_id)
            return 1

        if not args.keep:
            await _cleanup_db(document_id)

    print()
    print(
        "PASS: ADMIN + same-department LECTURER allowed; "
        "cross-department LECTURER denied."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
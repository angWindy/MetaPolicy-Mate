"""Cross-check the configuration of `.env` and `.env.rag`.

Prints a comparison table of every database/vector/store URL the runtime reads,
then actively pings each external service so we fail loud before any user does.

Checks performed:

* `DATABASE_URL`    (.env / .env.rag) -> backend schema `public` AND RAG
                                       schema `rag_legacy` (single shared key)
* `QDRANT_URL`      (.env.rag)        -> Qdrant vector store
* `OPENAI_API_KEY`  (.env / .env.rag) -> embedding / generator provider

Both backend and RAG layer point at the same Neon cluster; src/db/session.py
applies `schema_translate_map={"None": "rag_legacy"}` so the two schemas never
collide in the same database.

The script intentionally does NOT mutate anything - safe to run anywhere.

Exit code 0 when everything is reachable; 1 otherwise. The output is plain
text by default; pass `--json` for machine-parseable results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


REDACTED_KEY_LEN = 4


def mask(value: str | None, *, keep: int = REDACTED_KEY_LEN) -> str:
    """Hide all but the trailing ``keep`` chars of a secret-like value."""
    if not value:
        return ""
    if len(value) <= keep:
        return "***"
    return f"***{value[-keep:]}"


def host_of(url: str) -> str:
    return urlparse(url).hostname or ""


def scheme_of(url: str) -> str:
    return urlparse(url).scheme.split("+", 1)[0]


def render_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    label_w = max(len(label) for label, _ in rows)
    width = 80
    lines = [f"{'Key'.ljust(label_w)}  Value"]
    lines.append("-" * width)
    for label, value in rows:
        lines.append(f"{label.ljust(label_w)}  {value}")
    return "\n".join(lines)


def ping_postgres(url: str) -> tuple[bool, str]:
    try:
        import psycopg  # type: ignore
    except ImportError:
        return False, "psycopg not installed"
    try:
        # Normalise scheme so psycopg.connect accepts the URL.
        target = url
        if target.startswith("postgresql+psycopg://"):
            target = target.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(target, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, "SELECT 1 ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def ping_qdrant(url: str, collection: str) -> tuple[bool, str]:
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except ImportError:
        return False, "qdrant-client not installed"
    try:
        client = QdrantClient(url=url, timeout=5.0, check_compatibility=False)
        collections = client.get_collections()
        names = [c.name for c in collections.collections]
        if collection and collection in names:
            return True, f"qdrant reachable, '{collection}' ready"
        return True, f"qdrant reachable (collections={names})"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def ping_openai(key: str) -> tuple[bool, str]:
    if not key:
        return False, "OPENAI_API_KEY is empty"
    try:
        import urllib.request

        req = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a human-readable report.",
    )
    parser.add_argument(
        "--no-ping",
        action="store_true",
        help="Skip live pings (only compare values locally).",
    )
    args = parser.parse_args()

    # Local imports so the script can be `--help`d without a full install.
    from src.config import get_settings  # noqa: E402
    from src.rag.config import get_rag_settings  # noqa: E402

    settings = get_settings()
    rag = get_rag_settings()

    db_url = settings.database_url
    rag_url = rag.database_url
    qdrant_url = rag.qdrant_url
    collection = rag.qdrant_collection
    openai_key = (
        rag.openai_api_key
        or settings.openai_api_key
        or ""
    )

    # ---- URL consistency comparisons --------------------------------------
    host_db = host_of(db_url)
    host_rag = host_of(rag_url)
    host_qdrant = host_of(qdrant_url) if qdrant_url else ""
    scheme_db = scheme_of(db_url)
    scheme_rag = scheme_of(rag_url)

    warnings: list[str] = []

    if host_db and host_rag and host_db != host_rag:
        warnings.append(
            "Backend DATABASE_URL and RAG DATABASE_URL target different hosts; "
            "this is allowed but they will not share data unless the DB is "
            "intentionally split.",
        )
    if scheme_db and scheme_rag and scheme_db != scheme_rag:
        warnings.append(
            f"DB scheme mismatch: backend={scheme_db}, rag={scheme_rag}",
        )

    # ---- Live pings -------------------------------------------------------
    pings: dict[str, dict[str, str]] = {}
    if not args.no_ping:
        ok, msg = ping_postgres(db_url)
        pings["DATABASE_URL (backend)"] = {"ok": str(ok), "detail": msg}
        ok, msg = ping_postgres(rag_url)
        pings["DATABASE_URL (RAG)"] = {"ok": str(ok), "detail": msg}
        if rag.vector_backend == "qdrant":
            ok, msg = ping_qdrant(qdrant_url, collection)
            pings["QDRANT_URL"] = {"ok": str(ok), "detail": msg}
        else:
            pings["QDRANT_URL"] = {
                "ok": "n/a",
                "detail": f"vector_backend={rag.vector_backend}",
            }
        ok, msg = ping_openai(openai_key)
        pings["OPENAI_API_KEY"] = {"ok": str(ok), "detail": msg}

    report = {
        "settings": {
            "DATABASE_URL (backend)": db_url,
            "DATABASE_URL (RAG)": rag_url,
            "QDRANT_URL": qdrant_url,
            "QDRANT_COLLECTION": collection,
            "VECTOR_BACKEND": rag.vector_backend,
            "GENERATOR_PROVIDER": rag.generator_provider,
            "EMBEDDING_PROVIDER": rag.embedding_provider,
            "OPENAI_API_KEY": mask(openai_key),
        },
        "warnings": warnings,
        "pings": pings,
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        rows: list[tuple[str, str]] = []
        rows.append(("DATABASE_URL (backend)", db_url))
        rows.append(("DATABASE_URL (RAG)", rag_url))
        rows.append(("QDRANT_URL", qdrant_url))
        rows.append(("QDRANT_COLLECTION", collection))
        rows.append(("VECTOR_BACKEND", rag.vector_backend))
        rows.append(("GENERATOR_PROVIDER", rag.generator_provider))
        rows.append(("EMBEDDING_PROVIDER", rag.embedding_provider))
        rows.append(("OPENAI_API_KEY", mask(openai_key)))
        print("== env consistency report ==")
        print(render_table(rows))
        if warnings:
            print()
            print("Warnings:")
            for w in warnings:
                print(f"  - {w}")
        if pings:
            print()
            print("Live pings:")
            for key, info in pings.items():
                marker = "OK" if info["ok"] in {"True", "ok", "n/a"} else "FAIL"
                print(f"  [{marker}] {key}: {info['detail']}")

    failed = [k for k, v in pings.items() if v["ok"] == "False"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

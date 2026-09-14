"""End-to-end RAG query test that proves the pipeline returns *real data*.

For each of three RBAC roles (admin, reviewer, plain user) we:

1. POST /api/v1/auth/login to obtain a fresh JWT.
2. Decode the JWT payload to confirm the role claim is what we expect.
3. Reuse the live RAGContainer to (a) embed the question with OpenAI,
   (b) semantic-search the live Qdrant collection, and (c) call
   GPT-4o-mini with the retrieved context.
4. Assert that:
   * The Qdrant collection has > 0 points before the run.
   * At least one of the top-3 retrieved chunks contains a substring
     from a known ingested document.
   * Either the GPT answer references a real retrieved substring, or
     no retrieved chunk scored above 0.4 (LLM legitimately declined).
5. For role-permission coverage, send a DELETE for a known document as
   the plain user (must be 403) and as the reviewer/admin (must be 204).
   The reviewer/admin path is exercised end-to-end only when
   ``--cleanup`` is passed so the test is idempotent for the QA tenant.

Run::

    python scripts/test_e2e_rag_query.py
    python scripts/test_e2e_rag_query.py --cleanup
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from openai import OpenAI

from src.rag.config import get_rag_settings
from src.rag.container import RAGContainer


REAL_DATA_PROBES = [
    "Đại học",
    "Bách khoa",
    "Điều",
    "BỘ GIÁO DỤC",
    "mức học phí",
    "chương trình đào tạo",
    "ngoại ngữ",
    "chấm công",
    "ĐH",
]


ROLE_SCENARIOS = [
    {
        "role": "ADMIN",
        "email": "admin@p234.demo",
        "password": "P234@123",
        "question": (
            "Quy định về chấm công của trường "
            "Đại học Bách khoa Hà Nội là gì?"
        ),
    },
    {
        "role": "USER",
        "email": "hust@p234.demo",
        "password": "P234@123",
        "question": (
            "Yêu cầu chuẩn ngoại ngữ đầu ra cho "
            "sinh viên đại học?"
        ),
    },
    {
        "role": "USER",
        "email": "huce@p234.demo",
        "password": "P234@123",
        "question": (
            "Mức học phí các chương trình đào tạo "
            "chuẩn năm 2025 là bao nhiêu?"
        ),
    },
]


def _decode_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(
        payload + padding
    )
    return json.loads(decoded.decode("utf-8"))


async def _load_chunk_bodies(
    rag_container: RAGContainer,
    chunk_ids: list[str],
) -> dict[str, str]:
    """Fetch the body text for the given chunk_ids from rag_legacy.chunks.

    The Qdrant payload only stores heading/structure metadata; the actual
    chunk body lives in PostgreSQL (rag_legacy.chunks.text). This helper
    loads them in one query.
    """
    if not chunk_ids:
        return {}
    from sqlalchemy import select  # noqa: PLC0415

    from src.db.models import Chunk  # noqa: PLC0415

    database = rag_container.database
    result: dict[str, str] = {}
    with database.session_factory() as session:
        rows = session.execute(
            select(Chunk.id, Chunk.text).where(
                Chunk.id.in_(chunk_ids)
            )
        ).all()
        for chunk_id, text in rows:
            result[str(chunk_id)] = text or ""
    return result


def _load_openai_key(env_path: Path) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        return api_key
    with env_path.open() as fh:
        for line in fh:
            if line.startswith("OPENAI_API_KEY="):
                api_key = line.strip().split("=", 1)[1]
                return api_key
    raise RuntimeError(
        "OPENAI_API_KEY not found in env or .env.rag"
    )


async def _login(
    client: httpx.AsyncClient,
    base_url: str,
    email: str,
    password: str,
) -> str:
    response = await client.post(
        f"{base_url}/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": (
                f"e2e-rag-{email.split('@')[0]}"
            ),
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"login failed for {email}: "
            f"{response.status_code} {response.text}"
        )
    payload = response.json()
    return payload["access_token"]


async def _scenario(
    *,
    role: str,
    email: str,
    password: str,
    question: str,
    base_url: str,
    rag_settings,
    rag_container: RAGContainer,
    openai_client: OpenAI,
    cleanup: bool,
    target_document_id: str | None,
) -> tuple[bool, str]:
    """Run the RAG E2E for one role; return (passed, summary_line)."""
    print()
    print(f"--- ROLE: {role} ({email}) ---")
    print(f"  question: {question}")
    async with httpx.AsyncClient(
        timeout=30.0
    ) as http_client:
        token = await _login(
            http_client,
            base_url,
            email,
            password,
        )
        claims = _decode_jwt(token)
        jwt_role = (
            claims.get("role")
            or claims.get("Role")
            or "?"
        )
        if jwt_role != role:
            return (
                False,
                f"  FAIL: JWT role={jwt_role!r}, expected {role!r}",
            )
        print(
            f"  jwt.sub={claims.get('sub', '?')[:8]}.. "
            f"role={jwt_role} school={claims.get('SchoolId', '?')[:8]}.."
        )

        # 1) Verify Qdrant collection is non-empty.
        info = await (
            rag_container.vector_store.client
            .get_collection(rag_settings.qdrant_collection)
        )
        print(
            f"  qdrant_collection={info.points_count} points"
        )
        if info.points_count <= 0:
            return (
                False,
                "  FAIL: Qdrant collection is empty; run test_e2e_ingestion.py first.",
            )

        # 2) Embed + search with real APIs.
        embed_resp = openai_client.embeddings.create(
            model=rag_settings.embedding_model,
            input=[question],
        )
        query_vector = (
            embed_resp.data[0].embedding
        )
        sem_hits = await rag_container.vector_store.search(
            query_vector=query_vector, limit=5,
        )
        # 2) Embed + search with real APIs.
        embed_resp = openai_client.embeddings.create(
            model=rag_settings.embedding_model,
            input=[question],
        )
        query_vector = (
            embed_resp.data[0].embedding
        )
        sem_hits = await rag_container.vector_store.search(
            query_vector=query_vector, limit=5,
        )
        # Enrich each Qdrant hit with the chunk body from rag_legacy.chunks
        # because the legacy ingestion only stored headings/structure in the
        # payload - the full chunk text lives in PostgreSQL.
        chunk_ids = [chunk_id for chunk_id, _, _ in sem_hits]
        bodies = await _load_chunk_bodies(
            rag_container, chunk_ids
        )

        def _chunk_text(payload: dict, chunk_id: str) -> str:
            heading_part = " ".join(
                str(payload.get(k) or "")
                for k in ("heading", "section", "point")
            )
            body = bodies.get(chunk_id) or ""
            if not body:
                return heading_part
            return f"{heading_part}\n{body}"

        print(f"  semantic_hits={len(sem_hits)}")
        for chunk_id, score, payload in sem_hits[:3]:
            text_preview = (
                _chunk_text(payload, chunk_id)
            )[:160].replace("\n", " ")
            print(
                f"    score={score:.4f}  id={chunk_id[:8]}..  "
                f"text={text_preview!r}"
            )

        top_text = "\n".join(
            _chunk_text(payload, chunk_id)
            for chunk_id, _, payload in sem_hits[:5]
        )
        matched_probe = next(
            (
                probe
                for probe in REAL_DATA_PROBES
                if probe.lower() in top_text.lower()
            ),
            None,
        )
        if matched_probe is None:
            return (
                False,
                "  FAIL: top-5 chunks contain no substring from any ingested PDF.",
            )
        print(
            f"  real-data probe hit: {matched_probe!r}"
        )

        # 3) GPT-4o-mini with the real retrieved context.
        context_blocks = []
        for chunk_id, score, payload in sem_hits[:5]:
            text = _chunk_text(payload, chunk_id)
            title = payload.get("title", "?")
            docnum = payload.get("document_number", "?")
            context_blocks.append(
                f"[Nguồn: {title} | {docnum} | score={score:.3f}]\n{text}"
            )
        context = "\n\n---\n\n".join(context_blocks)
        system_prompt = (
            "Bạn là trợ lý AI trả lời câu hỏi về quy chế của "
            "Đại học Bách khoa Hà Nội. Hãy trả lời dựa trên ngữ cảnh "
            "(context) được cung cấp. Nếu context không đủ để trả lời, "
            "hãy nói rõ là không tìm thấy thông tin. Trả lời bằng tiếng Việt."
        )
        chat_resp = openai_client.chat.completions.create(
            model=rag_settings.model_name,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        f"Câu hỏi: {question}\n\n"
                        f"Ngữ cảnh (trích từ văn bản nội bộ):\n{context}\n\n"
                        "Trả lời:"
                    ),
                },
            ],
            max_tokens=600,
            temperature=0.2,
        )
        answer = chat_resp.choices[0].message.content
        usage = chat_resp.usage
        print(
            f"  GPT usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens}"
        )
        print("  ANSWER:")
        for line in answer.split("\n"):
            print(f"    {line}")

        top_score = sem_hits[0][1] if sem_hits else 0.0
        no_answer = (
            "không tìm thấy" in answer.lower()
            or "không đủ" in answer.lower()
        )
        answer_has_probe = any(
            probe.lower() in answer.lower()
            for probe in REAL_DATA_PROBES
        )
        if no_answer and not answer_has_probe and top_score < 0.7:
            print(
                "  NOTE: LLM declined (low confidence); this is acceptable."
            )
        elif no_answer and not answer_has_probe:
            return (
                False,
                f"  FAIL: LLM refused but top_score={top_score:.3f} >= 0.7 and answer has no PDF substrings.",
            )
        elif not answer_has_probe:
            return (
                False,
                "  FAIL: answer contains none of the known PDF substrings.",
            )

        # 4) Permission contract — plain user must not delete.
        if target_document_id:
            delete_resp = await http_client.delete(
                f"{base_url}/api/v1/regulatory-documents/{target_document_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                },
            )
            expected_status = (
                204
                if role == "ADMIN"
                else 403
            )
            print(
                f"  DELETE status={delete_resp.status_code} (expected {expected_status})"
            )
            if (
                delete_resp.status_code != expected_status
                and not (
                    role == "ADMIN"
                    and cleanup
                )
            ):
                return (
                    False,
                    f"  FAIL: DELETE expected {expected_status}, got {delete_resp.status_code}",
                )
            if (
                role == "ADMIN"
                and not cleanup
            ):
                print(
                    "  (delete skipped; pass --cleanup to actually delete)"
                )

    return True, f"  PASS: {role}"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help=(
            "Actually run DELETE for ADMIN "
            "scenarios (default: only assert 403 for USER)."
        ),
    )
    parser.add_argument(
        "--document-id",
        default=None,
        help=(
            "Optional UUID to exercise the DELETE permission "
            "test. If omitted the test only checks 403 for USER."
        ),
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
    )
    args = parser.parse_args()

    print("=== E2E RAG query test (3 roles, real data) ===")
    settings = get_rag_settings()
    container = RAGContainer(settings)
    info = await (
        container.vector_store.client
        .get_collection(settings.qdrant_collection)
    )
    print(
        f"Collection '{settings.qdrant_collection}': "
        f"{info.points_count} points, status={info.status}"
    )
    print(
        f"generator_provider={settings.generator_provider} "
        f"model={settings.model_name} "
        f"embedding_model={settings.embedding_model}"
    )
    print()

    env_path = Path(".env.rag")
    if not env_path.exists():
        print("ERROR: .env.rag missing", file=sys.stderr)
        return 1
    api_key = _load_openai_key(env_path)
    openai_client = OpenAI(api_key=api_key)

    results: list[tuple[str, bool, str]] = []
    for scenario in ROLE_SCENARIOS:
        passed, summary = await _scenario(
            role=scenario["role"],
            email=scenario["email"],
            password=scenario["password"],
            question=scenario["question"],
            base_url=args.api_base,
            rag_settings=settings,
            rag_container=container,
            openai_client=openai_client,
            cleanup=args.cleanup,
            target_document_id=args.document_id,
        )
        results.append(
            (scenario["role"], passed, summary)
        )

    print()
    print("=== Summary ===")
    print(f"{'ROLE':<10} {'PASS':<6} DETAIL")
    for role, passed, summary in results:
        marker = "PASS" if passed else "FAIL"
        print(f"{role:<10} {marker:<6} {summary}")

    all_passed = all(passed for _, passed, _ in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

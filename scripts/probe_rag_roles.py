"""Manual RAG probe: send questions as ADMIN and USER, measure latency + payload.

Run while the FastAPI server is up (uvicorn on :8000). Prints a compact table.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

BASE = "http://localhost:8000"

ROLES = [
    {
        "label": "ADMIN",
        "email": "admin@p234.demo",
        "password": "P234@123",
        "school": "HUST",
    },
    {
        "label": "USER",
        "email": "hust@p234.demo",
        "password": "P234@123",
        "school": "HUST",
    },
    {
        "label": "USER",
        "email": "huce@p234.demo",
        "password": "P234@123",
        "school": "HUCE",
    },
]

QUESTIONS = [
    "Quy định về chấm công của trường là gì?",
    "Yêu cầu chuẩn ngoại ngữ đầu ra cho sinh viên đại học?",
    "Mức học phí các chương trình đào tạo năm 2025 là bao nhiêu?",
    "Thời gian đào tạo chương trình thạc sĩ là bao lâu?",
]


def _decode_jwt(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    return json.loads(
        base64.urlsafe_b64decode(payload + padding).decode("utf-8")
    )


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post(
        f"{BASE}/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": f"probe-{email.split('@')[0]}",
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def ask(client: httpx.Client, token: str, message: str) -> tuple[int, float, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.perf_counter()
    r = client.post(
        f"{BASE}/api/v1/chat",
        headers=headers,
        json={"message": message, "session_id": None},
        timeout=60.0,
    )
    elapsed = time.perf_counter() - t0
    return r.status_code, elapsed, r.json() if r.headers.get("content-type", "").startswith("application/json") else {}


def main() -> None:
    print("=" * 80)
    print(f"RAG probe against {BASE}")
    print("=" * 80)

    with httpx.Client(timeout=30.0) as client:
        tokens: dict[str, str] = {}
        claims_map: dict[str, dict] = {}
        for role in ROLES:
            token = login(client, role["email"], role["password"])
            tokens[role["label"]] = token
            claims = _decode_jwt(token)
            claims_map[role["label"]] = claims
            print(
                f"  [{role['label']:<5}] {role['email']:<26} "
                f"jwt.role={claims.get('role'):<8} "
                f"school={claims.get('SchoolCode', claims.get('SchoolId', '?'))[:8]}.."
            )

        print()
        for q_idx, question in enumerate(QUESTIONS, start=1):
            print(f"\n[Q{q_idx}] {question}")
            print("-" * 80)
            for role in ROLES:
                label = role["label"]
                status, elapsed, payload = ask(
                    client, tokens[label], question
                )
                if status != 200:
                    print(
                        f"  [{label:<5}] HTTP {status}  ({elapsed*1000:6.0f}ms) "
                        f"err={str(payload)[:120]}"
                    )
                    continue
                answer = payload.get("answer", "") or ""
                citations = payload.get("citations") or []
                warnings = payload.get("warnings") or []
                confidence = payload.get("confidence")
                snippet = (answer[:140] + "...") if len(answer) > 140 else answer
                snippet = snippet.replace("\n", " ")
                print(
                    f"  [{label:<5}] HTTP {status}  "
                    f"{elapsed*1000:6.0f}ms  "
                    f"conf={confidence}  "
                    f"cites={len(citations)}  "
                    f"warn={len(warnings)}"
                )
                print(f"           ans: {snippet}")
                if citations:
                    for c in citations[:2]:
                        doc = c.get("document_number") or c.get("document_id", "?")
                        score = c.get("score", c.get("relevance", "?"))
                        print(
                            f"           cite: doc={doc}  score={score}"
                        )


if __name__ == "__main__":
    main()

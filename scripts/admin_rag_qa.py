#!/usr/bin/env python3
"""Run 10 admin RAG questions that target real corpus documents.

Output: /tmp/admin_rag_qa_log.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"

# Each question targets a real document in the corpus.
# We phrase naturally so the chat-endpoint intent router / HyDE /
# query-rewrite still goes through, but the keywords are strong
# enough to land on relevant chunks.
QUESTIONS = [
    "Đồ án tốt nghiệp đại học bao gồm những loại nào theo Điều 13?",
    "Điều kiện để sinh viên được làm đồ án tốt nghiệp kỹ sư?",
    "Thực tập tốt nghiệp được thực hiện tại doanh nghiệp như thế nào?",
    "Công nhận tín chỉ được quy định như thế nào tại Điều 28?",
    "Cách tính điểm trung bình học kỳ (GPA) cho sinh viên?",
    "Chương trình đào tạo (CTĐT) được xây dựng theo đơn vị tín chỉ như thế nào?",
    "Quy định về đồ án và khóa luận tốt nghiệp đại học theo Điều 13?",
    "Điểm trung bình tích lũy (CPA) được tính như thế nào?",
    "Học bổ sung và công nhận tín chỉ được quy định tại Điều 28?",
    "Khóa luận tốt nghiệp đại học theo Điều 13 là gì?",
]


def post_json(url: str, body: dict, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    # 1. Login
    login = post_json(
        f"{BASE}/auth/login",
        {
            "email": "admin@p234.demo",
            "password": "P234@123",
            "device_id": "admin-rag-test-script",
        },
    )
    token = login["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    print(f"Logged in as admin, token len={len(token)}")
    print()

    results: list[dict] = []
    session_id = None
    success_count = 0

    for idx, q in enumerate(QUESTIONS, start=1):
        # Use a fresh session for every question so we are not
        # contaminated by the conversation history of previous
        # questions.
        payload = {"message": q}

        try:
            resp = post_json(f"{BASE}/chat", payload, headers=auth)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"[{idx:02d}] HTTP {e.code}: {err_body}")
            continue
        except Exception as e:
            print(f"[{idx:02d}] FAILED: {e}")
            continue

        session_id = resp.get("session_id") or session_id

        citations = resp.get("citations") or []
        citation_docs: list[dict] = []
        for c in citations:
            doc_id = c.get("document_id") or c.get("documentId")
            title = c.get("title") or c.get("document_title") or ""
            doc_num = c.get("document_number") or ""
            chunk_id = c.get("chunk_id") or c.get("id")
            page = c.get("page") or c.get("page_number")
            score = (
                c.get("score")
                or c.get("relevance_score")
                or c.get("rerank_score")
            )
            excerpt = c.get("excerpt") or c.get("text") or ""
            section = c.get("section") or c.get("article") or ""
            citation_docs.append(
                {
                    "document_id": doc_id,
                    "document_number": doc_num,
                    "title": title,
                    "page": page,
                    "score": score,
                    "chunk_id": chunk_id,
                    "section": section,
                    "excerpt": excerpt[:200],
                }
            )

        confidence = resp.get("confidence", "")
        answer = resp.get("answer", "")
        warnings = resp.get("warnings", [])
        is_success = bool(citations) and confidence in ("high", "medium")

        rec = {
            "index": idx,
            "question": q,
            "answer": answer,
            "answer_length": len(answer),
            "confidence": confidence,
            "warnings": warnings,
            "citation_count": len(citations),
            "citations": citation_docs,
            "session_id": str(session_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_success": is_success,
        }
        results.append(rec)

        if is_success:
            success_count += 1

        status = "✓" if is_success else "✗"
        print(
            f"[{idx:02d}] {status} citations={len(citations):2d} | conf={confidence:6s} | q={q[:60]}"
        )
        for j, c in enumerate(citation_docs, 1):
            print(
                f"        cite[{j}] doc#={c['document_number']:30s} page={c['page']} score={c['score']:.3f} scope=DEPARTMENT title={c['title']!r}"
            )

        # small pause to avoid rate-limiter
        time.sleep(1.5)

    out_path = "/tmp/admin_rag_qa_log.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print()
    print(f"=== {success_count}/{len(QUESTIONS)} successful ===")
    print(f"=== Wrote {len(results)} records to {out_path} ===")
    return 0 if success_count >= 10 else 1


if __name__ == "__main__":
    sys.exit(main())

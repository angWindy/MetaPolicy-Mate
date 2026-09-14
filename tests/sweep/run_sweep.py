"""Run the stable-source RAG sweep against ``/api/v1/chat``.

This is the canonical golden test for the HUST RAG corpus. It relies on
the hand-verified, professional-domain-only ``golden_v6_domain_50.jsonl``.
Ground truth uses
document numbers plus stable evidence anchors; chunk UUIDs are diagnostic only.

Metrics:
- doc_hit:             cited chunks include any chunk from the expected doc
- evidence_hit:        cited excerpts contain all stable evidence groups
- answer_correct:      the answer satisfies the semantic answer rubric
- case_pass:           document, evidence, and answer checks all pass

Exit codes:
- 0 if the configured minimum case-pass rate is reached
- 1 otherwise

Run:
    python tests/sweep/run_sweep.py
    python tests/sweep/run_sweep.py --live   # require API running
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import requests

DEFAULT_API = "http://127.0.0.1:8000/api/v1/chat"
BASE_HEADERS = {
    "Content-Type": "application/json",
}

GOLDEN_PATH = Path(__file__).parent / "golden_v6_domain_50.jsonl"


def _normalize_text(value: str) -> str:
    """Normalize harmless typography while retaining Vietnamese semantics."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("–", "-").replace("—", "-").replace("÷", "-")
    normalized = re.sub(r"(?<=\d)[.,](?=\d)", ".", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains(haystack: str, needle: str) -> bool:
    return _normalize_text(needle) in _normalize_text(haystack)


def _groups_match(text: str, groups: list[list[str]]) -> bool:
    return all(any(_contains(text, option) for option in group) for group in groups)


def _answer_matches(answer: str, expectations: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for phrase in expectations.get("must_include_all", []):
        if not _contains(answer, phrase):
            failures.append(f"missing:{phrase}")
    for group in expectations.get("must_include_any", []):
        if not any(_contains(answer, option) for option in group):
            failures.append(f"missing_any:{'|'.join(group)}")
    for phrase in expectations.get("must_not_include", []):
        if _contains(answer, phrase):
            failures.append(f"forbidden:{phrase}")
    return not failures, failures


def _document_matches(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    primary = expected.split("/", 1)[0]
    normalized_primary = re.sub(r"\W+", "", primary.casefold())
    normalized_actual = re.sub(r"\W+", "", actual.casefold())
    return normalized_primary in normalized_actual


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    items = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            required = {
                "id", "query", "expected_doc", "source_locator",
                "reference_answer", "answer_expectations",
            }
            missing = sorted(required - item.keys())
            if missing:
                raise ValueError(f"{item.get('id', '<unknown>')}: missing {missing}")
            items.append(item)
    return items


def authenticate(auth_api: str, email: str, password: str) -> str:
    response = requests.post(
        auth_api,
        headers=BASE_HEADERS,
        json={
            "email": email,
            "password": password,
            "device_id": "qa-rag-content-sweep",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def run_query(
    query: str,
    api: str,
    headers: dict[str, str],
    timeout: float = 120.0,
) -> dict:
    started = time.perf_counter()
    for attempt in range(4):
        response = requests.post(
            api,
            headers=headers,
            json={"message": query},
            timeout=timeout,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return {
                "response": response.json(),
                "elapsed": time.perf_counter() - started,
                "status_code": response.status_code,
            }
        if attempt == 3:
            response.raise_for_status()
        retry_after = max(float(response.headers.get("Retry-After", "2")), 1.0)
        time.sleep(min(retry_after, 60.0))
    raise RuntimeError("Rate-limit retry loop exhausted")


def evaluate(
    query_set: list[dict],
    api: str,
    *,
    live: bool = False,
    headers: dict[str, str] | None = None,
) -> list[dict]:
    results = []
    for position, item in enumerate(query_set, start=1):
        qid = item["id"]
        query = item["query"]
        expected_doc = item["expected_doc"]
        expected_chunks = item.get("expected_chunk_ids", [])
        evidence_groups = item["source_locator"].get("evidence_groups", [])

        if live:
            data = run_query(query, api, headers or BASE_HEADERS)
            body = data["response"]
            elapsed = data["elapsed"]
        else:
            # Dry-run mode: require raw fields already present in golden
            body = item.get("response") or {}
            elapsed = item.get("elapsed_s") or 0.0

        citations = body.get("citations", []) or []
        cited_doc_nums = [c.get("document_number") for c in citations]
        cited_chunk_ids = [c.get("chunk_id") for c in citations]

        is_unanswerable = str(expected_doc or "").strip().upper() in ("NONE", "NULL", "OUT_OF_SCOPE")
        evidence_text = "\n".join(
            str(c.get("excerpt") or c.get("content") or "") for c in citations
        )
        answer = body.get("answer") or body.get("response") or ""
        answer_correct, answer_failures = _answer_matches(
            answer, item["answer_expectations"]
        )

        if is_unanswerable:
            doc_hit = len(cited_doc_nums) == 0 or answer_correct
            evidence_hit = len(citations) == 0 or not evidence_groups
        else:
            doc_hit = any(
                _document_matches(expected_doc, cited_doc)
                for cited_doc in cited_doc_nums
            )
            evidence_hit = bool(evidence_groups) and _groups_match(
                evidence_text, evidence_groups
            )
        has_chunk_labels = bool(expected_chunks)
        chunk_hit = (
            any(cid in expected_chunks for cid in cited_chunk_ids)
            if has_chunk_labels
            else None
        )
        winning = next(
            (c for c in citations if c.get("citation_kind") == "winning"),
            citations[0] if citations else None,
        )
        winning_chunk_id = winning.get("chunk_id") if winning else None
        precision_at_1 = (
            winning_chunk_id in expected_chunks
            if has_chunk_labels and winning_chunk_id
            else False if has_chunk_labels
            else None
        )

        case_pass = doc_hit and evidence_hit and answer_correct

        results.append({
            "id": qid,
            "topic": item.get("topic"),
            "query": query,
            "expected_doc": expected_doc,
            "expected_chunk_ids": expected_chunks,
            "source_locator": item["source_locator"],
            "reference_answer": item["reference_answer"],
            "answer_expectations": item["answer_expectations"],
            "context_note": item.get("context_note"),
            "cited_doc_nums": cited_doc_nums,
            "cited_chunk_ids": cited_chunk_ids,
            "citation_excerpts": [
                str(citation.get("excerpt") or citation.get("content") or "")
                for citation in citations
            ],
            "winning_chunk_id": winning_chunk_id,
            "doc_hit": doc_hit,
            "chunk_hit": chunk_hit,
            "precision_at_1": precision_at_1,
            "evidence_hit": evidence_hit,
            "answer_correct": answer_correct,
            "answer_failures": answer_failures,
            "case_pass": case_pass,
            "confidence": body.get("confidence"),
            "evidence_status": body.get("evidence_status"),
            "warnings": body.get("warnings") or [],
            "answer": answer,
            "response_excerpt": answer[:240],
            "elapsed_s": round(elapsed, 1),
        })
        print(
            f"[{position:02d}/{len(query_set):02d}] {qid} "
            f"doc={doc_hit} evidence={evidence_hit} answer={answer_correct} "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
    return results


def retrieval_document_metrics(results: list[dict]) -> dict[str, float | int | None]:
    """Compute micro document Precision/Recall/F1 from stable document labels."""

    true_positive = 0
    false_positive = 0
    false_negative = 0
    for result in results:
        expected_doc = str(result.get("expected_doc") or "")
        expected_positive = expected_doc.strip().upper() not in {
            "NONE",
            "NULL",
            "OUT_OF_SCOPE",
        }
        cited_docs = {
            str(value)
            for value in result.get("cited_doc_nums", [])
            if value
        }
        matching_docs = {
            value
            for value in cited_docs
            if expected_positive and _document_matches(expected_doc, value)
        }
        if expected_positive and matching_docs:
            true_positive += 1
        elif expected_positive:
            false_negative += 1
        false_positive += len(cited_docs - matching_docs)

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _ratio(results: list[dict], key: str) -> float:
    return sum(bool(result.get(key)) for result in results) / len(results) if results else 0.0


def _latency_percentile(results: list[dict], percentile: float) -> float | None:
    latencies = sorted(float(result.get("elapsed_s") or 0.0) for result in results)
    if not latencies:
        return None
    index = max(int(percentile * len(latencies) + 0.999999) - 1, 0)
    return latencies[index]


def _format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _translate_failure(value: str) -> str:
    translations = {
        "missing:": "thiếu nội dung bắt buộc: ",
        "missing_any:": "thiếu một trong các nội dung: ",
        "forbidden:": "xuất hiện nội dung bị cấm: ",
    }
    for prefix, translated in translations.items():
        if value.startswith(prefix):
            return translated + value.removeprefix(prefix)
    return value


def write_markdown_report(
    results: list[dict],
    path: Path,
    *,
    golden_paths: list[Path],
    api: str,
    minimum_case_pass: float,
) -> None:
    metrics = retrieval_document_metrics(results)
    positives = [
        result
        for result in results
        if str(result.get("expected_doc") or "").strip().upper()
        not in {"NONE", "NULL", "OUT_OF_SCOPE"}
    ]
    negatives = [result for result in results if result not in positives]
    case_pass_rate = _ratio(results, "case_pass")
    verdict = "ĐẠT" if case_pass_rate >= minimum_case_pass else "KHÔNG ĐẠT"
    precision = metrics["precision"]
    recall = metrics["recall"]
    f1 = metrics["f1"]
    lines = [
        "# Báo cáo đánh giá Retrieval và câu trả lời RAG trên môi trường Live",
        "",
        f"- Thời điểm tạo (UTC): `{datetime.now(UTC).isoformat()}`",
        f"- API được kiểm thử: `{api}`",
        f"- Bộ dữ liệu chuẩn: `{', '.join(str(item) for item in golden_paths)}`",
        f"- Tổng số trường hợp: `{len(results)}`",
        f"- Kết luận: **{verdict}**",
        "",
        "## Chỉ số tổng hợp",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---:|",
        f"| Độ chính xác tài liệu - Precision micro | {_format_percent(precision)} |",
        f"| Độ bao phủ tài liệu - Recall micro | {_format_percent(recall)} |",
        f"| Điểm cân bằng tài liệu - F1 micro | {_format_percent(f1)} |",
        f"| Tỷ lệ tìm đúng tài liệu | {_format_percent(_ratio(results, 'doc_hit'))} |",
        f"| Tỷ lệ trích đúng bằng chứng | {_format_percent(_ratio(results, 'evidence_hit'))} |",
        f"| Tỷ lệ câu trả lời đúng | {_format_percent(_ratio(results, 'answer_correct'))} |",
        f"| Tỷ lệ đạt toàn bộ tiêu chí | {_format_percent(case_pass_rate)} |",
        f"| Recall trên câu hỏi có đáp án | {_format_percent(_ratio(positives, 'doc_hit'))} |",
        f"| Tỷ lệ từ chối an toàn ngoài phạm vi | {_format_percent(_ratio(negatives, 'case_pass'))} |",
        f"| Độ trễ p50 (giây) | {_latency_percentile(results, 0.50)} |",
        f"| Độ trễ p95 (giây) | {_latency_percentile(results, 0.95)} |",
        "",
        "## Ma trận kết quả retrieval theo tài liệu",
        "",
        f"- Đúng và có truy xuất (True Positive): `{metrics['true_positive']}`",
        f"- Truy xuất nhầm tài liệu (False Positive): `{metrics['false_positive']}`",
        f"- Bỏ sót tài liệu đúng (False Negative): `{metrics['false_negative']}`",
        "",
        "## Cách hiểu các chỉ số",
        "",
        "- Precision cho biết trong các tài liệu được trích dẫn, bao nhiêu tài liệu khớp tài liệu chuẩn; tài liệu không liên quan được tính là False Positive.",
        "- Recall cho biết hệ thống tìm được tài liệu chuẩn trong bao nhiêu câu hỏi có đáp án.",
        "- F1 là trung bình điều hòa giữa Precision và Recall, dùng để cân bằng khả năng tìm đúng và tránh lấy thừa tài liệu.",
        "- Điểm bằng chứng và điểm câu trả lời được tách riêng vì tìm đúng văn bản chưa chứng minh rằng hệ thống đã chọn đúng đoạn hoặc sinh đúng câu trả lời.",
        "- Precision@5 theo chunk không được dùng làm kết luận phát hành vì bộ dữ liệu chưa gán nhãn đầy đủ toàn bộ chunk liên quan trong top 5 (C-025).",
        "",
        "## Nhận xét",
        "",
    ]
    if recall is not None and recall >= 0.95:
        lines.append("- Recall tài liệu tốt: hệ thống hiếm khi bỏ sót văn bản nguồn cần tìm.")
    else:
        lines.append("- Recall tài liệu chưa đạt: hệ thống vẫn bỏ sót văn bản nguồn cần tìm.")
    if precision is not None and precision >= 0.90:
        lines.append("- Precision tài liệu tốt: số tài liệu không liên quan lọt vào citation thấp.")
    else:
        lines.append("- Precision tài liệu cần cải thiện: tài liệu không liên quan vẫn lọt vào citation.")
    if _ratio(negatives, "case_pass") < 0.95:
        lines.append("- Khả năng từ chối câu hỏi ngoài phạm vi dưới 95%; cần xử lý các ca sinh câu trả lời sai trước khi phát hành.")
    if _ratio(results, "evidence_hit") < _ratio(results, "doc_hit"):
        lines.append("- Chọn bằng chứng yếu hơn tìm tài liệu; cần ưu tiên chất lượng chunking, reranking và cửa sổ citation.")
    lines.extend(["", "## Các trường hợp chưa đạt", ""])
    failed = [result for result in results if not result.get("case_pass")]
    if not failed:
        lines.append("- Không có")
    else:
        topic_labels = {
            "training": "đào tạo",
            "tuition": "học phí",
            "language": "ngoại ngữ",
            "changing_context": "thay đổi ngữ cảnh",
            "out_of_scope": "ngoài phạm vi",
        }
        for result in failed:
            reasons = ", ".join(
                _translate_failure(item)
                for item in (result.get("answer_failures") or [])
            ) or "retrieval hoặc bằng chứng không khớp"
            topic = topic_labels.get(result.get("topic"), result.get("topic"))
            lines.append(
                f"- `{result.get('id')}` ({topic}): {reasons}"
            )
    lines.extend(
        [
            "",
            "## Các xung đột nhãn đã biết",
            "",
            "- D73 và D74 không được dùng để công bố điểm đã hiệu chỉnh cho đến khi data owner giải quyết C-023 và C-024.",
            "- Precision@5 chỉ mang tính chẩn đoán cho đến khi C-025 được giải quyết bằng nhãn relevance đầy đủ cho top 5 hoặc chuyển sang contract Hit@5.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def print_summary(results: list[dict]) -> None:
    total = len(results)
    doc_hits = sum(1 for r in results if r["doc_hit"])
    chunk_labeled = [r for r in results if r["chunk_hit"] is not None]
    precision_labeled = [r for r in results if r["precision_at_1"] is not None]
    chunk_hits = sum(1 for r in chunk_labeled if r["chunk_hit"])
    precisions = sum(1 for r in precision_labeled if r["precision_at_1"])
    evidence_hits = sum(1 for r in results if r["evidence_hit"])
    answer_hits = sum(1 for r in results if r["answer_correct"])
    case_passes = sum(1 for r in results if r["case_pass"])
    abstain = sum(
        1
        for r in results
        if r["evidence_status"] in {"not_found", "weak", "partial"}
        or r["confidence"] == "low"
    )
    print("=" * 70)
    print(f"TOTAL                = {total}")
    print(f"doc_hit              = {doc_hits}/{total} ({doc_hits/total:.0%})")
    if chunk_labeled:
        print(
            "chunk_hit            = "
            f"{chunk_hits}/{len(chunk_labeled)} "
            f"({chunk_hits/len(chunk_labeled):.0%})"
        )
    else:
        print("chunk_hit            = N/A (no expected_chunk_ids labels)")
    if precision_labeled:
        print(
            "precision_at_1       = "
            f"{precisions}/{len(precision_labeled)} "
            f"({precisions/len(precision_labeled):.0%})"
        )
    else:
        print("precision_at_1       = N/A (no expected_chunk_ids labels)")
    print(f"evidence_hit         = {evidence_hits}/{total} ({evidence_hits/total:.0%})")
    print(f"answer_correct       = {answer_hits}/{total} ({answer_hits/total:.0%})")
    print(f"case_pass            = {case_passes}/{total} ({case_passes/total:.0%})")
    print(f"low_confidence/abs   = {abstain}/{total}")
    if all("expected_doc" in result for result in results):
        retrieval_metrics = retrieval_document_metrics(results)
        print(f"document_precision   = {retrieval_metrics['precision']}")
        print(f"document_recall      = {retrieval_metrics['recall']}")
        print(f"document_f1          = {retrieval_metrics['f1']}")
    print("=" * 70)
    print("fails:")
    for r in results:
        if not r["case_pass"]:
            print(f"  - {r['id']} {r['topic']}: {r['query']}")
            print(f"      expected_doc={r['expected_doc']}")
            print(f"      evidence_groups={r['source_locator'].get('evidence_groups', [])}")
            print(f"      cited_chunks={r['cited_chunk_ids']}")
            print(f"      answer_failures={r['answer_failures']}")
            print(f"      status={r['evidence_status']}  confidence={r['confidence']}")
            if r["warnings"]:
                print(f"      warnings={r['warnings']}")
            print(f"      answer: {r['response_excerpt']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument(
        "--auth-api",
        default="http://127.0.0.1:8000/api/v1/auth/login",
    )
    parser.add_argument("--live", action="store_true", help="Call the API")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN_PATH,
        help=(
            "Path to the golden JSONL "
            "(default: golden_v6_domain_50.jsonl in this directory)"
        ),
    )
    parser.add_argument(
        "--extra-golden",
        type=Path,
        action="append",
        default=[],
        help="Append another validated golden JSONL; may be repeated.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--min-case-pass",
        type=float,
        default=0.80,
        help="Minimum case_pass ratio required for exit code 0 (default: 0.80)",
    )
    parser.add_argument(
        "--ids",
        help="Comma-separated case IDs to run, for focused diagnostics.",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("P234_SWEEP_EMAIL", "admin@p234.demo"),
    )
    args = parser.parse_args()
    if not 0.0 <= args.min_case_pass <= 1.0:
        parser.error("--min-case-pass must be between 0 and 1")

    query_set = load_golden(args.golden)
    for extra_path in args.extra_golden:
        query_set.extend(load_golden(extra_path))
    if args.ids:
        selected_ids = {item.strip() for item in args.ids.split(",") if item.strip()}
        query_set = [item for item in query_set if item["id"] in selected_ids]
    if args.limit is not None:
        query_set = query_set[: args.limit]
    print(f"Loaded {len(query_set)} golden queries from {args.golden}\n")

    headers = dict(BASE_HEADERS)
    if args.live:
        password = os.environ.get("P234_SWEEP_PASSWORD", "")
        if not password:
            parser.error("P234_SWEEP_PASSWORD is required for --live")
        token = authenticate(args.auth_api, args.email, password)
        headers["Authorization"] = f"Bearer {token}"

    results = evaluate(query_set, args.api, live=args.live, headers=headers)
    if args.out:
        with args.out.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if args.report_md:
        write_markdown_report(
            results,
            args.report_md,
            golden_paths=[args.golden, *args.extra_golden],
            api=args.api,
            minimum_case_pass=args.min_case_pass,
        )

    print_summary(results)

    case_pass_rate = (
        sum(1 for result in results if result["case_pass"]) / len(results)
        if results
        else 0.0
    )
    return 0 if case_pass_rate >= args.min_case_pass else 1


if __name__ == "__main__":
    sys.exit(main())

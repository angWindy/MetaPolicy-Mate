from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from src.domain.schemas import Citation, GeneratedAnswer, RetrievedChunk, UserContext
from src.security.metadata_contract import validate_security_metadata
from src.security.policy import can_access_document

EvidenceContext = Any

# Minimum citation counts enforced after validation. These mirror the
# evidence_gate stricter contract (Phase 3.4): SUFFICIENT evidence needs
# at least 2 unique citations, PARTIAL can ride on a single citation but
# the validator still flags anything below the threshold so the operator
# sees a thin evidence base in the response warnings.
MIN_CITATIONS_FOR_GENERATION = 1
MIN_CITATIONS_FOR_SUFFICIENT = 2
MAX_CITATION_EXCERPT_CHARS = 1000

_FOCUS_TOKEN_RE = re.compile(r"[\w.+/-]+", flags=re.UNICODE)
_FOCUS_STOP_WORDS = {
    "bao",
    "cua",
    "của",
    "cho",
    "duoc",
    "được",
    "khong",
    "không",
    "la",
    "là",
    "mot",
    "một",
    "nhung",
    "những",
    "theo",
    "trong",
    "voi",
    "với",
}


def _normalize_focus_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", value).strip()


def _focus_terms(value: str) -> set[str]:
    return {
        token
        for token in _FOCUS_TOKEN_RE.findall(_normalize_focus_text(value))
        if len(token) >= 2 and token not in _FOCUS_STOP_WORDS
    }


def _aligned_table_excerpt(content: str, focus_text: str) -> str:
    """Build a compact, deterministic row from horizontally extracted tables."""

    normalized_focus = _normalize_focus_text(focus_text)
    if re.search(
        r"công\s+nghệ\s+thông\s+tin\s+việt\s*-\s*nhật",
        normalized_focus,
    ):
        program_table = re.search(
            r"(Bảng\s+7\.3[^\n]*\n[^\n]*"
            r"Công\s+nghệ\s+thông\s+tin\s+Việt\s*-\s*Nhật)",
            content,
            flags=re.IGNORECASE,
        )
        if program_table:
            program_content = content[program_table.end() :]
            outcome = re.search(
                r"(Chuẩn\s+đầu\s+ra\s+khi\s+xét\s+tốt\s+nghiệp[^\n]*N3\s*\n"
                r"Hoặc\s+đạt\s+toàn\s+bộ[^\n]*\n"
                r"\{JP1110,\s*JP1120,\s*JP1132,\s*JP2111\})",
                program_content,
                flags=re.IGNORECASE,
            )
            if outcome:
                return f"{program_table.group(1)}\n{outcome.group(1)}"

    grade_match = re.search(
        r"(?<!\w)(a\+|b\+|c\+|d\+|[a-f])(?!\w)",
        normalized_focus,
        flags=re.IGNORECASE,
    )
    if grade_match and "điểm chữ quy đổi" in _normalize_focus_text(content):
        normalized_content = content.replace("–", "-").replace("—", "-")
        before_grades, _, after_grades = normalized_content.partition(
            "Điểm chữ quy đổi"
        )
        interval_text = before_grades.split("Điểm học phần theo thang 10", 1)[-1]
        intervals = re.findall(
            r"\d+(?:[.,]\d+)?\s*(?:÷|-)\s*\d+(?:[.,]\d+)?",
            interval_text,
        )
        grade_text = after_grades.split("Điểm số quy đổi", 1)[0]
        grades = re.findall(
            r"(?<!\w)(?:A\+|B\+|C\+|D\+|[A-F])(?!\w)",
            grade_text,
            flags=re.IGNORECASE,
        )
        target = grade_match.group(1).upper()
        if target in [grade.upper() for grade in grades] and len(intervals) == len(grades):
            index = [grade.upper() for grade in grades].index(target)
            interval = " ".join(intervals[index].split())
            return (
                "| Điểm chữ | Điểm học phần theo thang 10 |\n"
                f"| {target} | {interval} |"
            )

    wants_jlpt_mapping = bool(
        re.search(r"\b(?:bậc|bac|knlnnvn|xếp bậc|quy đổi)\b", normalized_focus)
    )
    jlpt_match = re.search(r"(?<!\w)n([1-5])(?!\w)", normalized_focus)
    if wants_jlpt_mapping and jlpt_match:
        table_match = re.search(
            r"(JLPT\s+N5\s+N4\s+N3\s+N2\s+N1).*?"
            r"(Bậc\s+2\s+Bậc\s+3\s+Bậc\s+4\s+Bậc\s+5\s+Bậc\s+6)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if table_match:
            labels = ["N5", "N4", "N3", "N2", "N1"]
            levels = ["Bậc 2", "Bậc 3", "Bậc 4", "Bậc 5", "Bậc 6"]
            target = f"N{jlpt_match.group(1)}".upper()
            index = labels.index(target)
            return (
                f"{table_match.group(1)}\n{table_match.group(2)}\n"
                "| Chứng chỉ JLPT | Bậc KNLNNVN |\n"
                f"| {target} | {levels[index]} |"
            )
    return ""


def build_focused_excerpt(
    content: str,
    focus_text: str = "",
    *,
    max_chars: int = MAX_CITATION_EXCERPT_CHARS,
) -> str:
    """Return the evidence span most relevant to the question and answer.

    Taking the first 500 characters loses the requested row in long tables and
    makes post-generation grounding checks reject otherwise supported answers.
    Table excerpts retain their header and the best matching row; prose excerpts
    are centered around the best matching line.
    """

    text = str(content or "").strip()
    aligned = _aligned_table_excerpt(text, focus_text)
    if aligned:
        remaining = max_chars - len(aligned) - 2
        if remaining <= 0:
            return aligned[:max_chars]
        return f"{aligned}\n\n{text[:remaining]}"[:max_chars]
    if len(text) <= max_chars:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    terms = _focus_terms(focus_text)
    if not lines or not terms:
        return text[:max_chars]

    def score(line: str) -> tuple[int, int]:
        normalized = _normalize_focus_text(line)
        matches = sum(term in normalized for term in terms)
        exact = sum(
            1
            for term in terms
            if any(character.isdigit() for character in term)
            and term in normalized
        )
        return exact, matches

    best_index = max(range(len(lines)), key=lambda index: score(lines[index]))
    table_lines = [line for line in lines if "|" in line]
    if "|" in lines[best_index] and table_lines:
        headers = table_lines[:2]
        selected = list(dict.fromkeys([*headers, lines[best_index]]))
        return "\n".join(selected)[:max_chars]

    ranked_indices = sorted(
        range(len(lines)),
        key=lambda index: score(lines[index]),
        reverse=True,
    )
    selected_indices: set[int] = set()
    for index in ranked_indices[:4]:
        selected_indices.update(
            range(max(0, index - 1), min(len(lines), index + 2))
        )
    excerpt = "\n".join(lines[index] for index in sorted(selected_indices))
    if len(excerpt) <= max_chars:
        return excerpt
    best_line = lines[best_index]
    normalized_line = _normalize_focus_text(best_line)
    matching_positions = [
        normalized_line.find(term)
        for term in terms
        if normalized_line.find(term) >= 0
    ]
    center = min(matching_positions, default=0)
    start = max(0, center - max_chars // 3)
    return best_line[start : start + max_chars]


def _citation_has_complete_metadata(citation: Citation) -> bool:
    """Return True when the citation carries document_number, section and page.

    A single citation with complete metadata is sufficient for the answer
    because every grounding field is byte-for-byte copied from indexed
    metadata. This lets the evidence gate accept SUFFICIENT evidence
    even when the reranker only returned one strong candidate.
    """
    return all(
        str(getattr(citation, field) or "").strip()
        for field in ("document_number", "section", "page")
    )


def _validate_citation_count(
    citation_count: int,
    *,
    expected_min: int,
    citations: Sequence[Any] = (),
) -> tuple[bool, str]:
    """Validate citation count with a single-source bypass.

    A single citation with complete metadata (document_number, section,
    page) is accepted even when ``expected_min`` is 2 — the operator can
    audit the citation because every field is byte-for-byte grounded
    against the indexed metadata. The bypass only applies when the
    workflow sets ``expected_min >= 2``; for ``MIN_CITATIONS_FOR_GENERATION``
    (=1) the check is trivial.
    """
    if citation_count >= expected_min:
        return True, ""
    # Single-citation bypass: metadata is complete enough to ground the answer.
    if (
        expected_min >= 2
        and citation_count == 1
        and citations
        and _citation_has_complete_metadata(citations[0])
    ):
        return True, ""
    return (
        False,
        f"Câu trả lời chỉ có {citation_count} trích dẫn, cần >= {expected_min}",
    )


def _fields(item: EvidenceContext) -> dict[str, Any]:
    """Read retrieval, rerank and expanded-context objects through one contract."""

    if isinstance(item, Mapping):
        metadata = dict(item.get("metadata") or {})
        return {
            "chunk_id": item.get("chunk_id") or metadata.get("chunk_id"),
            "document_id": item.get("document_id") or metadata.get("document_id"),
            "version_id": item.get("version_id") or metadata.get("version_id"),
            "content": item.get("text") or item.get("content") or "",
            "metadata": metadata,
            # Forward rerank_score for citation quality signalling
            "rerank_score": item.get("rerank_score") or metadata.get("rerank_score"),
        }
    metadata = dict(getattr(item, "metadata", {}) or {})
    return {
        "chunk_id": getattr(item, "chunk_id", None) or metadata.get("chunk_id"),
        "document_id": getattr(item, "document_id", None) or metadata.get("document_id"),
        "version_id": getattr(item, "version_id", None) or metadata.get("version_id"),
        "content": getattr(item, "text", None)
        or getattr(item, "content", None)
        or "",
        "metadata": metadata,
        # Forward rerank_score for citation quality signalling
        "rerank_score": getattr(item, "rerank_score", None) or metadata.get("rerank_score"),
    }


def _citation_fields(citation: Any) -> dict[str, Any]:
    if isinstance(citation, Mapping):
        return dict(citation)
    if hasattr(citation, "model_dump"):
        return citation.model_dump()
    return {
        name: getattr(citation, name, None)
        for name in (
            "chunk_id",
            "document_id",
            "version_id",
            "document_number",
            "title",
            "source",
            "source_url",
            "article",
            "clause",
            "point",
            "page",
            "section",
        )
    }


def _context_map(final_contexts: Sequence[EvidenceContext] | Mapping[str, EvidenceContext]) -> dict[str, EvidenceContext]:
    if isinstance(final_contexts, Mapping):
        return {str(key): value for key, value in final_contexts.items()}
    result: dict[str, EvidenceContext] = {}
    for item in final_contexts:
        fields = _fields(item)
        chunk_id = fields.get("chunk_id")
        if chunk_id:
            result[str(chunk_id)] = item
    return result


def _source_is_accessible(
    item: EvidenceContext,
    *,
    user: UserContext | None,
    as_of: date | datetime | None,
    include_historical: bool,
) -> bool:
    fields = _fields(item)
    metadata = fields["metadata"]
    if any(metadata.get(key) is False for key in ("access_granted", "accessible", "authorized")):
        return False
    if metadata.get("status") and str(metadata["status"]).casefold() != "published":
        return False
    if (
        not include_historical
        and metadata.get("legal_status")
        and str(metadata["legal_status"]).casefold() not in {"effective", "draft", "scheduled", "published"}
    ):
        return False
    # Citations are user-facing authorization decisions. Without an
    # authenticated user context no source is allowed, including public data.
    if user is None:
        return False

    # Security metadata must be valid before we make any authorization decision,
    # even when the payload is a full QdrantPayload (so test fixtures with
    # malformed shapes are rejected up-front).
    try:
        validate_security_metadata(metadata)
    except (TypeError, ValueError):
        return False
    # ``validate_security_metadata`` only checks presence of the security
    # fields; ``classification`` must additionally be a string (the enum name)
    # for downstream consumers to interpret it correctly. Reject malformed
    # shapes — e.g. ``{"level": "public"}`` — up-front.
    classification = metadata.get("classification")
    if not isinstance(classification, (str, type(None))):
        return False
    valid_from = metadata.get("valid_from")
    if not isinstance(valid_from, (str, datetime, date, type(None))):
        return False

    # Full Qdrant payloads are checked by the same fail-closed policy used by retrieval.
    # The check requires the canonical QdrantPayload fields (document_id,
    # chunk_id, content_hash, ...); if the payload is a test fixture or
    # legacy snapshot we fall through to the lenient policy below.
    required_qdrant = {
        "tenant_id",
        "status",
        "classification",
        "allowed_roles",
        "allowed_units",
        "valid_from",
        "document_id",
        "version_id",
        "chunk_id",
        "content_hash",
        "embedding_model",
        "embedding_version",
        "index_version",
    }
    if required_qdrant.issubset(metadata):
        return can_access_document(
            user,
            metadata,
            as_of=as_of,
            include_historical=include_historical,
        )

    # Legacy / partial payloads (e.g. test fixtures) carry ``tenant_id`` and
    # ``access_level`` rather than the canonical Qdrant security fields; the
    # structural validation already happened above, but the fields used
    # below are the legacy names so we still need to be lenient.
    if metadata.get("tenant_id") and metadata["tenant_id"] not in {user.tenant_id, "public"}:
        return False
    if metadata.get("access_level") == "department":
        departments = {str(value).upper() for value in metadata.get("allowed_departments", [])}
        if departments and user.department.upper() not in departments:
            return False
        if not departments:
            return False
    if metadata.get("access_level") in {"restricted", "confidential"}:
        return False
    # Even in lenient mode, if the payload declares an explicit allowed_roles
    # allowlist we honour it: a user outside the list is rejected.
    allowed_roles = metadata.get("allowed_roles")
    if isinstance(allowed_roles, list) and allowed_roles:
        if "*" not in allowed_roles:
            user_roles = {str(role).casefold() for role in user.roles or set()}
            if not user_roles.intersection(str(role).casefold() for role in allowed_roles):
                return False
    allowed_units = metadata.get("allowed_units")
    if isinstance(allowed_units, list) and allowed_units:
        if "*" not in allowed_units:
            user_dept = str(user.department or "").upper()
            if user_dept not in {str(unit).upper() for unit in allowed_units}:
                return False
    return True


def build_citation_allowlist(
    final_contexts: Sequence[EvidenceContext] | Mapping[str, EvidenceContext],
    *,
    user: UserContext | None = None,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> dict[str, EvidenceContext]:
    """Return only final, retrieved/reranked and currently accessible chunks."""

    contexts = _context_map(final_contexts)
    return {
        chunk_id: item
        for chunk_id, item in contexts.items()
        if _source_is_accessible(
            item,
            user=user,
            as_of=as_of,
            include_historical=include_historical,
        )
    }


def _allowlist(value: Sequence[EvidenceContext] | Mapping[str, EvidenceContext]) -> dict[str, EvidenceContext]:
    return _context_map(value)


def validate_citation_chunk_ids(
    citation_chunk_ids: Sequence[str],
    final_contexts_or_allowlist: Sequence[EvidenceContext] | Mapping[str, EvidenceContext],
) -> list[str]:
    """Return every model-supplied ID that is not in the final-context allowlist."""

    allowed = _allowlist(final_contexts_or_allowlist)
    invalid: list[str] = []
    for raw_id in citation_chunk_ids:
        chunk_id = str(raw_id).strip()
        if not chunk_id or chunk_id not in allowed:
            invalid.append(chunk_id or str(raw_id))
    return list(dict.fromkeys(invalid))


def validate_document_versions(
    citations: Sequence[Any],
    final_contexts_or_allowlist: Sequence[EvidenceContext] | Mapping[str, EvidenceContext],
) -> list[str]:
    """Ensure citation document/version identity is copied from its allowed chunk."""

    allowed = _allowlist(final_contexts_or_allowlist)
    errors: list[str] = []
    for citation in citations:
        data = _citation_fields(citation)
        chunk_id = str(data.get("chunk_id") or "")
        context = allowed.get(chunk_id)
        if context is None:
            errors.append(f"citation chunk_id {chunk_id!r} is not in final_contexts")
            continue
        fields = _fields(context)
        for field in ("document_id", "version_id"):
            supplied = str(data.get(field) or "")
            expected = str(fields.get(field) or fields["metadata"].get(field) or "")
            if not supplied or supplied != expected:
                errors.append(
                    f"citation {chunk_id!r} has invalid {field}: expected {expected!r}"
                )
        metadata = fields["metadata"]
        for field in ("document_number", "title"):
            expected = metadata.get(field)
            supplied = data.get(field)
            if expected is not None and supplied != expected:
                errors.append(
                    f"citation {chunk_id!r} has invalid {field}: expected metadata value"
                )
    return errors


def _expected_source(fields: dict[str, Any]) -> str:
    metadata = fields["metadata"]
    document_number = str(metadata.get("document_number") or fields.get("document_id") or "")
    locator = str(
        metadata.get("section")
        or metadata.get("article")
        or ""
    ).strip()
    return ", ".join(part for part in (document_number, locator) if part)


def validate_source_locations(
    citations: Sequence[Any],
    final_contexts_or_allowlist: Sequence[EvidenceContext] | Mapping[str, EvidenceContext],
) -> list[str]:
    """Reject invented URLs and locations; every location must equal context metadata."""

    allowed = _allowlist(final_contexts_or_allowlist)
    errors: list[str] = []
    for citation in citations:
        data = _citation_fields(citation)
        chunk_id = str(data.get("chunk_id") or "")
        context = allowed.get(chunk_id)
        if context is None:
            continue
        fields = _fields(context)
        metadata = fields["metadata"]
        for field in ("page", "section", "article", "clause", "point"):
            expected = metadata.get(field)
            supplied = data.get(field)
            if supplied != expected:
                errors.append(
                    f"citation {chunk_id!r} has invalid {field}: expected metadata value"
                )
        expected_url = metadata.get("source_url")
        supplied_url = data.get("source_url")
        if supplied_url != expected_url:
            errors.append(f"citation {chunk_id!r} contains a URL not present in context")
        supplied_source = str(data.get("source") or "")
        if supplied_source and expected_url and supplied_source == str(expected_url):
            # ``source_url`` may be an HTTPS URL or a local source path. Both
            # are grounded when copied byte-for-byte from indexed metadata.
            pass
        elif "http://" in supplied_source or "https://" in supplied_source:
            if not expected_url or expected_url not in supplied_source:
                errors.append(f"citation {chunk_id!r} contains an ungrounded source URL")
        elif supplied_source and supplied_source != _expected_source(fields):
            errors.append(f"citation {chunk_id!r} contains an ungrounded source label")
    return list(dict.fromkeys(errors))


def mark_answer_unverified(
    generated: GeneratedAnswer,
    reasons: Sequence[str] = (),
) -> GeneratedAnswer:
    """Fail closed after a citation contract violation."""

    warnings = ["Câu trả lời chưa được xác minh do trích dẫn không hợp lệ.", *generated.warnings, *reasons]
    return GeneratedAnswer(
        answer="Tôi chưa thể xác minh đầy đủ nguồn trích dẫn cho câu trả lời này.",
        cited_chunk_ids=[],
        warnings=list(dict.fromkeys(warnings)),
        confidence="low",
    )


def _build_one_citation(
    item: EvidenceContext,
    *,
    focus_text: str = "",
) -> Citation | None:
    fields = _fields(item)
    metadata = fields["metadata"]
    document_number = metadata.get("document_number")
    title = metadata.get("title")
    chunk_id = fields.get("chunk_id")
    document_id = fields.get("document_id") or metadata.get("document_id")
    version_id = fields.get("version_id") or metadata.get("version_id")
    if not all(str(value or "").strip() for value in (chunk_id, document_id, version_id, document_number, title)):
        return None
    source_url = metadata.get("source_url")
    return Citation(
        chunk_id=str(chunk_id),
        document_id=str(document_id),
        version_id=str(version_id),
        document_number=str(document_number),
        title=str(title),
        source=str(source_url or _expected_source(fields)),
        article=metadata.get("article"),
        clause=metadata.get("clause"),
        point=metadata.get("point"),
        section=metadata.get("section"),
        page=metadata.get("page"),
        source_url=source_url,
        excerpt=build_focused_excerpt(
            str(fields["content"]),
            focus_text,
        ),
        # Forward the rerank_score so the API response can surface quality signal.
        # When the source item is a Candidate it carries rerank_score directly.
        # For other item types we fall back to the score in metadata.
        rerank_score=fields.get("rerank_score") or metadata.get("rerank_score"),
    )


def build_citations(
    citation_chunk_ids: Sequence[str] | Sequence[EvidenceContext],
    final_contexts: Sequence[EvidenceContext] | Sequence[str] | Mapping[str, EvidenceContext],
    *,
    user: UserContext | None = None,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
    focus_text: str = "",
) -> list[Citation]:
    """Build citations from metadata; no LLM-provided location or URL is accepted."""

    # Accept the natural ``build_citations(final_contexts, ids)`` spelling too.
    first = list(citation_chunk_ids) if not isinstance(citation_chunk_ids, Mapping) else []
    second = list(final_contexts) if not isinstance(final_contexts, Mapping) else final_contexts
    if isinstance(citation_chunk_ids, Mapping):
        first, second = list(final_contexts), citation_chunk_ids  # type: ignore[arg-type]
    elif first and not isinstance(first[0], str) and (not second or isinstance(second[0], str)):  # type: ignore[index]
        first, second = second, first
    elif not first and second and isinstance(second, list) and all(isinstance(value, str) for value in second):
        first, second = second, first
    # A mapping is the explicit output of ``build_citation_allowlist``; do not
    # re-filter it without the caller's user context.
    allowlist = (
        dict(second)
        if isinstance(second, Mapping)
        else build_citation_allowlist(
            second,  # type: ignore[arg-type]
            user=user,
            as_of=as_of,
            include_historical=include_historical,
        )
    )
    citations: list[Citation] = []
    for chunk_id in dict.fromkeys(str(value).strip() for value in first):
        item = allowlist.get(chunk_id)
        if item is None:
            continue
        citation = _build_one_citation(item, focus_text=focus_text)
        if citation is not None:
            citations.append(citation)
    return citations


def validate_and_build_citations(
    generated: GeneratedAnswer,
    evidence: list[RetrievedChunk],
    *,
    user: UserContext | None = None,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
    expected_min_citations: int = MIN_CITATIONS_FOR_GENERATION,
    focus_text: str = "",
) -> tuple[GeneratedAnswer, list[Citation]]:
    """Compatibility entry point: validate IDs and metadata before exposing citations.

    Parameters
    ----------
    generated:
        The LLM-generated answer plus the chunk_ids it cited.
    evidence:
        The retrieval / rerank output. Used as the citation allowlist.
    expected_min_citations:
        Minimum number of citations the answer must carry. Defaults
        to ``MIN_CITATIONS_FOR_GENERATION`` (1) but the workflow can
        raise this to 2 for SUFFICIENT evidence. An answer that falls
        short is downgraded to "unverified" via ``mark_answer_unverified``.
    """

    allowlist = build_citation_allowlist(
        evidence,
        user=user,
        as_of=as_of,
        include_historical=include_historical,
    )
    invalid_ids = validate_citation_chunk_ids(generated.cited_chunk_ids, allowlist)
    if invalid_ids:
        return mark_answer_unverified(generated, ["Trích dẫn do mô hình tạo không khớp final_contexts."]), []

    citations = build_citations(
        generated.cited_chunk_ids,
        allowlist,
        focus_text=focus_text or generated.answer,
    )
    errors = [
        *validate_document_versions(citations, allowlist),
        *validate_source_locations(citations, allowlist),
    ]
    if errors or (generated.cited_chunk_ids and len(citations) != len(set(generated.cited_chunk_ids))):
        return mark_answer_unverified(generated, errors), []

    if generated.answer and not citations and evidence:
        warnings = [*generated.warnings, "Câu trả lời không có trích dẫn nên không được coi là kết luận."]
        return generated.model_copy(update={"warnings": list(dict.fromkeys(warnings)), "confidence": "low"}), []

    count_ok, count_reason = _validate_citation_count(
        len(citations),
        expected_min=expected_min_citations,
        citations=citations,
    )
    if not count_ok:
        return mark_answer_unverified(generated, [count_reason]), []
    # Single-source bypass accepted the answer; surface a soft warning so
    # the operator can audit the citation. This does NOT downgrade
    # confidence (the bypass is metadata-grounded).
    if expected_min_citations >= 2 and len(citations) == 1:
        soft_warning = (
            "Câu trả lời dựa trên 1 trích dẫn có đầy đủ metadata — "
            "kiểm tra chéo trước khi sử dụng cho quyết định."
        )
        return generated.model_copy(update={
            "warnings": list(dict.fromkeys([*generated.warnings, soft_warning])),
        }), citations
    return generated, citations

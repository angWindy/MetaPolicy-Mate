from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src.domain.schemas import GeneratedAnswer, RetrievedChunk
from src.rag.config import RAGSettings


class AnswerGenerator(Protocol):
    async def generate(
        self,
        query: str,
        evidence: list[RetrievedChunk],
        *,
        tenant_display_name: str | None = None,
    ) -> GeneratedAnswer: ...


def _load_system_prompt(settings: RAGSettings) -> str:
    """Resolve the system prompt template for the LLM answer generator.

    Resolution order:
    1. ``settings.system_prompt_file`` if non-empty and readable — load file.
    2. ``settings.system_prompt_template`` (inline default).

    Raises FileNotFoundError if ``system_prompt_file`` is set but unreadable,
    so operators see config errors immediately at startup instead of getting
    a silent fallback to the hard-coded default.
    """
    file_path = (settings.system_prompt_file or "").strip()
    if file_path:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"system_prompt_file={file_path!r} is set but the file does "
                "not exist or is not readable."
            )
        return path.read_text(encoding="utf-8")
    return settings.system_prompt_template


class TemplateAnswerGenerator:
    """Safe local generator for tests and demos without an API key."""

    async def generate(
        self,
        query: str,
        evidence: list[RetrievedChunk],
        *,
        tenant_display_name: str | None = None,
    ) -> GeneratedAnswer:
        del tenant_display_name  # unused by template; preserved for protocol
        if not evidence:
            return GeneratedAnswer(
                answer="Tôi chưa có đủ căn cứ trong kho văn bản đã được phê duyệt để trả lời.",
                warnings=["Không tìm thấy bằng chứng phù hợp."],
                confidence="low",
                cited_chunk_ids=[],
            )
        best = evidence[0]
        metadata = best.metadata
        # Defensive: every locator part must be a non-empty string. Without
        # this, missing metadata produces a citation like "QĐ-ĐHBK-10232, Điều None"
        # which is meaningless to the user.
        def _str_or_none(value):
            return value if isinstance(value, str) and value.strip() else None

        document_number = _str_or_none(metadata.get("document_number"))
        article = _str_or_none(metadata.get("article"))
        clause = _str_or_none(metadata.get("clause"))
        page = metadata.get("page")
        title = _str_or_none(metadata.get("title"))

        locator_parts = [
            document_number,
            f"Điều {article}" if article else None,
            f"Khoản {clause}" if clause else None,
            f"trang {page}" if page is not None else None,
        ]
        locator = ", ".join(item for item in locator_parts if item)
        return GeneratedAnswer(
            answer=f"Theo {locator or title or 'văn bản nguồn'}: {best.text}",
            cited_chunk_ids=[best.chunk_id],
            confidence="medium" if best.score < 0.5 else "high",
        )


def _format_chunk_for_generator(text: str, focus_text: str = "") -> str:
    import re

    from src.rag.citation_validator import build_focused_excerpt

    formatted = text
    if "điểm chữ quy đổi" in text.lower() and "thang 10" in text.lower():
        normalized_content = text.replace("–", "-").replace("—", "-").replace("÷", "-")
        try:
            before_grades, _, after_grades = normalized_content.partition(
                "Điểm chữ quy đổi"
            )
            interval_text = before_grades.split("thang 10", 1)[-1]
            intervals = re.findall(
                r"\d+(?:[.,]\d+)?\s*-\s*\d+(?:[.,]\d+)?",
                interval_text,
            )
            grade_text = after_grades.split("Điểm số quy đổi", 1)[0]
            grades = re.findall(
                r"(?<!\w)(?:A\+|B\+|C\+|D\+|[A-F])(?!\w)",
                grade_text,
                flags=re.IGNORECASE,
            )
            if intervals and len(intervals) == len(grades):
                rows = []
                for grade, interval in zip(grades, intervals):
                    clean_interval = re.sub(r"\s+", " ", interval)
                    clean_interval = clean_interval.replace("-", "đến").strip()
                    rows.append(f"| {grade.upper()} | {clean_interval} |")
                table_md = "\nBảng quy đổi điểm tương ứng:\n| Điểm chữ | Khoảng điểm thang 10 |\n|---|---|\n" + "\n".join(rows)
                formatted = f"{text}\n\n{table_md}"
        except Exception:
            pass
    # Long serialized tables dilute the requested row. Keep the original
    # RetrievedChunk unchanged for policy and citation validation, while the
    # generator sees the header and the row most relevant to the question.
    if focus_text and "|" in formatted and len(formatted) > 3000:
        return build_focused_excerpt(formatted, focus_text, max_chars=3000)
    return formatted


class MultiProviderAnswerGenerator:
    """LLM-backed generator using multi-provider factory (OpenAI / Claude / Gemini / Mistral / Ollama).

    LLM được khởi tạo lazy trong lần gọi `generate()` đầu tiên, tránh việc gọi API
    ngay khi khởi tạo (nhiều provider yêu cầu API key ngay cả khi chỉ validate config).

    Retry & Fallback:
    - Khi provider bị rate-limit (429) hoặc lỗi tạm thời (timeout, 5xx), tự động
      retry với exponential backoff (LLM_MAX_RETRIES lần).
    - Sau khi hết retry → chuyển sang fallback provider trong chain
      (LLM_FALLBACK_PROVIDERS: mặc định ollama → template).
    - Template luôn ở cuối chain và không bao giờ fail.

    The system prompt is loaded from ``settings.system_prompt_file`` (if set)
    or falls back to ``settings.system_prompt_template``. Tenant branding is
    substituted via ``{tenant_name}`` and the response language via
    ``{response_language}`` — both come from settings, so multi-tenant
    deployments can override them per environment without code changes.
    """

    def __init__(self, settings: RAGSettings):
        self._settings = settings
        self._llm: Any = None  # MultiProviderResilientLLM
        # Resolve the template once at construction; the result is cached for
        # the lifetime of this generator instance. If ``system_prompt_file``
        # changes between calls, the operator must restart the process.
        self._system_prompt = _load_system_prompt(settings)

    @property
    def _resilient(self) -> Any:  # MultiProviderResilientLLM
        if self._llm is None:
            from src.services.llm_resilient import MultiProviderResilientLLM

            self._llm = MultiProviderResilientLLM(self._settings)
        return self._llm

    async def generate(
        self,
        query: str,
        evidence: list[RetrievedChunk],
        *,
        tenant_display_name: str | None = None,
    ) -> GeneratedAnswer:
        from src.services.llm_factory import AnswerSchema

        # Build set of allowed chunk_ids from evidence so we can validate
        # the LLM's cited_chunk_ids against ground truth (defense against
        # hallucinated citations).
        allowed_chunk_ids = {item.chunk_id for item in evidence}

        evidence_text = "\n\n".join(
            (
                f"[{idx + 1}] [chunk_id={item.chunk_id}]\n"
                f"Source: {item.metadata.get('document_number') or '-'} | "
                f"Title: {item.metadata.get('title') or '-'} | "
                f"Section: {item.metadata.get('section') or '-'} | "
                f"Article {item.metadata.get('article') or '-'} | "
                f"Clause {item.metadata.get('clause') or '-'} | "
                f"Page {item.metadata.get('page') or '-'}\n"
                f"Content: {_format_chunk_for_generator(item.text, query)}"
            )
            for idx, item in enumerate(evidence)
        )

        # Per-call tenant display name overrides the global settings default.
        # The workflow injects the per-user display name resolved from
        # JWT school_code + roles, so multi-tenant deployments see the
        # correct branding without restarting the process.
        effective_tenant_name = (
            tenant_display_name
            if isinstance(tenant_display_name, str) and tenant_display_name.strip()
            else self._settings.tenant_display_name
        )

        # Build the system prompt by substituting the configured placeholders.
        # Unknown placeholders are left intact so operators can extend the
        # template without crashing the generator. ``tenant_name`` and
        # ``response_language`` are sourced from settings, NOT hard-coded.
        try:
            prompt = self._system_prompt.format(
                tenant_name=effective_tenant_name,
                response_language=self._settings.response_language,
                query=query,
                evidence_text=evidence_text or "(no evidence retrieved)",
            )
        except (KeyError, IndexError) as exc:
            # Malformed template (e.g. unbalanced braces) — log and fall back
            # to the original evidence-only prompt so the LLM call still
            # goes through instead of failing the whole workflow.
            return GeneratedAnswer(
                answer="Tôi chưa có đủ căn cứ để kết luận.",
                warnings=[
                    f"system_prompt_template has invalid placeholder syntax: "
                    f"{type(exc).__name__}: {exc}"
                ],
                confidence="low",
            )

        try:
            result = await self._resilient.ainvoke(prompt)
            if isinstance(result, AnswerSchema):
                raw_cited = result.cited_chunk_ids
                validated_cited, dropped = _validate_citations(
                    raw_cited, allowed_chunk_ids, evidence=evidence, answer=result.answer
                )
                warnings = list(result.warnings)
                if dropped:
                    warnings.append(
                        f"LLM cite {len(dropped)} chunk_id ngoài bằng chứng; "
                        f"đã loại: {dropped}"
                    )
                return GeneratedAnswer(
                    answer=result.answer,
                    cited_chunk_ids=validated_cited,
                    warnings=warnings,
                    confidence=result.confidence,
                )
            elif isinstance(result, dict):
                raw_cited = result.get("cited_chunk_ids", []) or []
                validated_cited, dropped = _validate_citations(
                    raw_cited, allowed_chunk_ids, evidence=evidence, answer=result.get("answer", "")
                )
                result["cited_chunk_ids"] = validated_cited
                warnings = list(result.get("warnings", []) or [])
                if dropped:
                    warnings.append(
                        f"LLM cite {len(dropped)} chunk_id ngoài bằng chứng; "
                        f"đã loại: {dropped}"
                    )
                    result["warnings"] = warnings
                return GeneratedAnswer(**result)
            else:
                return GeneratedAnswer(
                    answer=str(result),
                    warnings=[f"Unexpected result type from {self._settings.generator_provider}: {type(result)}"],
                    confidence="low",
                )
        except Exception as exc:
            # This should only fire when even the template fallback has failed.
            return GeneratedAnswer(
                answer="Xin lỗi, đã xảy ra lỗi khi sinh câu trả lời. Vui lòng thử lại.",
                warnings=[f"Lỗi generator (fallback exhausted): {type(exc).__name__}: {exc}"],
                confidence="low",
            )


def build_answer_generator(settings: RAGSettings) -> AnswerGenerator:
    provider = settings.generator_provider
    if provider == "template":
        return TemplateAnswerGenerator()
    # All other providers use the multi-provider factory
    return MultiProviderAnswerGenerator(settings)


def _validate_citations(
    cited: list[str],
    allowed_ids: set[str],
    evidence: list[RetrievedChunk] | None = None,
    answer: str = "",
) -> tuple[list[str], list[str]]:
    """Filter cited chunk_ids to those that actually appear in the evidence.

    Also maps 1-based evidence index references (e.g. "1", "2") and recovers
    bracketed markers from answer text if cited list is empty or dropped.
    """
    validated: list[str] = []
    dropped: list[str] = []
    for cid in cited or []:
        clean_cid = str(cid).strip().strip("[]")
        if clean_cid in allowed_ids:
            if clean_cid not in validated:
                validated.append(clean_cid)
        elif clean_cid.isdigit() and evidence and 1 <= int(clean_cid) <= len(evidence):
            mapped_id = evidence[int(clean_cid) - 1].chunk_id
            if mapped_id in allowed_ids and mapped_id not in validated:
                validated.append(mapped_id)
        else:
            dropped.append(cid)

    if not validated and answer and evidence:
        import re
        for m in re.findall(r"\[(\d+)\]", answer):
            idx = int(m)
            if 1 <= idx <= len(evidence):
                mapped_id = evidence[idx - 1].chunk_id
                if mapped_id in allowed_ids and mapped_id not in validated:
                    validated.append(mapped_id)

    return validated, dropped

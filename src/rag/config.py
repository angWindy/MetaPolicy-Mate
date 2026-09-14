import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvidenceThresholds(BaseModel):
    """Domain-calibrated thresholds consumed by the evidence gate."""

    # Lowered 2026-09-01: original 0.20/0.10 caused 8/12 questions to be
    # rejected as "insufficient evidence" (conf=low). New defaults allow
    # more borderline candidates through to the generator for partial
    # grounding, reducing the abstain rate.
    sufficient_top_score: float = 0.15
    partial_top_score: float = 0.05
    minimum_score_gap: float = Field(default=0.0, ge=0.0)
    minimum_independent_sources: int = Field(default=1, ge=1)
    max_retries: int = Field(default=2, ge=0, le=10)
    require_citation_metadata: bool = False  # Changed from True to reduce rejections

    @model_validator(mode="after")
    def validate_score_thresholds(self) -> "EvidenceThresholds":
        if self.partial_top_score > self.sufficient_top_score:
            raise ValueError("partial_top_score must not exceed sufficient_top_score")
        return self


class RAGSettings(BaseSettings):
    """Configuration owned by the RAG and database module."""

    model_config = SettingsConfigDict(
        env_file=(".env.rag", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    data_dir: Path = Path("./data")
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    openai_api_key: str = ""  # Used by both OpenAI LLM and OpenAI embeddings
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    generator_provider: Literal["template", "openai", "anthropic", "gemini", "mistral", "ollama"] = "template"
    embedding_provider: Literal["hash", "openai", "gemini", "sentence_transformers", "ollama"] = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_version: str = "1"
    embedding_device: str = "cpu"
    embedding_dimensions: int = Field(default=1536, ge=32, le=4096)
    embedding_batch_size: int = Field(default=64, ge=1, le=2048)
    sparse_embedding_provider: Literal["hashed"] = "hashed"
    sparse_embedding_model: str = "hashed-lexical"
    sparse_embedding_version: str = "1"
    database_url: str = "postgresql+psycopg://p234:p234@localhost:5432/p234"
    vector_backend: Literal["memory", "qdrant"] = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "hust-regulations-v1"
    qdrant_local_path: str = ""
    semantic_top_k: int = Field(default=20, ge=1, le=100)
    keyword_top_k: int = Field(default=20, ge=1, le=100)
    fused_limit: int = Field(default=60, ge=50, le=100)
    max_chunks_per_document: int = Field(default=4, ge=1, le=4)
    near_duplicate_similarity_threshold: float = Field(default=0.95, ge=0.8, le=1.0)
    retrieval_leg_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    tool_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_model_revision: str = "ef6343e0838fa68e275959461b0140b39f264eb0"
    reranker_device: str = "cpu"
    reranker_backend: Literal["torch", "onnx"] = "torch"
    reranker_batch_size: int = Field(default=32, ge=1, le=256)
    reranker_max_length: int = Field(default=512, ge=128, le=8192)
    reranker_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    reranker_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    reranker_circuit_cooldown_seconds: float = Field(default=60.0, gt=0.0, le=3600.0)
    reranker_provider: Literal["cross_encoder", "lexical_fallback"] = "cross_encoder"
    dev_auth_bypass: bool = True
    # ── Multi-provider LLM settings ─────────────────────────────────────────
    # OpenAI
    openai_base_url: str = "https://api.openai.com/v1"
    openai_org: str = ""
    # Anthropic (Claude)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_version: str = "2023-06-01"
    # Google Gemini
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_api_version: str = "v1"
    # MistralAI
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    # Ollama (local)
    ollama_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3"
    # Streaming
    streaming_enabled: bool = False
    # ── System prompt (multi-tenant, configurable) ───────────────────────────
    # The system prompt sent to the LLM during answer generation. Override via
    # env var SYSTEM_PROMPT_TEMPLATE or SYSTEM_PROMPT_TEMPLATE_FILE. Placeholder
    # ``{tenant_name}`` is substituted at runtime with ``tenant_display_name``.
    # Multi-tenant deployments MUST replace the default HUST branding via env.
    system_prompt_template: str = (
        "You are an expert regulatory assistant for {tenant_name}.\n"
        "Answer the user's question strictly from the EVIDENCE chunks below.\n"
        "\n"
        "Constraints:\n"
        "- Use ONLY the EVIDENCE; do not invent document numbers, articles, "
        "clauses, page numbers, or conclusions.\n"
        "- If EVIDENCE is empty, missing, or contradicts the question, respond "
        "that you do not have sufficient grounds to conclude.\n"
        "- Only assist analysis and suggest; never replace human authority.\n"
        "- CONVERSATION CONTEXT, when present in the QUESTION, is for "
        "reference resolution only and is NOT factual evidence.\n"
        "- ``cited_chunk_ids`` MUST be a subset of chunk_ids present in EVIDENCE.\n"
        "- Support each conclusion with the exact sentence or table row from "
        "EVIDENCE.\n"
        "- Preserve the unit and scope stated in EVIDENCE. If the question "
        "asks for TCHP, credits, a semester, or a year, state that exact unit "
        "in the answer; never infer a larger monetary unit from a bare table "
        "number.\n"
        "- When reading tables or lists, align columns and rows carefully "
        "(e.g. in grade conversion tables, match each letter grade to its "
        "exact corresponding score range).\n"
        "- Respond in {response_language} with concise, formal prose.\n"
        "\n"
        "Inline citation markers (MANDATORY):\n"
        "- Each EVIDENCE chunk is labeled [1], [2], [3], ... in order of appearance\n"
        "- When you reference a fact from an EVIDENCE chunk, append [N] "
        "(e.g. ``Theo Điều 5 [1]``, ``Quyết định 10232 [3]``) where N is the "
        "1-based index of the chunk in the EVIDENCE list.\n"
        "- If a sentence uses multiple chunks, include all markers: ``...quy định "
        "tại [1][3]...``\n"
        "- Do NOT add markers when no chunk is cited.\n"
        "- The first chunk cited in your response must be the first chunk in "
        "the list (index 1), the second distinct chunk you cite must be index 2, "
        "and so on. Keep numbering consistent with the EVIDENCE order.\n"
        "- ``cited_chunk_ids`` MUST match the chunks you cited with [N] markers.\n"
        "\n"
        "QUESTION:\n{query}\n"
        "\n"
        "EVIDENCE:\n{evidence_text}\n"
    )
    # Optional path to a file containing the system prompt template. If set,
    # ``system_prompt_file`` is loaded at startup and overrides the inline
    # ``system_prompt_template`` default. Useful for ops to iterate on prompts
    # without code changes.
    system_prompt_file: str = ""
    # Display name of the tenant the LLM is answering on behalf of (e.g.
    # "HUST - Hanoi University of Science and Technology"). Substituted into
    # ``{tenant_name}`` of the system prompt template.
    tenant_display_name: str = "Hanoi University of Science and Technology (HUST)"
    # Output language for the LLM response. Substituted into
    # ``{response_language}`` of the system prompt template.
    response_language: str = "Vietnamese"
    # ── Retry & Fallback ─────────────────────────────────────────────────────
    # LLM: max retries on transient errors (429, timeout, 5xx) before fallback
    llm_max_retries: int = Field(default=3, ge=1, le=10)
    llm_retry_base_delay: float = Field(default=2.0, ge=0.5, le=60.0)
    llm_retry_max_delay: float = Field(default=60.0, ge=1.0, le=300.0)
    # Embedding: max retries before fallback to sentence_transformers or hash
    embedding_max_retries: int = Field(default=3, ge=1, le=10)
    embedding_retry_base_delay: float = Field(default=1.0, ge=0.5, le=60.0)
    embedding_retry_max_delay: float = Field(default=30.0, ge=1.0, le=120.0)
    # Fallback chain (comma-separated, evaluated in order)
    # LLM fallback: first failed provider → next in chain → template (last resort)
    llm_fallback_providers: str = "ollama,template"
    # Embedding fallback: first failed provider → next in chain → hash (last resort)
    embedding_fallback_providers: str = "sentence_transformers,hash"
    rerank_candidate_limit: int = Field(default=30, ge=10, le=60)
    rerank_pre_diversity_limit: int = Field(default=15, ge=5, le=20)
    rerank_score_threshold: float | None = None
    rerank_score_gap_min: float | None = Field(default=None, gt=0.0)
    rerank_mmr_lambda: float = Field(default=0.85, ge=0.5, le=1.0)
    final_context_limit: int = Field(default=5, ge=3, le=5)
    final_max_chunks_per_document: int = Field(default=2, ge=1, le=2)
    context_token_budget: int = Field(default=3000, ge=128, le=32768)
    context_max_referenced_definitions: int = Field(default=3, ge=0, le=10)
    final_top_k: int = Field(default=6, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1, le=200)
    rrf_alpha: float = Field(default=0.3, ge=0.2, le=0.4)
    minimum_evidence_score: float = Field(default=0.05, ge=0.0, le=1.0)
    evidence_domain: str = "general"
    evidence_thresholds_by_domain: dict[str, EvidenceThresholds] = Field(
        default_factory=lambda: {"general": EvidenceThresholds()}
    )
    expiry_warning_days: int = Field(default=30, ge=1, le=365)
    # Hard latency budget per pipeline leg. When exceeded the leg fails
    # fast and routes to abstain_node, preventing runaway latency.
    retrieval_timeout_seconds: float = Field(default=20.0, gt=0.0, le=60.0)
    rerank_timeout_seconds: float = Field(default=15.0, gt=0.0, le=60.0)
    generation_timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    # In-memory LRU cache for retrieval results. Key includes tenant_id
    # so cross-tenant queries do not collide.
    cache_enabled: bool = True
    cache_ttl_seconds: float = Field(default=300.0, gt=0.0, le=3600.0)
    cache_max_size: int = Field(default=256, ge=1, le=4096)
    chunk_max_chars: int = Field(default=2200, ge=300, le=10000)
    chunk_overlap_chars: int = Field(default=250, ge=0, le=2000)
    parser_backend: Literal["auto", "native", "pypdf", "pypdf_table", "docling"] = "auto"
    docling_enabled: bool = True
    require_human_approval: bool = True
    # ── Query rewrite (deterministic lexical expansion) ─────────────────────
    # When enabled, transform_query_node appends short lexical variants to
    # the variant list (e.g. "JLPT" → "Bảng quy đổi tương đương các chứng
    # chỉ tiếng Nhật"). The hybrid retriever then merges results across
    # variants via RRF. Zero LLM cost — purely pattern-matched.
    query_expansion_enabled: bool = True
    query_expansion_max_extra: int = Field(default=4, ge=0, le=8)
    # ── HyDE (Hypothetical Document Embedding) ──────────────────────────────
    # When enabled, transform_query_node asks the generator to write a
    # short hypothetical passage answering the query. The passage is then
    # embedded in place of the raw query for dense retrieval. Best for
    # semantic queries where the user's wording diverges from chunk
    # vocabulary. Costs one LLM call per query (cached after first hit).
    hyde_enabled: bool = False
    hyde_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    hyde_min_query_chars: int = Field(default=12, ge=4, le=120)

    # ── OCR / PDF Processing ────────────────────────────────────────────────
    ocr_enabled: bool = True
    # Engine selection. Two supported values:
    # - ``rapidocr_vi`` (RapidOCR + PP-OCRv6 Vietnamese ONNX, default) —
    #   handles mixed digital/scan PDFs through the hybrid text-extract gate.
    # - ``pp_structure`` (PP-StructureV3 layout-aware pipeline) — opt-in for
    #   table-heavy documents; legacy PaddleOCR abstraction has been retired.
    ocr_engine: Literal["rapidocr_vi", "pp_structure"] = "rapidocr_vi"
    ocr_gpu: bool = False  # CPU is the MVP default; pass --ocr-gpu to enable CUDA
    ocr_languages: str = "vi,en"  # Comma-separated language codes
    ocr_batch_size: int = Field(default=1, ge=1, le=32)
    ocr_workers: int = Field(default=4, ge=1, le=32)
    ocr_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # Lowered from 0.7 -> 0.5 (2026-09-06 metadata cleanup). Lower
    # threshold surfaces more scan pages as low-confidence for the
    # audit flag, which routes them through the semantic-chunking
    # fallback in ``extract_sections(ocr_mode=True)``. Operators can
    # still override per-environment via env var or constructor.
    ocr_low_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    # Hybrid text-extract gate — pages with >= this many native chars
    # bypass OCR even when the page classifier labelled them SCAN/HYBRID.
    # 0 disables the override (legacy behaviour).
    ocr_hybrid_text_threshold: int = Field(default=50, ge=0, le=10_000)
    # Vietnamese recognition model directory (env: OCR_MODELS_DIR).
    ocr_models_dir: Path = Field(default=Path("ocr_models"))
    # PP-StructureV3 (optional, layout-aware + table recognition)
    use_pp_structure: bool = False
    pp_structure_layout_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    pp_structure_text_det_limit_side_len: int = Field(default=1536, ge=256, le=4096)
    # Image preprocessing (scan pages)
    preprocess_mode: Literal["fast", "balanced", "quality"] = "quality"
    preprocess_dpi: int = Field(default=600, ge=72, le=1200)
    preprocess_binary_threshold: int = Field(default=140, ge=0, le=255)
    preprocess_denoise: bool = True
    preprocess_sharpen: bool = True
    # Table detection
    detect_tables: bool = True
    # VLM review (optional, expensive)
    vlm_enabled: bool = False
    vlm_review_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @property
    def ocr_languages_list(self) -> list[str]:
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]

    @property
    def llm_fallback_provider_list(self) -> list[str]:
        return [p.strip() for p in self.llm_fallback_providers.split(",") if p.strip()]

    @property
    def embedding_fallback_provider_list(self) -> list[str]:
        return [p.strip() for p in self.embedding_fallback_providers.split(",") if p.strip()]

    @property
    def raw_documents_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def parsed_documents_dir(self) -> Path:
        return self.data_dir / "parsed"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_dir / "quarantine"

    @model_validator(mode="after")
    def validate_database_url(self) -> "RAGSettings":
        # SQLite is no longer a supported runtime database. Tests can still opt in
        # to an in-memory SQLite fixture via APP_ENV=test to avoid requiring a
        # Postgres container in the unit suite.
        scheme = self.database_url.split("://", 1)[0].lower()
        is_sqlite = scheme in {"sqlite", "sqlite+pysqlite", "sqlite+pysqlcipher"}
        if is_sqlite and self.app_env != "test":
            raise ValueError(
                "SQLite is no longer supported as a runtime database. "
                "Configure DATABASE_URL to point at Postgres "
                "(e.g. postgresql+psycopg://user:pass@host:5432/db)."
            )
        if not is_sqlite and not scheme.startswith("postgresql"):
            raise ValueError(
                f"Unsupported DATABASE_URL scheme '{scheme}'. "
                "Use 'postgresql+psycopg://...' (Postgres only)."
            )
        return self

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "RAGSettings":
        if self.app_env == "production":
            # OpenAI
            if self.generator_provider == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when GENERATOR_PROVIDER=openai")
            if self.embedding_provider == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
            if self.embedding_provider == "gemini" and not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
            # Anthropic
            if self.generator_provider == "anthropic" and not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required when GENERATOR_PROVIDER=anthropic")
            # Google Gemini
            if self.generator_provider == "gemini" and not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when GENERATOR_PROVIDER=gemini")
            # MistralAI
            if self.generator_provider == "mistral" and not self.mistral_api_key:
                raise ValueError("MISTRAL_API_KEY is required when GENERATOR_PROVIDER=mistral")
            # Ollama (optional - local, may not require key)
            if self.generator_provider == "ollama":
                if not self.ollama_base_url:
                    raise ValueError("OLLAMA_BASE_URL is required when GENERATOR_PROVIDER=ollama")
            # Embedding
            if self.embedding_provider == "openai" and self.app_env == "production":
                allowed_dimensions = {256, 512, 1024, 1536, 3072}
                if self.embedding_dimensions not in allowed_dimensions:
                    raise ValueError(
                        f"OPENAI embedding_dimensions must be one of {sorted(allowed_dimensions)}, "
                        f"got {self.embedding_dimensions}."
                    )
            if self.dev_auth_bypass:
                raise ValueError("DEV_AUTH_BYPASS must be disabled in production.")
        if self.reranker_backend == "onnx" and not self.reranker_device.startswith("cpu"):
            raise ValueError("The ONNX reranker backend is supported for CPU only.")
        return self

    def evidence_thresholds(self, domain: str | None = None) -> EvidenceThresholds:
        requested = (domain or self.evidence_domain).strip().casefold()
        if requested in self.evidence_thresholds_by_domain:
            return self.evidence_thresholds_by_domain[requested]
        return self.evidence_thresholds_by_domain.get("general", EvidenceThresholds())

    @model_validator(mode="before")
    @classmethod
    def _load_evidence_thresholds_from_env(cls, values: dict) -> dict:
        """Populate `evidence_thresholds_by_domain` from legacy EVIDENCE_* env vars.

        Earlier releases exposed EVIDENCE_SUFFICIENT_TOP_SCORE / EVIDENCE_PARTIAL_TOP_SCORE
        as flat env vars. The current schema nests them under
        `evidence_thresholds_by_domain[<domain>]`. This validator bridges the
        gap so that flipping an env var in `.env.rag` actually changes the
        evidence gate's behaviour instead of being silently ignored.
        """
        # First: read directly from .env.rag files (pydantic-settings only
        # populates `os.environ` from `env_file` for declared fields, so we
        # have to parse them ourselves for the legacy EVIDENCE_* keys).
        candidate_values = dict(os.environ)
        try:
            from dotenv import dotenv_values
            for env_path in (".env.rag", ".env"):
                parsed = dotenv_values(env_path)
                if parsed:
                    candidate_values.update(parsed)
        except ImportError:
            pass

        env_pairs = {
            "sufficient_top_score": "EVIDENCE_SUFFICIENT_TOP_SCORE",
            "partial_top_score": "EVIDENCE_PARTIAL_TOP_SCORE",
            "minimum_score_gap": "EVIDENCE_MINIMUM_SCORE_GAP",
            "minimum_independent_sources": "EVIDENCE_MINIMUM_INDEPENDENT_SOURCES",
            "require_citation_metadata": "EVIDENCE_REQUIRE_CITATION_METADATA",
        }
        env_overrides = {
            key: candidate_values.get(var)
            for key, var in env_pairs.items()
            if candidate_values.get(var) is not None
        }
        if not env_overrides:
            return values

        domain = (values.get("evidence_domain") or "general").strip().casefold()
        if "evidence_thresholds_by_domain" in values:
            existing = dict(values["evidence_thresholds_by_domain"] or {})
        else:
            existing = {}
        # If the caller already provided a threshold object for this
        # domain, honour their values. Env overrides are a fallback for
        # production deployments that have not configured explicit
        # thresholds via code.
        if existing.get(domain):
            return values
        current: dict[str, object] = {}
        for key, raw in env_overrides.items():
            # Detect bool fields vs numeric.
            if key == "require_citation_metadata":
                current[key] = str(raw).lower() in {"1", "true", "yes", "on"}
            elif key == "minimum_independent_sources":
                try:
                    current[key] = int(raw)
                except ValueError:
                    current[key] = float(raw)
            else:
                try:
                    current[key] = float(raw)
                except ValueError:
                    continue
        if current:
            existing[domain] = current
            values["evidence_thresholds_by_domain"] = existing
        return values


@lru_cache
def get_rag_settings() -> RAGSettings:
    return RAGSettings()

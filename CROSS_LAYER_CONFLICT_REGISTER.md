# Cross-Layer Conflict Register

## C-021 — Conversation context contract drift

**Severity**: P1  
**Domain**: RAG chat  
**Layers**: Use cases / backend behavior ↔ RAG architecture

**Description**: `USE_CASES.md` UC-D-04 and `BACKEND_BEHAVIOR.md` require
session-backed follow-up context, while `docs/rag_database_architecture.md`
stated that `conversation_context` was omitted from the MVP.

**Evidence**:

- `USE_CASES.md`: UC-D-04 requires retrieval using relevant saved session context.
- `BACKEND_BEHAVIOR.md`: D-04 persists turns and re-checks citation access.
- `docs/rag_database_architecture.md`: the input contract previously said
  `conversation_context` was removed.

**Impact**: The implementation persisted sessions but concatenated up to ten full
answers into the retrieval query. This diluted single-turn relevance and did not
give the generator a separately governed memory channel.

**Resolution**: Resolved on 2026-09-03 by explicit user direction. Conversation
memory is now bounded, re-authorized per turn, separated from factual evidence,
and only added to retrieval for explicit follow-up references.

---

## C-022 — JWT school context source conflicts across canonical specifications

**Severity**: P1  
**Domain**: Auth / RBAC / tenant context  
**Layers**: Agent rules / backend architecture / backend behavior

**Description**: The canonical specifications disagree on how the JWT
`school_id` claim is derived. `AGENTS.md` and one section of
`BACKEND_ARCHITECTURE.md` require `user.department_id`, while another section
of `BACKEND_ARCHITECTURE.md` and `BACKEND_BEHAVIOR.md` say it comes from global
`Settings`.

**Evidence**:

- `AGENTS.md:163`: `school_id` must be derived from `user.department_id`, not
  from `Settings`.
- `BACKEND_ARCHITECTURE.md:120-123`: the JWT claim is derived from
  `user.department_id`, not `Settings`.
- `BACKEND_ARCHITECTURE.md:220-227`: the JWT claim table says `school_id` comes
  from `Settings`.
- `BACKEND_BEHAVIOR.md:102-105`: `school_id` is described as coming from
  `Settings`.
- Current code in `src/application/features/auth/register/register_handler.py`
  and `src/infrastructure/auth/jwt_token_service.py` uses the user-derived
  school context.

**Impact**: Following the stale global-settings contract could assign the same
tenant context to users from different schools, weakening tenant isolation and
making authorization, audit, and retrieval filters inconsistent.

**Recommendation**: Confirm `user.department_id` / the authenticated user's
school context as the canonical source, then update the two stale specification
passages. Do not change runtime auth behavior until that decision is approved.

**Resolution**: Resolved on 2026-09-03 by explicit user confirmation. The
authenticated user's `user.department_id` is the canonical JWT `school_id`
source; the stale `Settings` passages were updated without changing runtime
behavior.

---

## C-023 — Eval D73 contradicts the authoritative transition clause

**Severity**: P1  
**Domain**: RAG evaluation / training regulation  
**Layers**: Golden evaluation data ↔ authoritative PostgreSQL source

**Description**: Case D73 expects Khoản 2 Điều 18 to apply from the 2021
admission cohort (K66), while the indexed source text states that it applies
from the 2022 admission cohort.

**Evidence**:

- `tests/sweep/golden_v7_domain_100.jsonl`: D73 reference answer and required
  tokens identify 2021 / K66.
- PostgreSQL chunk `dfd8175a-9579-501d-b342-1e932727f715`: "Khoản 2 Điều 18
  ... được áp dụng với các khóa tuyển sinh từ năm 2022."

**Impact**: A source-grounded answer of 2022 is incorrectly scored as a failed
answer, while changing retrieval or generation to return 2021 would introduce
a factual error.

**Recommendation**: Verify the source PDF and amend D73 to 2022 only after
human approval. Do not tune production logic toward the current label.

---

## C-024 — Eval D74 uses the regulation-wide effective date for a listed exception

**Severity**: P1  
**Domain**: RAG evaluation / training regulation  
**Layers**: Golden evaluation data ↔ authoritative PostgreSQL source

**Description**: Case D74 expects the general effective date in Điều 48
(semester 1 of 2025-2026), but its question specifically asks about Khoản 1
Điều 24, which is listed as an exception effective from semester 2 of
2024-2025.

**Evidence**:

- `tests/sweep/golden_v7_domain_100.jsonl`: D74 requires 2025-2026 and semester 1.
- PostgreSQL chunk `108a7c93-178d-5884-b5f9-9383811e1f0f`: "Khoản 1 Điều 24
  ... được áp dụng từ học kỳ 2 năm học 2024-2025."

**Impact**: The current correct, precisely scoped answer is marked wrong. Tuning
the application to the golden label would make it ignore an explicit exception.

**Recommendation**: Verify the source PDF and amend D74 to semester 2 of
2024-2025 only after human approval. Do not change production behavior to match
the current label.

---

## C-025 — Precision@5 gate is incompatible with non-exhaustive chunk labels

**Severity**: P1
**Domain**: RAG evaluation
**Layers**: Golden evaluation data ↔ production gate

**Description**: The regression golden dataset labels one expected chunk per
answerable case, while `precision_at_k()` divides the number of labeled hits by
the fixed value `k=5` and the production gate requires `precision_at_5 >= 0.85`.

**Evidence**:

- `docs/eval/datasets/golden_questions.regression.jsonl`: each answerable row
  contains exactly one `expected_chunk_id`.
- `src/evaluation/pipeline.py`: `precision_at_k()` uses `hits / k` and
  `production_gate()` requires `precision_at_5 >= 0.85`.
- `docs/eval/results/retrieval_evaluation_20260904.md`: all expected chunks are
  retrieved and ranked first, but Precision@5 is 0.20.

**Impact**: The current dataset can score at most 0.20 Precision@5 per
answerable case, so the 0.85 gate is mathematically unreachable even when every
labeled expected chunk is ranked first. The resulting FAIL cannot be used as a
retrieval-quality verdict.

**Recommendation**: Choose one contract before using this metric as a release
gate: exhaustively label relevance for the top-five pool, replace the gate with
Hit@5/Recall@5 for single-answer labels, or define a judged-precision metric.
Do not lower the threshold or reinterpret missing relevance labels as negative
without data-owner approval.

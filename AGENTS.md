# AGENTS.md

> Project: P-234 PolicyMeta AI
> Last Updated: 2026-09-01
> Version: 1.2

---

## Purpose

This file defines rules for AI agents working on this codebase. Follow these rules to avoid creating cross-layer conflicts.

---

## Language Rules

**Think in English. Explain in Vietnamese.**

- **Chain-of-thought reasoning** (analysis, planning, root-cause diagnosis): always English — it keeps the reasoning portable and unambiguous.
- **User-facing communication** (chat replies, PR descriptions, BUGS_FOUND narratives, inline explanations to the user): Vietnamese by default.
- **Code, file headers, commit messages, docstrings, technical specs**: always English — these are the artefacts that survive beyond the team.
- **Code identifiers** (function names, variable names, class names, schema fields, enum members): always English, regardless of surrounding prose.
- **Error messages and log lines**: English (grep-friendly; matches the existing codebase convention).
- **User-visible UI strings** (frontend copy, validation errors shown to end-users): Vietnamese, owned by the frontend team.

Rationale: the codebase mixes Vietnamese (legacy handlers, user-facing copy) and English (canonical enums, contracts, technical docs). The rule keeps technical artefacts portable in English while ensuring all team-facing communication lands in Vietnamese.

---

## Specification Reading Order

When working on any feature, read specifications in this order:

1. **`AUDIT_SUMMARY.md`** - Tóm tắt conflict chéo layer (lịch sử)
2. **`PLAN.md`** - Trạng thái tổng thể, mục tiêu G1→G6
3. **`BACKEND_ARCHITECTURE.md`** - Kiến trúc canonical, RBAC identity
4. **`BACKEND_BEHAVIOR.md`** - Luồng backend chi tiết
5. **`USE_CASES.md`** - Bảng đặc tả 21 use case
6. **`docs/rag_database_architecture.md`** - RAG pipeline details

---

## Canonical Files (Source of Truth)

The following files are the **only** authoritative sources for their domains:

| Domain | Canonical File |
|--------|---------------|
| Processing Status Enum | `src/domain/schemas.py` (canonical English values) |
| Legal Status Enum | `src/domain/schemas.py` (canonical English values) |
| Access Scope Enum | `src/domain/schemas.py` (`PUBLIC` / `DEPARTMENT`) |
| Document Entity | `src/domain/entities/document.py` |
| DocumentVersion Entity | `src/domain/entities/document_version.py` |
| DocumentChunk Entity | `src/domain/entities/document_chunk.py` |
| API Contracts | `src/presentation/api/contracts/` |
| RAG Contracts | `src/domain/schemas.py` (`QdrantPayload`) |
| Database Schema | `database/schema.sql` |
| RBAC Identity Mapping | `src/application/features/auth/register/register_handler.py` (school_code → role/department) |

---

## Core Rules

### Rule 1: No Code Overrides Accepted Spec

If code and specification differ:
- **STOP**
- Report the drift
- Do not make the code match the spec without understanding why they differ
- Do not make the spec match the code without approval

### Rule 2: Two Specs Different = STOP

If two specification documents describe the same entity/contract differently:
- **STOP immediately**
- Do not implement anything
- Report the conflict
- Wait for human resolution

### Rule 3: No New Fields Without Contract

Before adding a new field:
1. Define it in the canonical entity
2. Add to database schema (migration)
3. Add to API contract (DTO)
4. Add to RAG metadata if applicable
5. Update all dependent layers

Do not add a field to just one layer.

### Rule 4: No Field Renames Across Layers

If you need to rename a field:
1. This is a **breaking change**
2. Requires migration plan
3. Requires updating all consumers
4. Requires updating all documentation

Do not rename silently across layers.

### Rule 5: No Enum Changes Without Canonical Update

Before changing enum values:
1. Update the canonical enum definition
2. Create database migration for existing data
3. Update all consumers
4. Update documentation

Do not add new enum values without canonical definition.

### Rule 6: No Implicit API Changes

Before modifying API behavior:
1. Update API contract documentation
2. Update frontend types
3. Update any external consumers
4. Test all consumers

Do not change response shape without explicit documentation.

### Rule 7: Cross-Layer Changes Require Impact Analysis

Before any cross-layer change:
1. Identify all affected layers
2. List all files that need updates
3. Estimate risk
4. Create rollback plan
5. Get approval for P0/P1 changes

Do not make cross-layer changes without analysis.

### Rule 8: Test Against Canonical Model

When writing tests:
1. Test against canonical entity definitions
2. Verify enum values match canonical
3. Test serialization/deserialization
4. Test API contract compliance

Do not write tests that validate incorrect behavior.

---

## Domain-Specific Rules

### Document Domain

- **Status values**: Use canonical enums only
- **Field names**: Use `document_number`, `legal_status`, `access_scope`
- **Do NOT use**: `status`, `access_level`, legacy Vietnamese values
- **API prefix**: `/api/v1/regulatory-documents`
- **Admin prefix**: `/api/v1/admin/documents`

### RAG Domain

- **Metadata contract**: Defined in `src/domain/schemas.py` (`QdrantPayload`)
- **Status values**: English lowercase (`published`, `approved`)
- **Filter fields**: `tenant_id`, `document_id`, `version_id`, `status`
- **Do NOT use**: Vietnamese status values in Qdrant payloads

### Auth/RBAC Domain

- **School context**: Always use `school_id` from JWT (derived from `user.department_id`, NOT from Settings)
- **Permission checks**: Use `require_permission()` dependency
- **Document access**: Use `require_document_access()` dependency
- **Do NOT bypass**: Auth checks for any reason

---

## Anti-Patterns to Avoid

### ❌ DO NOT: Hard-code status strings

```python
# WRONG
if status == "Indexed":
    ...

# RIGHT
from src.domain.enums.canonical import ProcessingStatus
if status == ProcessingStatus.INDEXED:
    ...
```

### ❌ DO NOT: Use wrong enum source

```python
# WRONG
from src.domain.enums.document_processing_status import DocumentProcessingStatus

# RIGHT
from src.domain.enums.canonical import ProcessingStatus
```

### ❌ DO NOT: Skip validation

```python
# WRONG - Trust database values
document = session.get(DocumentModel, id)

# RIGHT - Validate against canonical
from src.domain.enums.canonical import LegalStatus
if document.legal_status not in LegalStatus:
    raise ValueError("Invalid status")
```

### ❌ DO NOT: Create duplicate endpoints

```python
# WRONG - Duplicate functionality
@router.post("/admin/documents/{id}/approve")  # Already exists
@router.post("/admin/documents/{id}/approve-v2")  # Don't add this

# RIGHT - Update existing endpoint
@router.post("/admin/documents/{id}/approve")
```

---

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Enums | `*_status.py`, `*_scope.py` | `processing_status.py` |
| Entities | `*.py` (noun) | `document.py` |
| DTOs | `*_request.py`, `*_response.py` | `document_response.py` |
| Handlers | `*_handler.py` | `get_document_handler.py` |
| Commands | `*_command.py` | `upload_command.py` |
| Queries | `*_query.py` | `get_document_query.py` |

---

## Conflict Reporting

When you discover a conflict, report it using this template:

```
## Conflict Report

**ID**: C-XXX
**Severity**: P0/P1/P2/P3
**Domain**: [Domain name]
**Layers**: [Layer A] ↔ [Layer B]
**Description**: [What conflicts]

**Evidence**:
- [File A]: [specific line/code]
- [File B]: [specific line/code]

**Impact**: [Runtime impact description]

**Recommendation**: [How to fix]
```

---

## Emergency Procedures

### If you accidentally create a conflict:

1. Stop immediately
2. Revert the change
3. Report to human
4. Wait for guidance

### If you discover an existing conflict:

1. Document it in `CROSS_LAYER_CONFLICT_REGISTER.md`
2. Report to human
3. Do not attempt to fix without approval

---

## Exceptions

These rules may be temporarily suspended only with explicit human approval for:
- Security patches
- Data recovery operations
- Critical bug fixes

Document any exception with:
- Reason for exception
- Duration
- Rollback plan
- Sign-off from human

---

## Maintenance

This file should be updated when:
- New domains are added
- Architecture changes
- Conflicts are resolved
- New canonical files are created

Last review: 2026-08-31

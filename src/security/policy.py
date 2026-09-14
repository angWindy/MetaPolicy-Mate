from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from qdrant_client.models import (
    DatetimeRange,
    FieldCondition,
    Filter,
    IsNullCondition,
    MatchAny,
    MatchValue,
    PayloadField,
)

from src.domain.schemas import ClassificationLevel, QdrantPayload, UserContext

POLICY_VERSION = "retrieval-access-v1"

ROLE_INHERITANCE: dict[str, set[str]] = {
    "admin": {"staff", "manager", "data_owner", "security_admin"},
    "manager": {"staff"},
    "data_owner": {"staff"},
    "security_admin": set(),
}

ROLE_CLEARANCE: dict[str, ClassificationLevel] = {
    "anonymous": ClassificationLevel.PUBLIC,
    "staff": ClassificationLevel.INTERNAL,
    "admin": ClassificationLevel.INTERNAL,
    "manager": ClassificationLevel.INTERNAL,
    "data_owner": ClassificationLevel.INTERNAL,
    "security_admin": ClassificationLevel.INTERNAL,
    "confidential_reader": ClassificationLevel.CONFIDENTIAL,
    "restricted_reader": ClassificationLevel.RESTRICTED,
}

CLASSIFICATION_ORDER = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.INTERNAL: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.RESTRICTED: 3,
}


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Verified identity supplied by backend middleware or an IdP adapter."""

    user_id: str
    tenant_id: str
    department: str
    assigned_roles: frozenset[str] = field(default_factory=frozenset)
    granted_clearance: ClassificationLevel | None = None
    is_authenticated: bool = True


class AccessAuditWriter(Protocol):
    def create_audit_log(
        self,
        *,
        request_id: str,
        user: UserContext,
        action: str,
        outcome: str,
        query: str | None = None,
        resource_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> None: ...


def resolve_effective_roles(assigned_roles: Iterable[str]) -> set[str]:
    roles = {role.strip().lower() for role in assigned_roles if role.strip()}
    pending = list(roles)
    while pending:
        role = pending.pop()
        for inherited_role in ROLE_INHERITANCE.get(role, set()):
            if inherited_role not in roles:
                roles.add(inherited_role)
                pending.append(inherited_role)
    return roles


def resolve_clearance_level(
    effective_roles: Iterable[str],
    *,
    granted_clearance: ClassificationLevel | None = None,
) -> ClassificationLevel:
    if granted_clearance is not None:
        return granted_clearance
    clearance = ClassificationLevel.PUBLIC
    for role in effective_roles:
        role_clearance = ROLE_CLEARANCE.get(role.lower(), ClassificationLevel.PUBLIC)
        if CLASSIFICATION_ORDER[role_clearance] > CLASSIFICATION_ORDER[clearance]:
            clearance = role_clearance
    return clearance


def build_user_context(identity: AuthenticatedIdentity) -> UserContext:
    if not identity.is_authenticated:
        raise PermissionError("An authenticated backend identity is required.")
    roles = resolve_effective_roles(identity.assigned_roles)
    return UserContext(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        department=identity.department.upper(),
        roles=roles,
        clearance_level=resolve_clearance_level(
            roles,
            granted_clearance=identity.granted_clearance,
        ),
    )


def _as_utc_datetime(value: date | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _allowed_classifications(clearance: ClassificationLevel) -> list[str]:
    maximum = CLASSIFICATION_ORDER[clearance]
    return [
        level.value
        for level, rank in CLASSIFICATION_ORDER.items()
        if rank <= maximum
    ]


def build_access_filter(
    user: UserContext,
    *,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> Filter:
    """Build a fail-closed Qdrant pre-filter from backend-authenticated context."""

    effective_roles = resolve_effective_roles(user.roles)
    acl_conditions: list[Any] = [
        # allowed_units: PUBLIC documents have allowed_units=['*']; DEPARTMENT
        # documents have allowed_units=[department_code]. MatchAny accepts the
        # wildcard so both cases pass the ACL check.
        FieldCondition(
            key="allowed_units",
            match=MatchAny(
                any=sorted({user.department, "*"}),
            ),
        ),
        # allowed_roles: intentionally empty in P-234 (see rag_index_service.py).
        # Removing from the ACL filter so the policy does not require a
        # non-existent role match.
    ]
    # NOTE: allowed_roles is intentionally empty in P-234 (see rag_index_service.py).
    # The ACL filter uses allowed_units for department-level access control; role-based
    # filtering is not used in this deployment. We skip the allowed_roles condition
    # so the filter does not reject public documents that have allowed_roles=[].
    #
    # if effective_roles:
    #     acl_conditions.append(
    #         FieldCondition(
    #             key="allowed_roles",
    #             match=MatchAny(
    #                 any=sorted({*effective_roles, "*"}),
    #             ),
    #         ),
    #     )

    # Tenant filter: by default, restrict to the user's own tenant
    # plus the ``"public"`` namespace. ADMIN users are cross-tenant
    # and may search any tenant namespace — the entire tenant_id
    # condition is dropped for ADMIN so they can match every
    # tenant's chunks regardless of how the namespaces were
    # written at index time.
    is_admin = (
        "admin" in effective_roles
    )

    must: list[Any] = []

    if not is_admin:
        # Non-admin users: tenant_id must equal their own namespace
        # OR 'public'. 'public' is the canonical tenant_id for
        # PUBLIC-scope documents (see rag_index_service.py:
        # index_chunks sets tenant_id='public' for PUBLIC access_scope
        # documents). This allows any authenticated user to search
        # public documents regardless of their department.
        must.append(
            Filter(
                should=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(
                            value=user.tenant_id,
                        ),
                    ),
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value="public"),
                    ),
                ],
            )
        )

    must.extend(
        [
            FieldCondition(
                key="status",
                match=MatchValue(value="published"),
            ),
            FieldCondition(
                key="classification",
                match=MatchAny(
                    any=_allowed_classifications(
                        user.clearance_level,
                    ),
                ),
            ),
        ]
    )
    if not is_admin:
        must.append(Filter(should=acl_conditions))
    if not include_historical:
        target = _as_utc_datetime(as_of)
        must.extend(
            [
                FieldCondition(key="valid_from", range=DatetimeRange(lte=target)),
                Filter(
                    should=[
                        IsNullCondition(is_null=PayloadField(key="valid_to")),
                        FieldCondition(
                            key="valid_to",
                            range=DatetimeRange(gt=target),
                        ),
                    ]
                ),
            ]
        )
    return Filter(must=must)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return value
    if isinstance(value, datetime):
        return _as_utc_datetime(value)
    if isinstance(value, date):
        return _as_utc_datetime(value)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _as_utc_datetime(parsed)
    return None


def can_access_document(
    user: UserContext,
    document: QdrantPayload | Mapping[str, Any],
    *,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> bool:
    try:
        payload = (
            document
            if isinstance(document, QdrantPayload)
            else QdrantPayload.model_validate(document)
        )
    except (TypeError, ValueError):
        return False

    if payload.status != "published":
        return False
    effective_roles = resolve_effective_roles(user.roles)
    is_admin = "admin" in effective_roles
    # tenant_id: accept the user's own namespace OR 'public'.
    # 'public' is the canonical tenant_id for PUBLIC-scope documents.
    if not is_admin and payload.tenant_id not in {user.tenant_id, "public"}:
        return False
    try:
        classification = ClassificationLevel(payload.classification)
    except ValueError:
        return False
    if CLASSIFICATION_ORDER[classification] > CLASSIFICATION_ORDER[user.clearance_level]:
        return False

    allowed_by_acl = bool(
        is_admin
        or effective_roles.intersection(role.lower() for role in payload.allowed_roles)
        or user.department in payload.allowed_units
        or "*" in payload.allowed_roles
        or "*" in payload.allowed_units
    )
    if not allowed_by_acl:
        return False

    if include_historical:
        return True
    target = _as_utc_datetime(as_of)
    valid_from = _parse_datetime(payload.valid_from)
    valid_to = _parse_datetime(payload.valid_to)
    if valid_from is None or valid_from > target:
        return False
    return valid_to is None or valid_to > target


def audit_access_decision(
    audit_writer: AccessAuditWriter,
    *,
    request_id: str,
    user: UserContext,
    document: QdrantPayload,
    allowed: bool,
    reason: str,
) -> None:
    audit_writer.create_audit_log(
        request_id=request_id,
        user=user,
        action="retrieval_access_decision",
        outcome="allow" if allowed else "deny",
        resource_ids=[document.document_id, document.version_id, document.chunk_id],
        metadata={
            "policy_version": POLICY_VERSION,
            "tenant_id": user.tenant_id,
            "classification": document.classification,
            "reason": reason,
        },
    )

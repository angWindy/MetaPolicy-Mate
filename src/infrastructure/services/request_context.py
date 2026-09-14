from uuid import UUID

from src.application.common.interfaces.request_context import (
    RequestContext as RequestContextProtocol,
)
from src.domain.enums.audit_actor_type import (
    AuditActorType,
)


class RequestContext(
    RequestContextProtocol
):
    def __init__(
        self,
        claims: dict[str, object],
        headers: dict[str, str],
        ip_address: str | None,
        trace_id: str | None,
    ) -> None:
        self._claims = claims
        self._headers = headers
        self._ip_address = ip_address
        self._trace_id = trace_id

    @staticmethod
    def _parse_uuid(
        value: object | None,
    ) -> UUID | None:
        if value is None:
            return None

        try:
            return UUID(str(value))
        except (
            ValueError,
            TypeError,
        ):
            return None

    @property
    def user_id(
        self,
    ) -> UUID | None:
        value = (
            self._claims.get("sub")
            or self._claims.get(
                "http://schemas.xmlsoap.org/"
                "ws/2005/05/identity/claims/"
                "nameidentifier"
            )
        )

        return self._parse_uuid(value)

    @property
    def school_id(
        self,
    ) -> UUID | None:
        value = (
            self._claims.get("SchoolId")
            or self._claims.get("school_id")
        )

        return self._parse_uuid(value)

    @property
    def school_code(
        self,
    ) -> str | None:
        value = (
            self._claims.get("SchoolCode")
            or self._claims.get(
                "school_code"
            )
        )

        if value is None:
            return None

        return str(value)

    @property
    def user_type(
        self,
    ) -> AuditActorType:
        value = (
            self._claims.get("userType")
            or self._claims.get(
                "user_type"
            )
        )

        if value is not None:
            try:
                return AuditActorType(
                    int(str(value))
                )
            except (
                ValueError,
                TypeError,
            ):
                pass

        match value:
            case "TenantUser":
                return (
                    AuditActorType.SCHOOL_USER
                )

            case "PlatformUser":
                return (
                    AuditActorType.PLATFORM_USER
                )

            case _:
                return AuditActorType.SYSTEM

    @property
    def ip_address(
        self,
    ) -> str | None:
        return self._ip_address

    @property
    def user_agent(
        self,
    ) -> str | None:
        value = self._headers.get(
            "user-agent"
        )

        return value if value else None

    @property
    def device_id(
        self,
    ) -> str | None:
        value = self._headers.get(
            "x-device-id"
        )

        return value if value else None

    @property
    def trace_id(
        self,
    ) -> str | None:
        return self._trace_id
from uuid import UUID

from src.application.common.interfaces.current_user import (
    CurrentUser,
)


class CurrentUserService(CurrentUser):
    def __init__(
        self,
        claims: dict[str, object],
        is_authenticated: bool,
    ) -> None:
        self._claims = claims
        self._is_authenticated = (
            is_authenticated
        )

    @property
    def user_id(self) -> UUID | None:
        value = self._claims.get("sub")

        if value is None:
            return None

        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            return None

    @property
    def email(self) -> str | None:
        value = self._claims.get("email")

        if value is None:
            return None

        return str(value)

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated
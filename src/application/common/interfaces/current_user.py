from typing import Protocol
from uuid import UUID


class CurrentUser(Protocol):
    @property
    def user_id(self) -> UUID | None:
        ...

    @property
    def email(self) -> str | None:
        ...

    @property
    def is_authenticated(self) -> bool:
        ...
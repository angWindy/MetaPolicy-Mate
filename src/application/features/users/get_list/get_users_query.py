from dataclasses import dataclass


@dataclass(frozen=True)
class GetUsersQuery:
    search: str | None = None

    is_active: bool | None = None

    page: int = 1
    page_size: int = 20
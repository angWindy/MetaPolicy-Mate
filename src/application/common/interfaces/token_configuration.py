from typing import Protocol


class TokenConfiguration(Protocol):
    @property
    def access_token_minutes(self) -> int:
        ...

    @property
    def refresh_token_days(self) -> int:
        ...
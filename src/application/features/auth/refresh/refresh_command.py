from dataclasses import dataclass


@dataclass(frozen=True)
class RefreshCommand:
    refresh_token: str
    device_id: str
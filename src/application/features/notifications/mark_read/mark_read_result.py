from dataclasses import dataclass


@dataclass(frozen=True)
class MarkNotificationReadResult:
    success: bool
    unread_count: int

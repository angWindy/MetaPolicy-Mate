from dataclasses import dataclass


@dataclass(frozen=True)
class MarkAllNotificationsReadResult:
    marked_count: int

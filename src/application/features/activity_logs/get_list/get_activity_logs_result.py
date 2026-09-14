from dataclasses import dataclass

from src.application.features.activity_logs.common.activity_log_item import (
    ActivityLogItem,
)


@dataclass(frozen=True)
class GetActivityLogsResult:
    items: list[
        ActivityLogItem
    ]

    total: int

    page: int
    page_size: int
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.activity_logs.common.activity_log_item import (
    ActivityLogItem,
)
from src.application.features.activity_logs.get_list.get_activity_logs_query import (
    GetActivityLogsQuery,
)
from src.application.features.activity_logs.get_list.get_activity_logs_result import (
    GetActivityLogsResult,
)
from src.domain.repositories.user_activity_log_repository import (
    UserActivityLogRepository,
)


class GetActivityLogsHandler(
    RequestHandler[
        GetActivityLogsQuery,
        GetActivityLogsResult,
    ]
):
    def __init__(
        self,
        activity_log_repository: (
            UserActivityLogRepository
        ),
    ) -> None:
        self._repository = (
            activity_log_repository
        )

    async def handle(
        self,
        request: GetActivityLogsQuery,
    ) -> GetActivityLogsResult:
        items, total = await (
            self._repository
            .get_list(
                user_id=(
                    request.user_id
                ),
                request_name=(
                    request.request_name
                ),
                status=request.status,
                from_at=request.from_at,
                to_at=request.to_at,
                page=request.page,
                page_size=(
                    request.page_size
                ),
            )
        )

        return GetActivityLogsResult(
            items=[
                ActivityLogItem
                .from_entity(item)
                for item in items
            ],
            total=total,
            page=request.page,
            page_size=(
                request.page_size
            ),
        )
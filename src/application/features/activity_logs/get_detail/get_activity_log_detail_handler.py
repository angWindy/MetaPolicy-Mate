from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.activity_logs.common.activity_log_item import (
    ActivityLogItem,
)
from src.application.features.activity_logs.get_detail.get_activity_log_detail_query import (
    GetActivityLogDetailQuery,
)
from src.domain.repositories.user_activity_log_repository import (
    UserActivityLogRepository,
)


class GetActivityLogDetailHandler(
    RequestHandler[
        GetActivityLogDetailQuery,
        ActivityLogItem,
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
        request: (
            GetActivityLogDetailQuery
        ),
    ) -> ActivityLogItem:
        item = await (
            self._repository
            .get_by_id(
                request.log_id
            )
        )

        if item is None:
            raise NotFoundException(
                "Activity log not found."
            )

        return (
            ActivityLogItem
            .from_entity(item)
        )
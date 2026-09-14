from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.static_thresholds.get_history.get_static_threshold_history_query import (
    GetStaticThresholdHistoryQuery,
)
from src.application.features.static_thresholds.static_threshold_dto import (
    StaticThresholdDto,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)


class GetStaticThresholdHistoryHandler(
    RequestHandler[
        GetStaticThresholdHistoryQuery,
        list[StaticThresholdDto],
    ]
):
    def __init__(
        self,
        threshold_repository: (
            StaticThresholdRepository
        ),
    ) -> None:
        self._threshold_repository = (
            threshold_repository
        )

    async def handle(
        self,
        request: (
            GetStaticThresholdHistoryQuery
        ),
    ) -> list[
        StaticThresholdDto
    ]:
        key = (
            request.threshold_key
            .strip()
            .upper()
        )

        scope_key = (
            request.scope_key
            .strip()
            .upper()
        )

        items = await (
            self._threshold_repository
            .get_history(
                key,
                scope_key,
            )
        )

        return [
            StaticThresholdDto
            .from_entity(item)
            for item in items
        ]
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.static_thresholds.get_verified.get_verified_static_thresholds_query import (
    GetVerifiedStaticThresholdsQuery,
)
from src.application.features.static_thresholds.static_threshold_dto import (
    StaticThresholdDto,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)


class GetVerifiedStaticThresholdsHandler(
    RequestHandler[
        GetVerifiedStaticThresholdsQuery,
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
            GetVerifiedStaticThresholdsQuery
        ),
    ) -> list[
        StaticThresholdDto
    ]:
        items = await (
            self._threshold_repository
            .get_verified_current()
        )

        return [
            StaticThresholdDto
            .from_entity(item)
            for item in items
        ]
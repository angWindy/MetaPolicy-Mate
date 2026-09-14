from datetime import datetime
from uuid import uuid4

from src.application.common.interfaces.activity_log_service import (
    ActivityLogService as ActivityLogServiceProtocol,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.domain.entities.user_activity_log import (
    UserActivityLog,
)
from src.domain.repositories.user_activity_log_repository import (
    UserActivityLogRepository,
)


class ActivityLogService(
    ActivityLogServiceProtocol
):
    def __init__(
        self,
        activity_log_repository: (
            UserActivityLogRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._activity_log_repository = (
            activity_log_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def write(
        self,
        request_name: str,
        status: str,
        started_at: datetime,
        completed_at: datetime,
        request_context: (
            RequestContext | None
        ) = None,
        error_message: str | None = None,
    ) -> None:
        if status == "Failed":
            # Hủy dữ liệu business đã
            # flush nhưng chưa commit.
            #
            # Sau rollback mới được tạo
            # activity log của request lỗi.
            await (
                self._unit_of_work
                .rollback()
            )

        activity_log = UserActivityLog(
            id=uuid4(),

            school_id=(
                request_context.school_id
                if request_context
                else None
            ),

            user_id=(
                request_context.user_id
                if request_context
                else None
            ),

            request_name=request_name,
            status=status,

            trace_id=(
                request_context.trace_id
                if request_context
                else None
            ),

            ip_address=(
                request_context.ip_address
                if request_context
                else None
            ),

            device_id=(
                request_context.device_id
                if request_context
                else None
            ),

            user_agent=(
                request_context.user_agent
                if request_context
                else None
            ),

            error_message=(
                error_message
            ),

            started_at=started_at,
            completed_at=completed_at,
        )

        await (
            self._activity_log_repository
            .add(
                activity_log
            )
        )

        await (
            self._unit_of_work
            .save_changes()
        )
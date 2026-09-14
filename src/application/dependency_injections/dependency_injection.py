from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)
from src.application.common.pipeline.request_dispatcher import (
    RequestDispatcher,
)
from src.application.dependency_injections.request_handler_registration import (
    register_request_handlers,
)
from src.application.dependency_injections.validator_registration import (
    register_validators,
)


def add_application(
    container,
) -> None:
    register_request_handlers(
        container
    )

    register_validators(
        container
    )

    container.register_factory(
        RequestDispatcherProtocol,
        lambda container: RequestDispatcher(
            container
        ),
        scoped=True,
    )
import importlib
import inspect
import pkgutil
from typing import (
    Any,
    get_args,
    get_origin,
)

import src.application

from src.application.common.pipeline.decorators.audit_handler_decorator import (
    AuditHandlerDecorator,
)
from src.application.common.pipeline.decorators.logging_handler_decorator import (
    LoggingHandlerDecorator,
)
from src.application.common.pipeline.decorators.validation_handler_decorator import (
    ValidationHandlerDecorator,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)


def register_request_handlers(
    container: Any,
) -> None:
    for module_info in pkgutil.walk_packages(
        src.application.__path__,
        prefix=f"{src.application.__name__}.",
    ):
        module = importlib.import_module(
            module_info.name
        )

        for _, implementation in (
            inspect.getmembers(
                module,
                inspect.isclass,
            )
        ):
            if inspect.isabstract(
                implementation
            ):
                continue

            if (
                implementation.__module__
                != module.__name__
            ):
                continue

            handler_contract = (
                _get_request_handler_contract(
                    implementation
                )
            )

            if handler_contract is None:
                continue

            (
                request_type,
                response_type,
            ) = handler_contract

            container.register_request_handler(
                request_type=request_type,
                response_type=response_type,
                implementation=implementation,
                lifetime="transient",
            )

    container.decorate_request_handlers(
        ValidationHandlerDecorator
    )

    container.decorate_request_handlers(
        LoggingHandlerDecorator
    )

    container.decorate_request_handlers(
        AuditHandlerDecorator
    )


def _get_request_handler_contract(
    implementation: type,
) -> tuple[Any, Any] | None:
    for base in getattr(
        implementation,
        "__orig_bases__",
        (),
    ):
        origin = get_origin(
            base
        )

        if origin is not RequestHandler:
            continue

        arguments = get_args(
            base
        )

        if len(arguments) != 2:
            continue

        request_type = (
            arguments[0]
        )

        response_type = (
            arguments[1]
        )

        return (
            request_type,
            response_type,
        )

    return None
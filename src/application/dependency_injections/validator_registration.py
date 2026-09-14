import importlib
import inspect
import pkgutil
from typing import (
    Any,
    get_type_hints,
)

import src.application


def register_validators(
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

            request_type = (
                _get_validator_request_type(
                    implementation
                )
            )

            if request_type is None:
                continue

            container.register_validator(
                request_type=request_type,
                implementation=implementation,
            )


def _get_validator_request_type(
    implementation: type,
) -> type | None:
    validate = getattr(
        implementation,
        "validate",
        None,
    )

    if (
        validate is None
        or not callable(validate)
    ):
        return None

    signature = inspect.signature(
        validate
    )

    request_parameter = (
        signature.parameters.get(
            "request"
        )
    )

    if request_parameter is None:
        return None

    try:
        type_hints = get_type_hints(
            validate
        )
    except Exception:
        return None

    request_type = type_hints.get(
        "request"
    )

    if not inspect.isclass(
        request_type
    ):
        return None

    return request_type
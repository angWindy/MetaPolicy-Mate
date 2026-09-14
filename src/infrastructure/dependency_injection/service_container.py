import inspect
import logging
from collections.abc import Callable
from typing import Any


Factory = Callable[
    ["ServiceContainer"],
    Any,
]


class ServiceContainer:
    def __init__(
        self,
    ) -> None:
        self._scoped: dict[
            Any,
            Factory,
        ] = {}

        self._transient: dict[
            Any,
            Factory,
        ] = {}

        self._request_handlers: dict[
            type,
            tuple[
                type,
                type,
                str,
            ],
        ] = {}

        self._handler_decorators: list[
            type
        ] = []

        self._validators: dict[
            type,
            list[type],
        ] = {}

        self._scope_cache: dict[
            Any,
            Any,
        ] = {}

    def register_scoped(
        self,
        service_type: Any,
        implementation: Any,
    ) -> None:
        self._scoped[
            service_type
        ] = self._build_factory(
            implementation
        )

    def register_transient(
        self,
        service_type: Any,
        implementation: Any,
    ) -> None:
        self._transient[
            service_type
        ] = self._build_factory(
            implementation
        )

    def register_instance(
        self,
        service_type: Any,
        instance: Any,
    ) -> None:
        self._scoped[
            service_type
        ] = lambda _: instance

    def register_factory(
        self,
        service_type: Any,
        factory: Factory,
        scoped: bool = True,
    ) -> None:
        if scoped:
            self._scoped[
                service_type
            ] = factory
        else:
            self._transient[
                service_type
            ] = factory

    def register_request_handler(
        self,
        request_type: type,
        response_type: type,
        implementation: type,
        lifetime: str = "transient",
    ) -> None:
        self._request_handlers[
            request_type
        ] = (
            implementation,
            response_type,
            lifetime,
        )

    def decorate_request_handlers(
        self,
        decorator_type: type,
    ) -> None:
        self._handler_decorators.append(
            decorator_type
        )

    def register_validator(
        self,
        request_type: type,
        implementation: type,
    ) -> None:
        implementations = (
            self._validators.setdefault(
                request_type,
                [],
            )
        )

        implementations.append(
            implementation
        )

    def get_required(
        self,
        service_type: Any,
    ) -> Any:
        if (
            service_type
            in self._scope_cache
        ):
            return self._scope_cache[
                service_type
            ]

        if service_type in self._scoped:
            instance = self._scoped[
                service_type
            ](
                self
            )

            self._scope_cache[
                service_type
            ] = instance

            return instance

        if (
            service_type
            in self._transient
        ):
            return self._transient[
                service_type
            ](
                self
            )

        raise KeyError(
            "Service not registered: "
            f"{service_type}"
        )

    def get_required_handler(
        self,
        request_type: type,
    ) -> Any:
        registration = (
            self._request_handlers.get(
                request_type
            )
        )

        if registration is None:
            raise KeyError(
                "Request handler not "
                f"registered: "
                f"{request_type}"
            )

        (
            implementation,
            _,
            _,
        ) = registration

        handler = (
            self._create_instance(
                implementation
            )
        )

        for decorator_type in (
            self._handler_decorators
        ):
            handler = (
                self._create_decorator(
                    decorator_type,
                    handler,
                    request_type,
                )
            )

        return handler

    def create_scope(
        self,
    ) -> "ServiceContainer":
        scope = ServiceContainer()

        scope._scoped = (
            self._scoped.copy()
        )

        scope._transient = (
            self._transient.copy()
        )

        scope._request_handlers = (
            self._request_handlers.copy()
        )

        scope._handler_decorators = list(
            self._handler_decorators
        )

        scope._validators = {
            request_type: list(
                implementations
            )
            for (
                request_type,
                implementations,
            ) in self._validators.items()
        }

        return scope

    def _build_factory(
        self,
        implementation: Any,
    ) -> Factory:
        if inspect.isclass(
            implementation
        ):
            return (
                lambda container:
                container._create_instance(
                    implementation
                )
            )

        return (
            lambda _:
            implementation
        )

    def _create_instance(
        self,
        implementation: type,
    ) -> Any:
        # Use get_type_hints to resolve string/forward-reference annotations
        # (e.g. "Settings" → actual Settings class). inspect.signature
        # returns the raw annotation which may be a string in postponed-
        # evaluation or re-export scenarios, causing get_required() to look
        # up "Settings" (string) instead of Settings (class).
        try:
            type_hints = __import__("typing").get_type_hints(
                implementation.__init__
            )
        except Exception:  # noqa: BLE001
            # Fall back to raw signature annotations.
            type_hints = {}

        arguments: dict[
            str,
            Any,
        ] = {}

        for (
            name,
            parameter,
        ) in inspect.signature(
            implementation.__init__
        ).parameters.items():
            if name == "self":
                continue

            if parameter.kind in (
                inspect.Parameter
                .VAR_POSITIONAL,
                inspect.Parameter
                .VAR_KEYWORD,
            ):
                continue

            # Resolve the annotation: prefer get_type_hints (resolves strings
            # to classes), fall back to the raw annotation.
            annotation = type_hints.get(
                name,
                parameter.annotation,
            )

            if (
                annotation
                is inspect.Parameter.empty
            ):
                if (
                    parameter.default
                    is not inspect.Parameter.empty
                ):
                    continue

                raise TypeError(
                    "Missing type annotation "
                    f"for "
                    f"{implementation.__name__}"
                    f".{name}"
                )

            # Skip optional parameters that have a default value and their
            # annotation is not a concrete class (e.g. dict[str,str]|None,
            # Optional[str], Union[...], etc.). These use the default value
            # rather than being resolved from the container.
            if (
                parameter.default
                is not inspect.Parameter.empty
                and not isinstance(annotation, type)
            ):
                continue

            arguments[
                name
            ] = self.get_required(
                annotation
            )

        return implementation(
            **arguments
        )

    def _create_decorator(
        self,
        decorator_type: type,
        inner: Any,
        request_type: type,
    ) -> Any:
        if (
            decorator_type.__name__
            == "ValidationHandlerDecorator"
        ):
            validators = (
                self._get_validators(
                    request_type
                )
            )

            return decorator_type(
                inner,
                validators,
            )

        if (
            decorator_type.__name__
            == "AuditHandlerDecorator"
        ):
            is_auditable_request = all(
                hasattr(
                    request_type,
                    name,
                )
                for name in (
                    "action",
                    "entity",
                    "entity_id",
                )
            )

            if not is_auditable_request:
                return inner

            from src.application.common.interfaces.audit_service import (
                AuditService,
            )
            from src.application.common.interfaces.request_context import (
                RequestContext,
            )

            audit_service = (
                self.get_required(
                    AuditService
                )
            )

            request_context = (
                self.get_required(
                    RequestContext
                )
            )

            return decorator_type(
                inner,
                audit_service,
                request_context,
            )

        if (
            decorator_type.__name__
                == "LoggingHandlerDecorator"
        ):
            from src.application.common.interfaces.activity_log_service import (
                ActivityLogService,
            )
            from src.application.common.interfaces.request_context import (
                RequestContext,
            )

            logger = logging.getLogger(
                type(inner).__name__
            )

            activity_log_service = (
                self.get_required(
                    ActivityLogService
                )
            )

            request_context = None

            if (
                RequestContext
                in self._scope_cache
                or RequestContext
                in self._scoped
            ):
                try:
                    request_context = (
                        self.get_required(
                            RequestContext
                        )
                    )
                except KeyError:
                    request_context = None

            return decorator_type(
                inner,
                logger,
                activity_log_service,
                request_context,
            )

        return decorator_type(
            inner
        )

    def _get_validators(
        self,
        request_type: type,
    ) -> list[Any]:
        implementations = (
            self._validators.get(
                request_type,
                [],
            )
        )

        return [
            self._create_instance(
                implementation
            )
            for implementation
            in implementations
        ]
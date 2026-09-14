from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)


_root_container: ServiceContainer | None = None


def set_root_container(
    container: ServiceContainer,
) -> None:
    global _root_container

    _root_container = container


def get_root_container() -> ServiceContainer:
    if _root_container is None:
        raise RuntimeError(
            "Root container has not been configured."
        )

    return _root_container
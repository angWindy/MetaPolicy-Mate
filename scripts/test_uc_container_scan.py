from application.dependency_injections.dependency_injection import (
    add_application,
)
from application.features.auth.login.login_command import (
    LoginCommand,
)
from application.features.auth.logout.logout_command import (
    LogoutCommand,
)
from application.features.auth.refresh.refresh_command import (
    RefreshCommand,
)
from infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)


def main() -> None:
    container = ServiceContainer()

    add_application(
        container
    )

    print("REGISTERED HANDLERS")

    for request_type in (
        LoginCommand,
        RefreshCommand,
        LogoutCommand,
    ):
        registered = (
            request_type
            in container._request_handlers
        )

        print(
            f"{request_type.__name__}:",
            registered,
        )

        if not registered:
            raise RuntimeError(
                "Handler not registered: "
                f"{request_type.__name__}"
            )

    print()
    print(
        "Container handler scan test PASS"
    )


main()
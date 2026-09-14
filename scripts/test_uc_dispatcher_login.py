import asyncio
import sys

from application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)
from application.dependency_injections.dependency_injection import (
    add_application,
)
from application.features.auth.login.login_command import (
    LoginCommand,
)
from config import get_settings
from infrastructure.dependency_injection.dependency_injection import (
    add_infrastructure,
)
from infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    settings = get_settings()

    session_factory = TenantSessionFactory()

    session = session_factory.create(
        settings.database_url
    )

    try:
        container = ServiceContainer()

        # 1. Scan/register Application handlers
        add_application(
            container
        )

        # 2. Register Persistence + Auth
        add_infrastructure(
            container=container,
            settings=settings,
            session=session,
        )

        # 3. Resolve dispatcher
        dispatcher = container.get_required(
            RequestDispatcherProtocol
        )

        # 4. Send command through pipeline
        result = await dispatcher.send(
            LoginCommand(
                email="admin@p234.demo",
                password="P234@123",
                device_id=(
                    "dispatcher-login-device"
                ),
            )
        )

        print("DISPATCHER LOGIN")
        print(
            "Access token generated:",
            bool(result.access_token),
        )
        print(
            "Refresh token generated:",
            bool(result.refresh_token),
        )
        print(
            "Expires at:",
            result.expires_at,
        )

        if not result.access_token:
            raise RuntimeError(
                "Access token was not generated."
            )

        if not result.refresh_token:
            raise RuntimeError(
                "Refresh token was not generated."
            )

        print()
        print(
            "RequestDispatcher Login "
            "integration test PASS"
        )

    finally:
        await session.close()
        await session_factory.dispose()


asyncio.run(main())
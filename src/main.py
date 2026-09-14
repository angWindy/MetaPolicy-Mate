import asyncio
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import (
    CORSMiddleware,
)


from src.config import get_settings

from src.application.dependency_injections.dependency_injection import (
    add_application,
)

from src.infrastructure.audit.audit_outbox_worker import (
    AuditOutboxWorker,
)
from src.infrastructure.dependency_injection.composition_root import (
    set_root_container,
)
from src.infrastructure.dependency_injection.dependency_injection import (
    add_infrastructure,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)

try:
    from src.infrastructure.ai.rag_runtime import get_p234_rag_runtime

    _RUNTIME_IMPORT_ERROR: Exception | None = None
except ImportError as _runtime_import_error:  # pragma: no cover - import guard
    get_p234_rag_runtime = None  # type: ignore[assignment]
    _RUNTIME_IMPORT_ERROR = _runtime_import_error

from src.presentation.api.dependencies.request_scope import (
    get_tenant_session_factory,
)
from src.presentation.api.exception_handlers.exception_handler import (
    exception_handler,
)
from src.presentation.api.router import (
    api_router,
)


settings = get_settings()

container = ServiceContainer()

add_application(
    container
)

add_infrastructure(
    container,
    settings,
)

set_root_container(
    container
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    print(
        f"Starting {settings.app_name} "
        f"in {settings.app_env} mode"
    )

    tenant_session_factory = (
        get_tenant_session_factory()
    )

    audit_session_factory = (
        tenant_session_factory
        .get_session_factory(
            settings.database_url
        )
    )

    audit_worker = (
        AuditOutboxWorker(
            audit_session_factory
        )
    )

    stop_event = asyncio.Event()

    worker_task = asyncio.create_task(
        audit_worker.execute(
            stop_event
        )
    )

    # Eagerly warm up the reranker so the first user query does not pay the
    # 3-second model-load penalty. Errors are logged but do not block startup.
    if get_p234_rag_runtime is not None:
        try:
            runtime = await asyncio.to_thread(get_p234_rag_runtime)
            print("Reranker warmup complete (eager startup).")
        except Exception as exc:  # noqa: BLE001 - startup must not fail
            print(f"Reranker warmup skipped: {type(exc).__name__}: {exc}")

    try:
        yield

    finally:
        stop_event.set()

        await worker_task

        await (
            tenant_session_factory
            .dispose()
        )

        print(
            "Shutting down..."
        )


app = FastAPI(
    title="AI20K Agent",
    description=(
        "AI Agent built with LangGraph"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(
    Exception,
    exception_handler,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        settings.cors_origins.split(
            ","
        )
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Clean Architecture API
app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "env": settings.app_env,
    }
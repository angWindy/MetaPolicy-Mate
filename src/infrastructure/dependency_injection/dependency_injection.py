from src.application.common.interfaces.jwt_token_service import (
    JwtTokenService as JwtTokenServiceProtocol,
)
from src.application.common.interfaces.password_hasher import (
    PasswordHasher as PasswordHasherProtocol,
)
from src.application.common.interfaces.refresh_token_service import (
    RefreshTokenService as RefreshTokenServiceProtocol,
)
from src.config import Settings
from src.infrastructure.auth.jwt_settings import (
    JwtSettings,
)
from src.infrastructure.auth.jwt_token_service import (
    JwtTokenService,
)
from src.infrastructure.auth.refresh_token_service import (
    RefreshTokenService,
)
from src.infrastructure.security.password_hasher import (
    PasswordHasher,
)

from pathlib import Path

from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.infrastructure.storage.local_file_storage import (
    LocalFileStorage,
)
from src.infrastructure.storage.object_key import (
    ObjectKeyBuilder,
)
from src.infrastructure.storage.r2_file_storage import (
    R2FileStorage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.infrastructure.storage.local_file_storage import (
    LocalFileStorage,
)
from src.infrastructure.storage.object_key import (
    ObjectKeyBuilder,
)
from src.infrastructure.storage.r2_file_storage import (
    R2FileStorage,
)


_R2_PLACEHOLDER_TOKENS = {
    "",
    "placeholder_key_id",
    "placeholder-bucket",
}


def _is_r2_configured(settings: Settings) -> bool:
    """Treat the .env placeholders as 'R2 not configured' so we silently
    fall back to LocalFileStorage during local development."""
    return (
        bool(settings.r2_endpoint)
        and settings.r2_access_key_id
        not in _R2_PLACEHOLDER_TOKENS
        and settings.r2_bucket_name
        not in _R2_PLACEHOLDER_TOKENS
    )


def add_infrastructure(
    container,
    settings: Settings,
) -> None:
    container.register_instance(
        Settings,
        settings,
    )

    jwt_settings = JwtSettings(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        secret_key=settings.jwt_secret_key,
        access_token_minutes=(
            settings.jwt_access_token_minutes
        ),
        refresh_token_days=(
            settings.jwt_refresh_token_days
        ),
    )

    container.register_instance(
        JwtSettings,
        jwt_settings,
    )

    container.register_scoped(
        PasswordHasherProtocol,
        PasswordHasher,
    )

    container.register_scoped(
        RefreshTokenServiceProtocol,
        RefreshTokenService,
    )

    container.register_scoped(
        JwtTokenServiceProtocol,
        JwtTokenService,
    )

    if _is_r2_configured(settings):
        # R2 Cloudflare is the primary object store for the demo;
        # LocalFileStorage is only kept as a fallback when R2 env vars
        # are placeholders (e.g. on a developer's local machine without
        # R2 credentials).
        file_storage_factory = lambda _: R2FileStorage(
            endpoint=settings.r2_endpoint,
            access_key_id=(
                settings.r2_access_key_id
            ),
            secret_access_key=(
                settings.r2_secret_access_key
            ),
            bucket_name=(
                settings.r2_bucket_name
            ),
        )
    else:
        file_storage_factory = lambda _: LocalFileStorage(
            root_dir=PROJECT_ROOT / "data" / "storage",
        )

    container.register_factory(
        FileStorage,
        file_storage_factory,
        scoped=True,
    )

    # ObjectKeyBuilder is cheap to construct; keep it as a scoped
    # singleton so every request in the same scope reuses the same
    # tenant_code resolution rules.
    container.register_scoped(
        ObjectKeyBuilder,
        ObjectKeyBuilder,
    )
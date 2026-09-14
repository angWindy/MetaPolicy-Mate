import bcrypt

from src.application.common.interfaces.password_hasher import (
    PasswordHasher as PasswordHasherProtocol,
)


class PasswordHasher(PasswordHasherProtocol):
    def hash_password(
        self,
        password: str,
    ) -> str:
        password_bytes = password.encode("utf-8")

        hashed_password = bcrypt.hashpw(
            password_bytes,
            bcrypt.gensalt(),
        )

        return hashed_password.decode("utf-8")

    def verify_password(
        self,
        password: str,
        stored_hash: str,
    ) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            stored_hash.encode("utf-8"),
        )
class ForbiddenException(Exception):
    def __init__(
        self,
        message: str = "You do not have permission to perform this action.",
    ) -> None:
        super().__init__(message)
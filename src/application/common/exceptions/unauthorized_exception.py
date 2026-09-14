class UnauthorizedException(Exception):
    def __init__(
        self,
        message: str = "You are not authenticated.",
    ) -> None:
        super().__init__(message)
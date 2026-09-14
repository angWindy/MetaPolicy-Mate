class TooManyRequestsException(
    Exception
):
    def __init__(
        self,
        message: str,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(
            message
        )

        self.retry_after_seconds = (
            retry_after_seconds
        )
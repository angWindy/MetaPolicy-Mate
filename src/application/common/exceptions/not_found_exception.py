class NotFoundException(Exception):
    def __init__(
        self,
        message_or_name: str,
        key: object | None = None,
    ) -> None:
        if key is None:
            message = message_or_name
        else:
            message = (
                f"{message_or_name} with key '{key}' was not found."
            )

        super().__init__(message)
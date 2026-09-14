class ConflictException(Exception):
    def __init__(
        self,
        message: str = (
            "The request conflicts with the current state "
            "of the resource."
        ),
    ) -> None:
        super().__init__(message)
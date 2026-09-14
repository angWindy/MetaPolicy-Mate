from uuid import UUID


class DeleteUserCommand:
    def __init__(
        self,
        user_id: UUID,
    ) -> None:
        self.user_id = user_id

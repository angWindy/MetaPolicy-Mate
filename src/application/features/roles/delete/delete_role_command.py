from uuid import UUID


class DeleteRoleCommand:
    def __init__(
        self,
        role_id: UUID,
    ) -> None:
        self.role_id = role_id

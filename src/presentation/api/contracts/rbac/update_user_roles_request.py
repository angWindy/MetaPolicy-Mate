from uuid import UUID

from pydantic import BaseModel


class UpdateUserRolesRequest(
    BaseModel
):
    role_ids: list[UUID]
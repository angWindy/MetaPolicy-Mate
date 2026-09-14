from uuid import UUID

from pydantic import BaseModel


class UpdateRolePermissionsRequest(
    BaseModel
):
    permission_ids: list[UUID]
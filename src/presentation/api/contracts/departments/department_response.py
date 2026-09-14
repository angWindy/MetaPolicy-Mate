from uuid import UUID

from pydantic import BaseModel


class DepartmentResponse(
    BaseModel
):
    id: UUID
    code: str
    name: str
    is_active: bool
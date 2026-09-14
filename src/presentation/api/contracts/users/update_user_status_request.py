from pydantic import BaseModel


class UpdateUserStatusRequest(
    BaseModel
):
    is_active: bool
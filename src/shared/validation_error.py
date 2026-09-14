from pydantic import BaseModel


class ValidationError(BaseModel):
    property_name: str = ""
    error_message: str = ""
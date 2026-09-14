from datetime import date

from pydantic import BaseModel


class UpdateSectionVersionEffectivenessRequest(
    BaseModel
):
    effective_from: date

    effective_to: date | None = None

    is_current: bool
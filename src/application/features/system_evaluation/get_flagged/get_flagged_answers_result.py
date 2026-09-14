from dataclasses import dataclass

from src.application.features.system_evaluation.get_flagged.flagged_answer_item import (
    FlaggedAnswerItem,
)


@dataclass(frozen=True)
class GetFlaggedAnswersResult:
    items: list[FlaggedAnswerItem]
    total: int
    page: int
    page_size: int
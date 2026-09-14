from dataclasses import dataclass


@dataclass(frozen=True)
class GetSystemEvaluationSummaryResult:
    total_answers: int
    total_feedback: int

    flagged_answers: int
    reviewed_answers: int

    correct_answers: int
    incorrect_answers: int
    partially_correct_answers: int

    feedback_rate: float
    confirmed_error_rate: float
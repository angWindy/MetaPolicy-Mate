from dataclasses import dataclass


@dataclass(frozen=True)
class GetStaticThresholdHistoryQuery:
    threshold_key: str
    scope_key: str
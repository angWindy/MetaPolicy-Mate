from typing import Protocol


class AuditPayloadProvider(Protocol):
    def get_payload(
        self,
    ) -> object:
        ...
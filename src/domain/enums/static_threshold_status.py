from enum import Enum


class StaticThresholdStatus(
    str,
    Enum,
):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
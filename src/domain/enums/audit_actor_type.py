from enum import Enum


class AuditActorType(Enum):
    PLATFORM_USER = 0
    SCHOOL_USER = 1
    SYSTEM = 2
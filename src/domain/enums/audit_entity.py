from enum import Enum


class AuditEntity(Enum):
    SCHOOL = 0
    PLAN = 1
    SUBSCRIPTION = 2

    PLATFORM_USER = 3
    SCHOOL_USER = 4

    TEACHER = 5
    STUDENT = 6

    ROLE = 7
    FEATURE = 8

    PERMISSION = 9

    REGULATORY_DOCUMENT = 10
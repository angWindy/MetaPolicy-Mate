from enum import Enum


class DocumentReferenceNature(
    str,
    Enum,
):
    MANDATORY = "mandatory"
    REFERENCE = "reference"
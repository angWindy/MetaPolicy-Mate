from enum import Enum


class DocumentRelationType(
    str,
    Enum,
):
    AMENDS = "amends"
    SUPERSEDES = "supersedes"
    REFERENCES = "references"
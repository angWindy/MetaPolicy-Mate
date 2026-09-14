from enum import Enum


class ApplicationScopeType(
    str,
    Enum,
):
    WHOLE_DOCUMENT = "whole_document"
    SPECIFIC_CONTENT = "specific_content"
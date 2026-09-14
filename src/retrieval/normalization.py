"""Vietnamese-aware text normalization for lexical retrieval.

The standard regex tokeniser ``re.findall(r"\w+", text)`` matches
Vietnamese word characters but does not collapse diacritics. As a
result, queries like ``"cham cong"`` (no diacritics) do not match chunks
that contain ``"chấm công"``. This module exposes a ``vn_tokenize``
function that strips diacritics via NFD so a query without accents
matches text with accents and vice versa.

The flag ``VN_NORMALIZE_ENABLED`` (default False to preserve existing
behaviour during the transition) controls whether ``vn_tokenize`` is
used in place of the legacy ``re.findall`` tokeniser. Flip it on after
validating the change on the eval set.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from typing import Callable

import os


# Same character class as the legacy tokeniser plus the full
# Vietnamese diacritic range (À-ỹ, both upper and lower).
_WORD_RE = re.compile(r"[\wÀ-ỹ]+", flags=re.UNICODE)


@functools.lru_cache(maxsize=8192)
def _strip_diacritics(text: str) -> str:
    """Decompose to NFD then drop all combining marks (Mn category)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def vn_tokenize(text: str) -> list[str]:
    """Tokenise Vietnamese text into lowercase, diacritic-stripped tokens.

    Example:
        >>> vn_tokenize("Chấm công giảng viên")
        ['cham', 'cong', 'giang', 'vien']

    Returns an empty list for non-string input so callers can keep using
    ``if not tokens`` without a separate type guard.
    """
    if not isinstance(text, str):
        return []
    normalized = _strip_diacritics(text.casefold())
    return _WORD_RE.findall(normalized)


def is_vn_normalize_enabled() -> bool:
    """Read the env flag at call time so runtime changes are honoured."""
    return os.environ.get("VN_NORMALIZE_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


# Cached tokenizer selection — ``tokenize_fn`` returns the active
# tokeniser based on the runtime flag.
@functools.cache
def tokenize_fn() -> Callable[[str], list[str]]:
    """Return the active tokeniser for lexical retrieval.

    When ``VN_NORMALIZE_ENABLED`` is true, returns ``vn_tokenize``;
    otherwise returns the legacy regex tokenizer ``re.findall(r"\\w+", ...)``.
    The legacy tokenizer keeps the historical BM25 score distribution
    stable while the new tokenizer is being validated.
    """
    if is_vn_normalize_enabled():
        return vn_tokenize
    # Lazy import to avoid pulling this module when flag is off
    import re as _re
    _legacy = _re.compile(r"\w+", flags=_re.UNICODE)
    return lambda text: _legacy.findall(text.lower())

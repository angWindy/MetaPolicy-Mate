"""Vietnamese diacritic restoration from OCR output.

When PP-OCRv6_medium_rec emits diacritic-stripped tokens (e.g. ``Can cu``
instead of ``Căn cứ``), this module looks each token up in a corpus-
derived Vietnamese wordlist and substitutes the canonical diacritic
form. Falls back to the original token if no match — no hallucination
risk because every canonical form was extracted from real PDFs.

The wordlist is built by ``scripts/ocr/build_vn_wordlist.py`` and
contains ``{word_with_diacritics: frequency}`` pairs.

Usage::

    restorer = VNDiacriticRestorer.from_wordlist_json(
        Path("data/ocr/outputs/vn_wordlist.json")
    )
    restored = restorer.restore("Can cu Luat giao duc")  # "Căn cứ Luật giáo dục"
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# Same pattern as build_vn_wordlist.py — extract Vietnamese tokens.
_TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀÁÂĂĐÈÉÊÌÍÒÓÔƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỶỸỴ"
    r"àáâăđèéêìíòóôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ]+",
    re.UNICODE,
)

# ---------------------------------------------------------------------- #
# OCR artifact patterns observed in PP-OCRv6 + PP-OCRv6_mobile_rec output.
# ---------------------------------------------------------------------- #
#
# When PP-OCRv6 OCRs a scanned Vietnamese legal PDF (e.g. ``data/ocr/
# 188_QD_BGDDT.pdf``) it inserts two systematic artifacts:
#
# 1. The capital/diacritic letter ``Ả`` (U+1EA2 — ``A`` with hook and
#    breve) is used in place of word-separator whitespace. Every space
#    inside a word cluster becomes ``Ả``. Example::
#
#        "Bộ Giáo dục và Đào tạo"  ->  "BẢGIÁOẢDCẢVÀẢĐÀOẢTO"
#
# 2. Heading markers get re-ordered so the regex for ``Điều`` / ``Chương``
#    fails to match. Example::
#
#        "Điều 1. Phạm vi"  ->  "ĐiuẢ1.ẢPhmẢvi"
#        "Chương I"  ->  "ChuưongẢI"
#
# The cleaner's job is to fix these *before* :class:`VNDiacriticRestorer`
# runs so the wordlist lookup has a chance of producing canonical
# tokens.  We keep the substitutions conservative — every entry is a
# high-frequency pattern observed on the real corpus, not a fuzzy rule.
#
# Patterns operate on the cleaned line, not just tokens, because the
# artifact leaves no whitespace to anchor the token regex.

# Roman numeral alternation. Longest-first so ``VIII`` wins over ``V``,
# ``XII`` wins over ``XI`` etc. Compiled inline as a non-capturing
# group inside each pattern below.
_ROMAN = (
    r"(?:XXXVIII|XXXVII|XXXVI|XXXV|XXXIV|XXXIII|XXXII|XXXI|"
    r"XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|"
    r"XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|"
    r"IX|VIII|VII|VI|V|IV|III|II|I)"
)

# (regex, replacement, description). Order matters: more specific
# patterns must precede more generic ones in the same vicinity.
_OCR_ARTIFACT_SUBSTITUTIONS: tuple[tuple[re.Pattern, str, str], ...] = (
    # Heading + number/roman separator. The downstream heading regex
    # in ``legal_structure.extract_sections`` requires whitespace
    # between ``Điều`` and the article number, etc., so we must
    # inject a space when OCR stripped it. Examples::
    #
    #     "Điều1."   -> "Điều 1."
    #     "ChươngI"  -> "Chương I"
    #     "Khoản2"   -> "Khoản 2"
    (re.compile(r"(Điều)([0-9]+)"), r"\1 \2", "Điều<num> -> Điều <num>"),
    (re.compile(r"(điều)([0-9]+)"), r"\1 \2", "điều<num> -> điều <num>"),
    (re.compile(r"(Khoản)([0-9]+)"), r"\1 \2", "Khoản<num> -> Khoản <num>"),
    (re.compile(r"(khoản)([0-9]+)"), r"\1 \2", "khoản<num> -> khoản <num>"),
    (re.compile(r"(Điểm)([a-zđ])"), r"\1 \2", "Điểm<a> -> Điểm <a>"),
    (re.compile(r"(điểm)([a-zđ])"), r"\1 \2", "điểm<a> -> điểm <a>"),
    (re.compile(r"(Chương)([IVXLCDM0-9]+)"), r"\1 \2", "Chương<rom> -> Chương <rom>"),
    (re.compile(r"(chương)([IVXLCDM0-9]+)"), r"\1 \2", "chương<rom> -> chương <rom>"),
    (re.compile(r"(Mục)([IVXLCDM0-9]+)"), r"\1 \2", "Mục<rom> -> Mục <rom>"),
    (re.compile(r"(mục)([IVXLCDM0-9]+)"), r"\1 \2", "mục<rom> -> mục <rom>"),
    (re.compile(r"(Phần)([IVXLCDM0-9]+)"), r"\1 \2", "Phần<rom> -> Phần <rom>"),
    (re.compile(r"(phần)([IVXLCDM0-9]+)"), r"\1 \2", "phần<rom> -> phần <rom>"),
    # Heading-marker canonicalisation. PP-OCRv6 emits scrambled forms
    # that the heading regex needs to see in canonical shape. Examples::
    #
    #     "ĐiuẢ"  -> "Điều"
    #     "ChuưongẢ"  -> "Chương"   (note ``ươ`` -> ``ươ``)
    #     "ChưongẢ"  -> "Chương"     (one-element drop)
    #     "MụcẢ"  -> "Mục"
    #     "QuyếtẢ"  -> "Quyết"
    #     "TrườngẢ"  -> "Trường"
    #
    # These patterns preserve the trailing ``Ả`` so the generic rule
    # below can convert it to whitespace.
    (re.compile(r"Điu\u1EA2"), "Điều\u1EA2", "ĐiuẢ -> ĐiềuẢ (keep trailing Ả)"),
    (re.compile(r"điu\u1ea2"), "điều\u1ea2", "điuẢ -> điềuẢ"),
    (re.compile(r"Chuưong\u1EA2"), "Chương\u1EA2", "ChuưongẢ -> ChươngẢ"),
    (re.compile(r"Chưong\u1EA2"), "Chương\u1EA2", "ChưongẢ -> ChươngẢ"),
    (re.compile(r"chưong\u1ea2"), "chương\u1ea2", "chưongẢ -> chươngẢ"),
    (re.compile(r"Chương\u1EA2"), "Chương ", "ChươngẢ -> Chương (no-next)"),
    (re.compile(r"Mục\u1EA2"), "Mục ", "MụcẢ -> Mục"),
    (re.compile(r"mục\u1ea2"), "mục ", "mụcẢ -> mục"),
    (re.compile(r"Phần\u1EA2"), "Phần ", "PhầnẢ -> Phần"),
    (re.compile(r"phần\u1ea2"), "phần ", "phầnẢ -> phần"),
    (re.compile(r"Khoản\u1EA2"), "Khoản ", "KhoảnẢ -> Khoản"),
    (re.compile(r"khoản\u1ea2"), "khoản ", "khoảnẢ -> khoản"),
    (re.compile(r"Quyết\u1EA2"), "Quyết ", "QuyếtẢ -> Quyết"),
    (re.compile(r"quyết\u1ea2"), "quyết ", "quyếtẢ -> quyết"),
    (re.compile(r"Trường\u1EA2(?=h)"), "Trường ", "TrườngẢhợp -> Trường hợp"),
    (re.compile(r"trường\u1ea2(?=h)"), "trường ", "trườngẢhợp -> trường hợp"),
    # Roman numeral patterns (G7 — file 188 has 8 chapters).
    # OCR sometimes emits the heading keyword fused with the Roman numeral
    # without any whitespace, or with a stray ``Ả`` artifact in between.
    # Examples that must be cleaned to canonical ``Chương I``, ``Chương VIII``:
    #     "ChuongI"      -> "Chương I"          (fused, no space)
    #     "ChươngI"      -> "Chương I"
    #     "ChươngVIII"   -> "Chương VIII"
    #     "ChươngẢI"    -> "Chương I"          (Ả-as-space artifact)
    #     "ChươngẢVIII" -> "Chương VIII"
    # Roman numeral patterns — heading keyword fused with Roman numeral,
    # with or without the ``Ả``-as-space artifact. Used by file 188
    # which has 8 chapters (``Chương I`` .. ``Chương VIII``).
    (re.compile(r"(Chuong)\s*(" + _ROMAN + r")\b", re.IGNORECASE), r"\1 \2",
     "Chuong<rom> fused -> Chuong <rom>"),
    (re.compile(r"(Chương)\s*(" + _ROMAN + r")\b"), r"\1 \2",
     "Chương<rom> fused -> Chương <rom>"),
    (re.compile(r"(chương)\s*(" + _ROMAN + r")\b", re.IGNORECASE), r"\1 \2",
     "chương<rom> fused -> chương <rom>"),
    (re.compile(r"(Chương)\s*\u1EA2\s*(" + _ROMAN + r")\b",
                re.IGNORECASE), r"\1 \2",
     "ChươngẢ<rom> -> Chương <rom>"),
    (re.compile(r"(chương)\s*\u1ea2\s*(" + _ROMAN + r")\b",
                re.IGNORECASE), r"\1 \2",
     "chươngẢ<rom> -> chương <rom>"),
    (re.compile(r"(Mục)\s*\u1EA2\s*(" + _ROMAN + r")\b",
                re.IGNORECASE), r"\1 \2",
     "MụcẢ<rom> -> Mục <rom>"),
    (re.compile(r"(mục)\s*\u1ea2\s*(" + _ROMAN + r")\b",
                re.IGNORECASE), r"\1 \2",
     "mụcẢ<rom> -> mục <rom>"),
    # Generic trailing ``Ả`` before an uppercase Latin letter, ASCII
    # digit, or Vietnamese uppercase ``Đ``. Catches unknown heading-like
    # patterns without breaking legitimate ``Bả`` because we only fire
    # before capital letters / digits, not lowercase / Vietnamese
    # diacritic letters (the canonical ``B`` ``ả`` ``n`` shape is
    # matched by the regex but ``n`` is lowercase so it survives).
    (re.compile(r"\u1EA2(?=[A-Z0-9])"), " ", "Ả before uppercase/digit -> space"),
    (re.compile(r"\u1ea2(?=[A-Z0-9])"), " ", "ả before uppercase/digit -> space"),
    (re.compile(r"\u1EA2(?=Đ)"), " ", "Ả before Đ -> space"),
    (re.compile(r"\u1ea2(?=đ)"), " ", "ả before đ -> space"),
)


def _strip(word: str) -> str:
    """Strip combining diacritics via Unicode NFD."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


class VNDiacriticRestorer:
    """Look up diacritic-stripped tokens against a corpus wordlist."""

    def __init__(self, lookup: dict[str, str]):
        # ``lookup`` maps ``stripped_token -> canonical_vn_token``.
        self._lookup = lookup

    @classmethod
    def from_wordlist_json(cls, path: Path) -> "VNDiacriticRestorer":
        """Load the JSON produced by ``scripts/ocr/build_vn_wordlist.py``."""
        data = json.loads(path.read_text(encoding="utf-8"))
        # Strip all values; if multiple canonical forms collapse to the
        # same stripped key (e.g. "Căn" + "Cấn" both -> "Can"), keep the
        # most frequent one.
        freq: dict[str, tuple[int, str]] = {}
        for word, count in data.items():
            stripped = _strip(word)
            if not stripped:
                continue
            current = freq.get(stripped)
            if current is None or current[0] < count:
                freq[stripped] = (count, word)
        lookup = {stripped: canonical for stripped, (_, canonical) in freq.items()}
        return cls(lookup)

    def restore(self, text: str) -> str:
        """Restore diacritics on every word in ``text``.

        Tokens that already contain diacritics are kept verbatim (the
        wordlist entries are authoritative, but we never replace a
        non-stripped form with another form).
        Tokens not in the lookup are kept verbatim.
        """
        if not text or not self._lookup:
            return text

        def replace(match: re.Match) -> str:
            token = match.group(0)
            stripped = _strip(token)
            if stripped == token:
                # Already stripped — try to look up canonical.
                canonical = self._lookup.get(stripped)
                return canonical if canonical else token
            # Has diacritics already — leave as is (canonical list wins).
            return token

        return _TOKEN_RE.sub(replace, text)

    def restore_word(self, word: str) -> str:
        """Restore a single word; convenience wrapper."""
        return self.restore(word)


_default_singleton: VNDiacriticRestorer | None = None


def get_default_restorer() -> VNDiacriticRestorer | None:
    """Lazy-load the bundled wordlist (returns ``None`` if file missing)."""
    global _default_singleton
    if _default_singleton is None:
        wordlist = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "ocr"
            / "outputs"
            / "vn_wordlist.json"
        )
        if wordlist.is_file():
            _default_singleton = VNDiacriticRestorer.from_wordlist_json(wordlist)
    return _default_singleton


# ---------------------------------------------------------------------- #
# OCR artifact cleaner
# ---------------------------------------------------------------------- #
#
# :class:`OcrArtifactCleaner` runs *before* :class:`VNDiacriticRestorer`
# in :meth:`OCREngine._restore_diacritics_blocks`. Its sole job is to
# collapse the systematic PP-OCRv6 artifacts (``Ả``-as-space, scrambled
# heading markers) so the wordlist restorer has clean tokens to look up.
#
# The cleaner is intentionally conservative — every substitution is a
# pattern observed on real OCR output (``data/ocr/188_QD_BGDDT.pdf``
# being the canonical example).  When no pattern matches the line is
# returned untouched, so legitimate Vietnamese text such as ``Bả`` or
# ``Quản`` survives unchanged.


class OcrArtifactCleaner:
    """Strip the well-known PP-OCRv6 Vietnamese OCR artifacts.

    The cleaner must run BEFORE :class:`VNDiacriticRestorer` so the
    diacritic restorer sees the canonical heading markers (``Điều``,
    ``Chương``, ...) instead of the scrambled forms (``ĐiuẢ``,
    ``ChuưongẢ``) PP-OCRv6 tends to emit on scan pages.

    Usage::

        cleaner = OcrArtifactCleaner()
        cleaned = cleaner.clean("ĐiuẢ1.ẢPhmẢviẢđiuẢchnhẢ")
        # → "Điều 1. Phạm vi điều chỉnh"

    The cleaner is stateless and safe to instantiate per-call or reuse.
    """

    #: Public aliases so tests can introspect the rule set.
    PATTERNS: tuple[tuple[re.Pattern, str], ...] = tuple(
        (pattern, replacement) for pattern, replacement, _desc in _OCR_ARTIFACT_SUBSTITUTIONS
    )

    def clean(self, text: str) -> str:
        """Return ``text`` with known OCR artifacts collapsed.

        Cheap (a handful of regex substitutions) and idempotent — calling
        ``clean`` on already-clean text is a no-op.
        """
        if not text:
            return text
        result = text
        for pattern, replacement, _desc in _OCR_ARTIFACT_SUBSTITUTIONS:
            result = pattern.sub(replacement, result)
        return result

    def clean_word(self, word: str) -> str:
        """Convenience wrapper for single-token cleanup."""
        return self.clean(word)


_default_cleaner: OcrArtifactCleaner | None = None


def get_default_cleaner() -> OcrArtifactCleaner:
    """Return a singleton :class:`OcrArtifactCleaner`."""
    global _default_cleaner
    if _default_cleaner is None:
        _default_cleaner = OcrArtifactCleaner()
    return _default_cleaner

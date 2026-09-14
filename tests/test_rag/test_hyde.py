import asyncio

import pytest

from src.retrieval.hyde import (
    HydeCache,
    HYDE_PROMPT_TEMPLATE,
    default_cache,
    generate_hyde_passage,
    hash_query,
    is_identifier_like,
    should_apply_hyde,
)


def test_identifier_like_recognises_doc_number():
    assert is_identifier_like("Quyết định 7737/QĐ-ĐHBK do ai ký?")
    assert is_identifier_like("Điều 24 khoản 1 quy định gì?")


def test_identifier_like_rejects_semantic_query():
    assert not is_identifier_like("Học phí Tiến sĩ toàn khóa là bao nhiêu?")
    assert not is_identifier_like("Mức học phí thạc sĩ ngành kinh tế?")


def test_should_apply_hyde_skips_short_query():
    assert not should_apply_hyde("GCC", min_chars=12)
    assert not should_apply_hyde("QT-TC-003", min_chars=12)


def test_should_apply_hyde_skips_identifier_heavy():
    assert not should_apply_hyde("Điều 24 khoản 1 Áp dụng từ khi nào?", min_chars=12)


def test_should_apply_hyde_keeps_semantic_query():
    assert should_apply_hyde("Học phí Tiến sĩ toàn khóa là bao nhiêu?", min_chars=12)
    assert should_apply_hyde("Bảng quy đổi chứng chỉ tiếng Đức?", min_chars=12)


def test_hyde_prompt_contains_query_string():
    prompt = HYDE_PROMPT_TEMPLATE.format(query="Học phí Tiến sĩ?")
    assert "Học phí Tiến sĩ?" in prompt
    assert "đoạn văn" in prompt.lower() or "đại học" in prompt


def test_hyde_cache_round_trip():
    cache = HydeCache()
    cache.set("abcd", "passage text")
    assert cache.get("abcd") == "passage text"
    assert cache.get("missing") is None


def test_hyde_cache_evicts_lru():
    cache = HydeCache(max_size=3)
    cache.set("k1", "a")
    cache.set("k2", "b")
    cache.set("k3", "c")
    cache.set("k4", "d")  # evicts k1
    assert cache.get("k1") is None
    assert cache.get("k4") == "d"


def test_hash_query_is_stable_and_caseinsensitive():
    assert hash_query("Foo") == hash_query("foo")
    assert hash_query("Foo") == hash_query("  Foo  ")
    assert len(hash_query("anything")) == 16


def test_default_cache_is_module_singleton():
    assert default_cache is not None
    default_cache.set("sentinel", "x")
    assert default_cache.get("sentinel") == "x"
    default_cache.clear()


class _FakeLLM:
    def __init__(self, response: object | None = "hypothetical passage body", *,
                 raise_exc: Exception | None = None) -> None:
        # Default to None only when the caller explicitly opts into empty by
        # passing "" or None. The sentinel string is for the success path.
        if response is None:
            self.response = None
        elif isinstance(response, str) and response == "":
            self.response = ""
        else:
            self.response = response
        self.raise_exc = raise_exc
        self.calls = 0

    async def ainvoke(self, prompt: str) -> object:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def test_generate_hyde_passage_returns_passage():
    llm = _FakeLLM("Đây là đoạn văn giả thuyết về học phí Tiến sĩ.")
    out = asyncio.run(generate_hyde_passage("Học phí Tiến sĩ toàn khóa?", llm))
    assert out is not None
    assert "học phí" in out.lower()
    assert llm.calls == 1


def test_generate_hyde_passage_uses_cache_across_calls():
    llm = _FakeLLM("cached passage")
    cache = HydeCache()
    out1 = asyncio.run(generate_hyde_passage("Học phí Tiến sĩ toàn khóa?", llm, cache=cache))
    out2 = asyncio.run(generate_hyde_passage("Học phí Tiến sĩ toàn khóa?", llm, cache=cache))
    assert out1 == out2
    assert llm.calls == 1  # second call cached


def test_generate_hyde_passage_returns_none_on_llm_error():
    llm = _FakeLLM(raise_exc=RuntimeError("API down"))
    out = asyncio.run(generate_hyde_passage("Mức học phí Tiến sĩ toàn khóa?", llm))
    assert out is None


def test_generate_hyde_passage_skips_identifier_query():
    llm = _FakeLLM()
    out = asyncio.run(generate_hyde_passage("Quyết định 7737/QĐ-ĐHBK do ai ký?", llm))
    assert out is None
    assert llm.calls == 0  # we did not even call the LLM


def test_generate_hyde_passage_extracts_string_from_aimessage():
    class _Msg:
        content = "nội dung trong AIMessage"
    llm = _FakeLLM(_Msg())
    out = asyncio.run(generate_hyde_passage("Câu hỏi về học phí Tiến sĩ toàn khóa?", llm))
    assert out == "nội dung trong AIMessage"


def test_generate_hyde_passage_returns_none_on_empty_response():
    # Use a private cache so we don't pick up entries from other tests.
    llm = _FakeLLM("")
    cache = HydeCache()
    out = asyncio.run(generate_hyde_passage("Học phí Tiến sĩ toàn khóa?", llm, cache=cache))
    assert out is None
    # Whitespace-only is also rejected.
    llm_ws = _FakeLLM("   \n  ")
    out2 = asyncio.run(generate_hyde_passage("Mức học phí Tiến sĩ toàn khóa?", llm_ws, cache=cache))
    assert out2 is None

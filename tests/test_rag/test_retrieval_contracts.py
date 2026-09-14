import json

import pytest
from pydantic import ValidationError

from src.domain.schemas import (
    Candidate,
    Citation,
    EvidenceAssessment,
    Latency,
    RerankRequest,
    RerankResult,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatus,
    UserContext,
)


def candidate_payload() -> dict:
    return {
        "chunk_id": "chunk-001",
        "document_id": "document-001",
        "version_id": "version-002",
        "content": "Điều 5. Cán bộ được nghỉ phép theo kế hoạch.",
        "metadata": {"article": "5", "department": "TCCB"},
        "dense_rank": 2,
        "sparse_rank": 1,
        "fusion_score": 0.0317,
        "rerank_score": None,
    }


def citation_payload() -> dict:
    return {
        "chunk_id": "chunk-001",
        "document_id": "document-001",
        "version_id": "version-002",
        "document_number": "01/QĐ-ĐHBK",
        "title": "Quy định nghỉ phép",
        "source": "01/QĐ-ĐHBK, Điều 5",
        "article": "5",
        "excerpt": "Cán bộ được nghỉ phép theo kế hoạch.",
    }


def test_retrieval_request_serializes_and_deserializes():
    request = RetrievalRequest(
        original_query="Quy định nghỉ phép áp dụng cho ai?",
        user_context=UserContext(
            user_id="user-123",
            department="TCCB",
            roles={"staff"},
        ),
        limit=100,
        as_of_date="2026-08-04",
    )

    restored = RetrievalRequest.model_validate_json(request.model_dump_json())

    assert restored == request
    assert restored.as_of_date.isoformat() == "2026-08-04"


def test_pipeline_contracts_round_trip_through_json():
    candidate = Candidate.model_validate(candidate_payload())
    citation = Citation.model_validate(citation_payload())
    latency = Latency(total_ms=31.5, dense_ms=18.1, sparse_ms=7.4)
    retrieval = RetrievalResult(
        status=RetrievalStatus.PARTIAL,
        original_query="Quy định nghỉ phép áp dụng cho ai?",
        transformed_queries=["đối tượng áp dụng quy định nghỉ phép"],
        candidates=[candidate],
        warnings=["Sparse branch returned fewer candidates than requested."],
        latency=latency,
        index_version="regulations-2026-08-04",
    )
    rerank_request = RerankRequest(
        original_query=retrieval.original_query,
        candidates=retrieval.candidates,
        limit=5,
    )
    reranked_candidate = candidate.model_copy(update={"rerank_score": 0.91})
    rerank_result = RerankResult(
        status="sufficient",
        original_query=retrieval.original_query,
        candidates=[reranked_candidate],
        latency=Latency(rerank_ms=42.0, total_ms=42.0),
    )
    assessment = EvidenceAssessment(
        status="sufficient",
        original_query=retrieval.original_query,
        evidence_score=0.88,
        selected_candidates=rerank_result.candidates,
        citations=[citation],
        latency=Latency(evidence_gate_ms=1.1, total_ms=1.1),
    )

    for model in (retrieval, rerank_request, rerank_result, assessment):
        payload = json.loads(model.model_dump_json())
        restored = type(model).model_validate(payload)
        assert restored == model


@pytest.mark.parametrize("field", ["chunk_id", "document_id", "version_id"])
@pytest.mark.parametrize("invalid_value", [None, "", "   "])
def test_candidate_rejects_missing_or_blank_required_identifiers(field, invalid_value):
    payload = candidate_payload()
    if invalid_value is None:
        payload.pop(field)
    else:
        payload[field] = invalid_value

    with pytest.raises(ValidationError):
        Candidate.model_validate(payload)


@pytest.mark.parametrize("invalid_source", [None, "", "   "])
def test_citation_rejects_missing_or_blank_source(invalid_source):
    payload = citation_payload()
    if invalid_source is None:
        payload.pop("source")
    else:
        payload["source"] = invalid_source

    with pytest.raises(ValidationError):
        Citation.model_validate(payload)


@pytest.mark.parametrize("invalid_limit", [-1, 0, 101])
def test_retrieval_request_rejects_unsafe_limit(invalid_limit):
    with pytest.raises(ValidationError):
        RetrievalRequest(
            original_query="query",
            user_context=UserContext(user_id="user-123"),
            limit=invalid_limit,
        )


@pytest.mark.parametrize("invalid_limit", [-1, 0, 101])
def test_rerank_request_rejects_unsafe_limit(invalid_limit):
    with pytest.raises(ValidationError):
        RerankRequest(
            original_query="query",
            candidates=[Candidate.model_validate(candidate_payload())],
            limit=invalid_limit,
        )


@pytest.mark.parametrize(
    "model",
    [
        UserContext,
        RetrievalRequest,
        Candidate,
        Citation,
        Latency,
        RetrievalResult,
        RerankRequest,
        RerankResult,
        EvidenceAssessment,
    ],
)
def test_contract_has_json_schema_example(model):
    examples = model.model_json_schema().get("examples")
    assert examples
    model.model_validate(examples[0])

# RAG Sweep — Professional Domain Test Sets

A hand-verified golden test set for retrieval and answer correctness against
the HUST RAG corpus. Stable source anchors intentionally replace chunk UUIDs.

## Files

- `golden_v6_domain_50.jsonl` — 50 professional-domain test cases. It excludes
  admission lists, student names, student identifiers, and individual records.
  Each entry has:
  - `id`, `topic`, `query` — the test question
  - `expected_doc` — the document number that should be cited
  - `source_locator.evidence_groups` — stable phrases that must occur in citations
  - `reference_answer` — the human-reviewed answer
  - `answer_expectations` — required alternatives and forbidden wrong facts
- `golden_v7_domain_100.jsonl` — the expanded 100-case set, using the same
  stable-source contract.
- `run_sweep.py` — runner. Hits `/api/v1/chat` and computes metrics.

## Metrics

| Metric | Pass condition |
|--------|----------------|
| `doc_hit`             | Any cited chunk is from `expected_doc` |
| `evidence_hit`        | Citation excerpts satisfy every stable evidence group |
| `answer_correct`      | Answer satisfies required and forbidden fact rules |
| `case_pass`           | `doc_hit`, `evidence_hit`, and `answer_correct` all pass |
| `low_confidence`/`abstain` | `evidence_status` ∈ {`not_found`, `weak`, `partial`} |

`chunk_hit` and `precision_at_1` are diagnostic only. The runner reports them
as `N/A` when the selected golden set has no `expected_chunk_ids`, rather than
misreporting missing labels as retrieval misses.

## Running

```bash
# Start the API
PYTHONPATH=. python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

# Run sweep against the live API
python tests/sweep/run_sweep.py --live --out results.jsonl

# Or offline (reads pre-cached responses when present in a custom golden file)
python tests/sweep/run_sweep.py
```

The release gate is at least 80% `case_pass` (40/50), while every individual
failure remains visible for diagnosis.

## Why these queries?

Each query was chosen because:

1. The answer is verifiable in the raw PDF text (no ambiguity).
2. The expected chunk was located by direct DB lookup (`psql` style LIKE search).
3. The query wording exercises a different surface form from the chunk
   content (so we can detect if retrieval paraphrase weakness).

This means edge-case queries (typos, abbreviations, multilingual merges)
are intentionally out of scope here. A separate `--live` run is expected
to reveal which queries degrade when the model is asked to paraphrase.

## Maintenance

When you add a new high-priority document to the corpus:

1. Pick 2-3 representative facts from the new doc.
2. Locate stable evidence phrases in PostgreSQL:
   ```sql
   SELECT c.id, c.chunk_index, LEFT(c.text, 200)
   FROM chunks c
   JOIN document_versions v ON c.version_id = v.id
   JOIN documents d ON v.document_id = d.id
   WHERE c.text ILIKE '%<needle>%' AND d.document_number = '<doc#>';
   ```
3. Add a new entry to `golden_v6_domain_50.jsonl` with reviewed source anchors and answer rubric.

Do not add a query whose answer cannot be located by a deterministic
needle substring in the chunk text.

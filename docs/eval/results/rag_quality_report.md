# RAG Quality Evaluation

- Dataset: `docs\eval\datasets\golden_questions.regression.jsonl`
- Cases: `7`
- Infrastructure profile: `docker`
- Database backend: `postgresql`
- Vector backend: `qdrant`
- Evaluator: `local_deterministic_extractive_v1`
- RAGAS LLM judge executed: `false`
- Local gate: **PASS**

## Quality metrics

- answer_correctness: `0.8539080704051957`
- faithfulness: `1.0`
- context_precision: `0.7142857142857143`
- context_recall: `0.7142857142857143`
- citation_correctness: `1.0`
- citation_validation: `1.0`
- critical_abstention_correctness: `1.0`

The local evaluator measures extractive grounding and lexical answer overlap. It is not reported as a RAGAS LLM-judge result.

# OCR Backends — RapidOCR + PP-OCRv6 Vietnamese

> Single-engine architecture. No factory, no abstraction layer.
> `OCREngine` (in `src/ingestion/pdf_processor/ocr_engine.py`) wires
> RapidOCR ONNX directly to a Vietnamese-tuned recognition model.

## 1. Decision summary

| Aspect                | Value                                          |
| --------------------- | ---------------------------------------------- |
| Engine                | RapidOCR ONNX (single, not a factory)          |
| Recognition model     | PP-OCRv6_mobile_rec (73 MB)                    |
| Dictionary            | 18 708 chars (`dict.txt`)                      |
| Detection + cls       | Bundled defaults (`ch_PP-OCRv4_det`, `ch_ppocr_mobile_v2.0_cls`) |
| Runtime package       | `rapidocr-onnxruntime[opencv]`                 |
| Hybrid gate threshold | 50 chars (env `OCR_HYBRID_TEXT_THRESHOLD`)     |
| DPI                   | 200 body / 600 cover                           |
| Diacritic gate        | ≥ 0.05 ratio on every scanned page             |

## 2. Why hybrid (text-extract-first)

`data/raw/` audit (22 PDFs):

| Bucket | Count | What pipeline does |
| ------ | ----- | ------------------ |
| DIGITAL | 18    | `pymupdf.Page.get_text()` only — zero OCR cost |
| MIXED  | 4     | Text-extract first; OCR only on the 1-2 scanned pages |
| SCAN   | 0     | Full OCR via RapidOCR                              |

Pipeline behaviour: the `PageClassifier` may label pages `DIGITAL`,
`SCAN`, or `HYBRID` based on heuristics. The new hybrid gate in
`PDFProcessingPipeline._process_page` re-checks each page's raw text
length and overrides the classifier:

* `SCAN` or `HYBRID` + ≥ `hybrid_text_threshold` chars → forced to
  `DIGITAL` (no OCR).
* `DIGITAL` + < `hybrid_text_threshold` chars → forced to `SCAN`
  (full OCR).

Logged via `hybrid_gate_override` so bench scripts can verify
firing / non-firing on a per-page basis.

## 3. Engine wiring

`OCREngine.__init__` loads the RapidOCR session lazily on the first
`recognize()` call. Model files are searched at:

1. `<models_dir>/<vi_model_subdir>` (default `./ocr_models/rec_vi`)
2. `data/ocr/outputs/onnx_models/rec_vi` (development workspace)

Either is acceptable. The `scripts/ocr/install_rec_onnx.sh` one-shot
copies the workspace model into the runtime location at deploy time.

Failing fast surfaces clear messages:

* `RuntimeError("RapidOCR Vietnamese model directory not found. ...")`
  — both model dirs missing.
* `RuntimeError("RapidOCR Vietnamese model files missing in {dir}: ...")`
  — directory present but `inference.onnx` / `dict.txt` not.
* `ImportError("rapidocr_onnxruntime not installed. ...")` — runtime
  package missing.

## 4. Vietnamese diacritic gate

Per the audit in
`.cursor/plans/ocr_migration_plan_(with_deep_vietnamese_audit)_dec89d70.plan.md`:

* Hard requirement: diacritic ratio ≥ 0.05 on every OCR'd page.
* Failure modes caught by the gate: model accidentally loading the
  Chinese rec model, dict.txt stripped of Vietnamese chars.

`scripts/ocr/diff_chunks.py` computes the ratio per scanned page
using the Vietnamese diacritic set
(`ăâđêôơưĂÂĐÊÔƠƯ` + all tone marks) and flags any page below 0.05.

## 5. Bench scripts

All in `scripts/ocr/`:

| Script                       | Purpose                                       |
| ---------------------------- | --------------------------------------------- |
| `text_only_baseline.py`      | PyMuDF text extraction only — cheap baseline |
| `hybrid_text_first.py`       | Full pipeline with hybrid gate + RapidOCR fallback |
| `diff_chunks.py`             | Compare text-only vs hybrid per page; diacritic gate |
| `reingest_via_canonical.py`  | Ingest PDFs through the canonical production pipeline (`AiDocumentDigitizationService.digitize()` → `extract_sections` → `build_chunks` → Neon + Qdrant). Replaces the legacy side-script smoke test. |
| `ingest_full_corpus.py`      | Thin wrapper around `reingest_via_canonical.py` for batch re-ingest of all 22 PDFs. |

Run on the 4 MIXED files:

```bash
python3 scripts/ocr/text_only_baseline.py \
    --pdf 'data/raw/HUCE/1348_ QĐ biên soạn, lựa chọn tài liệu giảng dạy final.pdf' \
    --pdf 'data/raw/HUCE/25 - Kế hoạch nhiệm kỳ 2024-2029 của BGH.pdf' \
    --pdf 'data/raw/HUCE/Quy định Tổ chức thực hiện và đánh giá ĐATN của Trường ĐHXDHN.pdf' \
    --pdf 'data/raw/HUCE/QĐ 369 ky ngày 2 3 2026 Quy định ĐG & công nhận KQHT.pdf'

python3 scripts/ocr/hybrid_text_first.py \
    --pdf 'data/raw/HUCE/1348_ QĐ biên soạn, lựa chọn tài liệu giảng dạy final.pdf' \
    --pdf 'data/raw/HUCE/25 - Kế hoạch nhiệm kỳ 2024-2029 của BGH.pdf' \
    --pdf 'data/raw/HUCE/Quy định Tổ chức thực hiện và đánh giá ĐATN của Trường ĐHXDHN.pdf' \
    --pdf 'data/raw/HUCE/QĐ 369 ky ngày 2 3 2026 Quy định ĐG & công nhận KQHT.pdf'

python3 scripts/ocr/diff_chunks.py
```

Outputs go to `data/ocr/outputs/bench_text_only/`,
`data/ocr/outputs/bench_hybrid/`, `data/ocr/outputs/bench_diff/`.

## 6. Cloud DB re-ingest driver

The canonical driver now runs every PDF through the same
parser / section / chunk pipeline as the production HTTP endpoint:

```bash
# Re-ingest the full corpus (overwrites any prior page-level sections
# left by the legacy `ingest_one_cloud.py` smoke test).
python3 scripts/ocr/reingest_via_canonical.py --replace

# Per-school dry-run that skips Qdrant upsert — validates the parser +
# sections + chunks path without OpenAI / Qdrant creds.
python3 scripts/ocr/ingest_full_corpus.py --only huce --skip-qdrant

# PP-StructureV3 opt-in for table-heavy PDFs (e.g. 2048-table.pdf).
python3 scripts/ocr/reingest_via_canonical.py --replace \
    --ocr-engine pp_structure \
    --pdf data/raw/HUCE/2048-table.pdf
```

The driver writes outputs to
`data/ocr/outputs/reingest_canonical/` (single-PDF mode) or
`data/ocr/outputs/ingest_full_corpus/` (batch mode).

Reads `DATABASE_URL` from `.env`, runs the hybrid pipeline on the
PDF, then writes `documents`, `document_versions`, `document_sections`,
and `document_chunks` rows to the Neon DB. Prints a JSON summary
with the `chunk_count` so the operator can confirm the write.

## 7. Rollback

There is **no runtime-only rollback** — the PaddleOCR wrapper layer
was deleted (2026-09-05). To restore PaddleOCR:

```bash
git revert <merge-sha>
```

…or restore `src/ingestion/pdf_processor/ocr_backends/` from git
history and re-introduce the PaddleOCR engine class.

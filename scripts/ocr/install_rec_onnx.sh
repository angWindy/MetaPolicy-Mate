#!/usr/bin/env bash
# install_rec_onnx.sh — copy the Vietnamese recognition model files
# from the dev workspace location into the runtime location consumed
# by ``OCREngine._resolve_model_dir()``.
#
# Source: data/ocr/outputs/onnx_models/rec_vi/   (dev workspace, gitignored)
# Target: ocr_models/rec_vi/                      (runtime, gitignored)
#
# Usage:
#   ./scripts/ocr/install_rec_onnx.sh
#
# Idempotent — re-running just overwrites the files.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${REPO_ROOT}/data/ocr/outputs/onnx_models/rec_vi"
DST="${REPO_ROOT}/ocr_models/rec_vi"

if [[ ! -d "${SRC}" ]]; then
    echo "ERROR: source model directory not found: ${SRC}" >&2
    echo "Expected inference.onnx (73 MB) and dict.txt to be present." >&2
    exit 1
fi

mkdir -p "${DST}"

for f in inference.onnx dict.txt inference.yml; do
    if [[ -f "${SRC}/${f}" ]]; then
        cp -v "${SRC}/${f}" "${DST}/${f}"
    fi
done

echo
echo "Vietnamese OCR model installed at: ${DST}"
ls -lh "${DST}"

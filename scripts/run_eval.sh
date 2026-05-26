#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

: "${DIALECT:=postgres}"
: "${BENCHMARK_SCALE:=scale}"
: "${EVAL_SQL_MODE:=patch}"
: "${EVAL_RESPONSE_FIELD:=prediction}"
: "${EVAL_INPUT_DIR:=/workspace/benchmarks}"
: "${EVAL_OUTPUT_DIR:=/workspace/outputs/${DIALECT}}"

export DIALECT BENCHMARK_SCALE EVAL_SQL_MODE EVAL_RESPONSE_FIELD EVAL_INPUT_DIR EVAL_OUTPUT_DIR

bash scripts/benchmark_eval.sh

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DIALECT="${DIALECT:-postgres}"
BENCHMARK_SCALE="${BENCHMARK_SCALE:-scale}"
EVAL_INPUT_DIR="${EVAL_INPUT_DIR:-/workspace/benchmarks}"
EVAL_INPUT_FILE="${EVAL_INPUT_FILE:-}"
EVAL_FILTER_FILE="${EVAL_FILTER_FILE:-}"
EVAL_SQL_MODE="${EVAL_SQL_MODE:-patch}"
EVAL_RESPONSE_FIELD="${EVAL_RESPONSE_FIELD:-prediction}"

case "${BENCHMARK_SCALE}" in
  default|base|standard) BENCHMARK_SCALE="default" ;;
  scale|scaled) BENCHMARK_SCALE="scale" ;;
  *)
    echo "[benchmark_eval] Unsupported BENCHMARK_SCALE=${BENCHMARK_SCALE}. Use one of: default, scale"
    exit 1
    ;;
esac

case "${EVAL_SQL_MODE}" in
  patch|diff|step1|step2) EVAL_SQL_MODE="patch" ;;
  end2end|sql|full_sql) EVAL_SQL_MODE="end2end" ;;
  *)
    echo "[benchmark_eval] Unsupported EVAL_SQL_MODE=${EVAL_SQL_MODE}. Use one of: patch, end2end"
    exit 1
    ;;
esac

case "${EVAL_RESPONSE_FIELD}" in
  prediction) EVAL_RESPONSE_FIELD="prediction" ;;
  raw_response|raw) EVAL_RESPONSE_FIELD="raw_response" ;;
  *)
    echo "[benchmark_eval] Unsupported EVAL_RESPONSE_FIELD=${EVAL_RESPONSE_FIELD}. Use one of: prediction, raw_response"
    exit 1
    ;;
esac

if ! docker ps --format '{{.Names}}' | grep -q '^so_eval_env$'; then
  echo "[benchmark_eval] so_eval_env is not running. Start sandbox first: bash scripts/benchmark_up.sh"
  exit 1
fi

run_eval_for_dialect() {
  local d="$1"
  local script=""
  local output_dir="/workspace/outputs/${d}"

	  case "${d}" in
	    postgres|postgresql) script="/workspace/src/evaluation/eval_postgresql_execution.py" ;;
	    *)
	      echo "[benchmark_eval] Unsupported dialect in runner: ${d}"
	      return 1
      ;;
  esac

  local cmd="${EVAL_CMD:-python ${script}}"

  echo "[benchmark_eval] DIALECT=${d}"
  echo "[benchmark_eval] BENCHMARK_SCALE=${BENCHMARK_SCALE}"
  echo "[benchmark_eval] EVAL_SQL_MODE=${EVAL_SQL_MODE}"
  echo "[benchmark_eval] EVAL_RESPONSE_FIELD=${EVAL_RESPONSE_FIELD}"
  echo "[benchmark_eval] INPUT=${EVAL_INPUT_DIR}"
  if [[ -n "${EVAL_INPUT_FILE}" ]]; then
    echo "[benchmark_eval] INPUT_FILE=${EVAL_INPUT_FILE}"
  fi
  echo "[benchmark_eval] OUTPUT=${output_dir}"
  echo "[benchmark_eval] Running in so_eval_env: ${cmd}"
  docker exec -it \
    -e EVAL_DIALECT="${d}" \
    -e BENCHMARK_SCALE="${BENCHMARK_SCALE}" \
    -e EVAL_SQL_MODE="${EVAL_SQL_MODE}" \
    -e EVAL_RESPONSE_FIELD="${EVAL_RESPONSE_FIELD}" \
    -e EVAL_INPUT_DIR="${EVAL_INPUT_DIR}" \
    -e EVAL_INPUT_FILE="${EVAL_INPUT_FILE}" \
    -e EVAL_OUTPUT_DIR="${output_dir}" \
    -e EVAL_FILTER_FILE="${EVAL_FILTER_FILE}" \
    -e DB_MAPPING_FILE="/workspace/configs/db_mapping.benchmark-scale.json" \
    -e TPCH_MAPPING_FILE="/workspace/configs/tpch_mapping.benchmark-scale.json" \
    so_eval_env bash -lc "${cmd}"
}

if [[ "${DIALECT}" == "all" ]]; then
  run_eval_for_dialect "postgres"
else
  run_eval_for_dialect "${DIALECT}"
fi

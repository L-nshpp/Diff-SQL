#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

OUT_ROOT="${OUT_ROOT:-${ROOT_DIR}/outputs}"
DIALECTS="${DIALECTS:-postgres}"
FILE_PATTERN="${FILE_PATTERN:-}"
FILE="${FILE:-}"
GROUP_BY="${GROUP_BY:-dialect}"
TARGET_DIR="${TARGET_DIR:-}"

if [[ -n "${FILE}" ]]; then
  python3 "${ROOT_DIR}/scripts/benchmark_aggregate.py" \
    --file "${FILE}" \
    --group-by "${GROUP_BY}"
elif [[ -n "${TARGET_DIR}" ]]; then
  if [[ ! -d "${TARGET_DIR}" ]]; then
    echo "[ERROR] TARGET_DIR not found: ${TARGET_DIR}"
    exit 1
  fi
  mapfile -t _jsonl_files < <(find "${TARGET_DIR}" -maxdepth 1 -type f -name "*.jsonl" | sort)
  if [[ ${#_jsonl_files[@]} -eq 0 ]]; then
    echo "[ERROR] No .jsonl files found in TARGET_DIR: ${TARGET_DIR}"
    exit 1
  fi
  _files_csv="$(IFS=,; echo "${_jsonl_files[*]}")"
  python3 "${ROOT_DIR}/scripts/benchmark_aggregate.py" \
    --file "${_files_csv}" \
    --group-by "${GROUP_BY}"
else
  python3 "${ROOT_DIR}/scripts/benchmark_aggregate.py" \
    --root "${OUT_ROOT}" \
    --dialects "${DIALECTS}" \
    --file-pattern "${FILE_PATTERN}" \
    --group-by "${GROUP_BY}"
fi

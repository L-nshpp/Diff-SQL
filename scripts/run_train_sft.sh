#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

: "${TRAIN_SCRIPT:=diff_sql/training/sft/run_sft.sh}"
: "${TRAIN_CONFIG:=configs/model_training/sft.yaml}"
: "${TRAIN_DATA:=data/training/patch-generator/train.parquet}"
: "${DEV_DATA:=${TRAIN_DATA}}"
: "${OUTPUT_DIR:=checkpoints/sft}"

if [[ ! -f "${TRAIN_SCRIPT}" ]]; then
  echo "Training script not found: ${TRAIN_SCRIPT}" >&2
  echo "Set TRAIN_SCRIPT=/path/to/run_sft.sh if you want to use another trainer." >&2
  exit 2
fi

export TRAIN_CONFIG TRAIN_DATA DEV_DATA OUTPUT_DIR
bash "${TRAIN_SCRIPT}"

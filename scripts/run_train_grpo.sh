#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

: "${TRAIN_SCRIPT:=src/training/model_training/grpo/run_grpo.sh}"
: "${TRAIN_CONFIG:=configs/model_training/grpo.yaml}"
: "${TRAIN_DATA:=data/train_dataset/train_grpo.parquet}"
: "${TEST_DATA:=data/train_dataset/test_grpo.parquet}"
: "${OUTPUT_DIR:=checkpoints/grpo}"
: "${REWARD_FILE:=scripts/sql_reward_record.py}"

if [[ ! -f "${TRAIN_SCRIPT}" ]]; then
  echo "Training script not found: ${TRAIN_SCRIPT}" >&2
  echo "Set TRAIN_SCRIPT=/path/to/run_grpo.sh if you want to use another trainer." >&2
  exit 2
fi

export TRAIN_CONFIG TRAIN_DATA TEST_DATA OUTPUT_DIR REWARD_FILE
bash "${TRAIN_SCRIPT}"

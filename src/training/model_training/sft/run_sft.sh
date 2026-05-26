#!/usr/bin/env bash
set -euo pipefail
set -x

nproc_per_node="${NPROC_PER_NODE:-8}"

: "${TRAIN_DATA:=data/train_dataset/train_sft.parquet}"
: "${DEV_DATA:=data/train_dataset/test_sft.parquet}"
: "${MODEL_PATH:=models/base-model}"
: "${MODEL_NAME:=base-model}"
: "${OUTPUT_DIR:=checkpoints/sft}"

python -m torch.distributed.run \
    --standalone --nnodes=1 --nproc_per_node="${nproc_per_node}" \
    -m verl.trainer.fsdp_sft_trainer \
    data.train_files="${TRAIN_DATA}" \
    data.val_files="${DEV_DATA}" \
    data.prompt_key=prompt \
    data.response_key=response \
    data.micro_batch_size_per_gpu=2 \
    data.max_length=8192 \
    data.train_batch_size=16 \
    data.truncation='right' \
    model.fsdp_config.model_dtype=bfloat16 \
    model.partial_pretrain="${MODEL_PATH}" \
    model.enable_gradient_checkpointing=true \
    model.lora_rank=64 \
    model.lora_alpha=128 \
    model.target_modules=all-linear \
    trainer.default_local_dir="${OUTPUT_DIR}" \
    trainer.project_name=diff_sql_sft \
    trainer.experiment_name="${MODEL_NAME}_diff_sql_sft" \
    trainer.total_epochs=4 \
    trainer.logger=['console','tensorboard'] \
    optim.lr=5e-5 \
    optim.weight_decay=0.01 \
    trainer.save_freq=35 \
    trainer.test_freq=30 \
    "$@"

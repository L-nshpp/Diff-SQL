#!/usr/bin/env bash
set -euo pipefail
set -x

nproc_per_node="${NPROC_PER_NODE:-4}"

: "${TRAIN_DATA:?Set TRAIN_DATA=/path/to/train.parquet for GRPO training.}"
: "${TEST_DATA:=${TRAIN_DATA}}"
: "${MODEL_PATH:=checkpoints/sft/models}"
: "${OUTPUT_DIR:=checkpoints/grpo}"
: "${REWARD_FILE:=scripts/sql_reward_record.py}"
: "${PPO_MINI_BATCH_SIZE:=8}"
: "${SAVE_FREQ:=20}"
: "${TEST_FREQ:=25}"
: "${EXPERIMENT_NAME:=v1_grpo_db_opt}"

extra_args=()
if [[ -n "${RESUME_FROM_PATH:-}" ]]; then
    extra_args+=(trainer.resume_mode=resume_from_path)
    extra_args+=(trainer.resume_from_path="${RESUME_FROM_PATH}")
fi
if [[ -n "${TOTAL_TRAINING_STEPS:-}" ]]; then
    extra_args+=(trainer.total_training_steps="${TOTAL_TRAINING_STEPS}")
fi

python3 -m verl.trainer.main_ppo \
    algorithm.adv_estimator=grpo \
    +critic.enable=False \
    data.train_files="${TRAIN_DATA}" \
    data.val_files="${TEST_DATA}" \
    data.train_batch_size=32 \
    actor_rollout_ref.model.path="${MODEL_PATH}" \
    +model.lora_rank=64 \
    +model.lora_alpha=128 \
    +model.target_modules=all-linear \
    data.max_prompt_length=8192 \
    data.max_response_length=1024 \
    ++actor_rollout_ref.rollout.max_num_batched_tokens=10240 \
    ++actor_rollout_ref.model.model_kwargs.max_model_len=10240 \
    trainer.n_gpus_per_node="${nproc_per_node}" \
    ++model.fsdp_config.model_dtype=bfloat16 \
    actor_rollout_ref.rollout.tensor_model_parallel_size=1 \
    actor_rollout_ref.actor.optim.lr=5e-6 \
    actor_rollout_ref.actor.kl_loss_coef=0.01 \
    +reward_model.overlong_buffer.enable=True \
    +reward_model.overlong_buffer.penalty_factor=1.0 \
    actor_rollout_ref.rollout.n=8 \
    actor_rollout_ref.ref.fsdp_config.param_offload=True \
    +model.enable_gradient_checkpointing=true \
    actor_rollout_ref.actor.ppo_mini_batch_size="${PPO_MINI_BATCH_SIZE}" \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.8 \
    actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=4 \
    actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=4 \
    actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=4 \
    trainer.test_freq="${TEST_FREQ}" \
    trainer.save_freq="${SAVE_FREQ}" \
    trainer.project_name='sql_patch_optimize' \
    trainer.experiment_name="${EXPERIMENT_NAME}" \
    trainer.default_local_dir="${OUTPUT_DIR}" \
    custom_reward_function.path="${REWARD_FILE}" \
    custom_reward_function.name='sql_optimize' \
    "${extra_args[@]}" \
    "$@"

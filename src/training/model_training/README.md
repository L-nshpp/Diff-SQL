# Model Training Code

This directory contains the model-training entry points used by Diff-SQL.

```text
src/training/model_training/
├── sft/
│   └── run_sft.sh
└── grpo/
    └── run_grpo.sh
```

GRPO uses the standard verl entry point, `verl.trainer.main_ppo`, with the Diff-SQL SQL reward script passed through `custom_reward_function.path`.

Top-level wrappers from the repository root:

```bash
bash scripts/run_train_sft.sh
bash scripts/run_train_grpo.sh
```

The public release expects the finalized training parquet files from the HuggingFace dataset release:

```text
data/train_dataset/train_sft.parquet
data/train_dataset/test_sft.parquet
data/train_dataset/train_grpo.parquet
data/train_dataset/test_grpo.parquet
```

Override paths on a training machine with environment variables:

```bash
TRAIN_DATA=/path/to/train_sft.parquet \
DEV_DATA=/path/to/test_sft.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/sft \
bash scripts/run_train_sft.sh

TRAIN_DATA=/path/to/train_grpo.parquet \
TEST_DATA=/path/to/test_grpo.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/grpo \
bash scripts/run_train_grpo.sh
```

Optional GRPO resume controls:

```bash
RESUME_FROM_PATH=/path/to/global_step_150 \
TOTAL_TRAINING_STEPS=300 \
bash scripts/run_train_grpo.sh
```

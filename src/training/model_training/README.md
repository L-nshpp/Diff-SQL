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

The HuggingFace release contains SFT data:

```text
data/patch-generator-training-dataset/train.parquet        # Patch Generator SFT
data/constraint-aligner-training-dataset/train.parquet     # Constraint Aligner SFT warmup
```

Override paths on a training machine with environment variables:

```bash
TRAIN_DATA=/path/to/constraint-aligner-training-dataset/train.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/constraint-aligner-sft \
bash scripts/run_train_sft.sh
```

The constraint-aligner parquet is Constraint Aligner SFT warmup data.

```bash
TRAIN_DATA=/path/to/train.parquet \
TEST_DATA=/path/to/val.parquet \
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

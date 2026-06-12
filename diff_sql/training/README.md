# Model Training Code

This directory contains the model-training entry points used by Diff-SQL.

```text
diff_sql/training/
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
data/training/patch-generator/train.parquet          # Patch Generator SFT train split
data/training/patch-generator/dev.parquet            # Patch Generator SFT dev split
data/training/constraint-aligner/train.parquet       # Constraint Aligner SFT warmup train split
data/training/constraint-aligner/dev.parquet         # Constraint Aligner SFT warmup dev split
```

Override paths on a training machine with environment variables:

```bash
TRAIN_DATA=data/training/constraint-aligner/train.parquet \
DEV_DATA=data/training/constraint-aligner/dev.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/constraint-aligner-sft \
bash scripts/run_train_sft.sh
```

The constraint-aligner parquet files are Constraint Aligner SFT warmup data.

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

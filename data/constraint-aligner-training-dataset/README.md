# Constraint Aligner SFT Warmup Data Placeholder

Download the Diff-SQL HuggingFace dataset:

```text
https://huggingface.co/datasets/Lnsshp/Diff-SQL
```

Place the constraint-aligner SFT warmup parquet here:

```text
train.parquet
```

Expected HuggingFace path:

```text
data/constraint-aligner-training-dataset/train.parquet
```

This file is for supervised warmup of the Constraint Aligner. It is not the GRPO/RL dataset. The GRPO dataset is constructed later from examples that remain incorrect after warmup and is not included in the HuggingFace release.

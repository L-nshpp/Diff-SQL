# Diff-SQL

Diff-SQL is the code release for SQL efficiency optimization. The finalized training datasets and Effi-SQL benchmark file are released on HuggingFace:

```text
Training data: https://huggingface.co/datasets/birdsql/Diff-SQL
Benchmark:     https://huggingface.co/datasets/birdsql/Effi-SQL
```

This repository is organized for the benchmark-scale setting used in the paper: scale BIRD-Interact PostgreSQL databases, TPC-H PostgreSQL 3G, patch-style/end-to-end SQL evaluation, and verl-based SFT/GRPO training.

## Repository Layout

```text
.
├── data/
│   ├── benchmark/effi-sql/         # Effi-SQL benchmark files
│   ├── training/                   # HuggingFace training data placeholders
│   │   ├── patch-generator/
│   │   └── constraint-aligner/
│   └── databases/                  # local DB asset placeholders
│       ├── bird-interact-scale/
│       └── tpch-3g/
├── diff_sql/
│   ├── evaluation/                 # PostgreSQL evaluator
│   └── training/                   # verl SFT / GRPO launch code
├── docker/
│   ├── compose/                    # Docker Compose files
│   ├── postgresql/                 # BIRD-Interact DB init script
│   └── tpch/                       # TPC-H PostgreSQL schema/import scripts
├── configs/
├── scripts/                        # user-facing commands
├── Dockerfile.postgresql
├── Dockerfile.so_eval
├── requirements.txt
└── README.md
```

## HuggingFace Assets

The Diff-SQL training dataset is released at `birdsql/Diff-SQL`:

```text
patch-generator-training-dataset/
  train.parquet    # 3472 examples
  dev.parquet      # 388 examples
constraint-aligner-training-dataset/
  train.parquet    # 1554 examples
  dev.parquet      # 173 examples
```

The Effi-SQL benchmark is released at `birdsql/Effi-SQL`:

```text
effi-sql-pg.jsonl  # 300 PostgreSQL benchmark examples
```

Place or symlink those files into the repository paths below:

```text
data/training/patch-generator/train.parquet
data/training/patch-generator/dev.parquet
data/training/constraint-aligner/train.parquet
data/training/constraint-aligner/dev.parquet
data/benchmark/effi-sql/effi-sql-pg.jsonl
```

Example:

```bash
ln -s /path/to/Diff-SQL/patch-generator-training-dataset/train.parquet data/training/patch-generator/train.parquet
ln -s /path/to/Diff-SQL/patch-generator-training-dataset/dev.parquet data/training/patch-generator/dev.parquet
ln -s /path/to/Diff-SQL/constraint-aligner-training-dataset/train.parquet data/training/constraint-aligner/train.parquet
ln -s /path/to/Diff-SQL/constraint-aligner-training-dataset/dev.parquet data/training/constraint-aligner/dev.parquet
ln -s /path/to/Effi-SQL/effi-sql-pg.jsonl data/benchmark/effi-sql/effi-sql-pg.jsonl
```

## Database Assets

Prepare the PostgreSQL scale BIRD-Interact table dumps here:

```text
data/databases/bird-interact-scale/table-dumps/
  polar_equipment_template/
  robot_fault_prediction_template/
  solar_panel_template/
```

Generate or place TPC-H 3G raw data here:

```text
data/databases/tpch-3g/raw/
  region.tbl
  nation.tbl
  supplier.tbl
  customer.tbl
  part.tbl
  partsupp.tbl
  orders.tbl
  lineitem.tbl
```

To generate TPC-H 3G raw data, download the official TPC-H Tools package.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Docker is required for execution evaluation.

## Evaluation

Start the PostgreSQL benchmark databases and eval container:

```bash
bash scripts/db_up.sh
```

Run patch-style evaluation on the bundled benchmark copy:

```bash
EVAL_SQL_MODE=patch \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_FILE=eff-sql-pg.jsonl \
bash scripts/run_eval.sh
```

For direct full-SQL outputs:

```bash
EVAL_SQL_MODE=end2end \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_FILE=eff-sql-pg.jsonl \
bash scripts/run_eval.sh
```

Aggregate metrics:

```bash
bash scripts/aggregate_eval.sh
```

Stop the databases:

```bash
bash scripts/db_down.sh
```

By default, evaluation uses PostgreSQL scale BIRD-Interact databases and TPC-H 3G. Outputs are written to `outputs/postgres/`.

To evaluate the HuggingFace benchmark file:

```bash
EVAL_SQL_MODE=patch \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_FILE=effi-sql-pg.jsonl \
bash scripts/run_eval.sh
```

TPC-H PostgreSQL is initialized through:

```text
docker/tpch/postgresql/init/01-bootstrap.sh
docker/tpch/postgresql/import.sh
```

To import only the TPC-H database after placing raw data:

```bash
SMALLDB_ONLY=0 BUILD_IMAGES=0 docker compose -f docker/compose/tpch.yml up -d tpch_postgresql_3g
```

If you replace the TPC-H raw data after the Docker volume has already been initialized:

```bash
docker compose -f docker/compose/tpch.yml down -v
docker compose -f docker/compose/tpch.yml up -d tpch_postgresql_3g
```

## Training
Training is based on verl.

Run Patch Generator SFT:

```bash
bash scripts/run_train_sft.sh
```

Run Constraint Aligner SFT warmup:

```bash
TRAIN_DATA=data/training/constraint-aligner/train.parquet \
DEV_DATA=data/training/constraint-aligner/dev.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/constraint-aligner-sft \
bash scripts/run_train_sft.sh
```

The HuggingFace `constraint-aligner-training-dataset` files are Constraint Aligner SFT warmup data.

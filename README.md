# Diff-SQL

Diff-SQL is the code release for PostgreSQL SQL efficiency optimization. The finalized training datasets and Effi-SQL benchmark file are released on HuggingFace:

```text
https://huggingface.co/datasets/Lnsshp/Diff-SQL
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

Prompt construction, crawling, and intermediate data-generation scripts are intentionally not included in this release. Use the finalized HuggingFace training data for training.

## HuggingFace Assets

The HuggingFace dataset is structured as:

```text
data/
  patch-generator-training-dataset/
    train.parquet
  constraint-aligner-training-dataset/
    train.parquet
  effi-sql/
    benchmark.jsonl
```

Place or symlink those files into the repository paths below:

```text
data/training/patch-generator/train.parquet
data/training/constraint-aligner/train.parquet
data/benchmark/effi-sql/benchmark.jsonl
```

Example:

```bash
ln -s /path/to/hf/data/patch-generator-training-dataset/train.parquet data/training/patch-generator/train.parquet
ln -s /path/to/hf/data/constraint-aligner-training-dataset/train.parquet data/training/constraint-aligner/train.parquet
ln -s /path/to/hf/data/effi-sql/benchmark.jsonl data/benchmark/effi-sql/benchmark.jsonl
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

To generate TPC-H 3G raw data, download the official TPC-H Tools package from:

```text
https://www.tpc.org/tpc_documents_current_versions/current_specifications5.asp
```

After accepting the TPC license, unzip the tools package and build `dbgen`:

```bash
mkdir -p /path/to/diff-sql/data/databases/tpch-3g/raw
cd /path/to/tpc-h-tools/dbgen
make
./dbgen -s 3 -f
mv *.tbl /path/to/diff-sql/data/databases/tpch-3g/raw/
```

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
EVAL_INPUT_FILE=benchmark.jsonl \
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

Run Patch Generator SFT:

```bash
bash scripts/run_train_sft.sh
```

Run Constraint Aligner SFT warmup:

```bash
TRAIN_DATA=data/training/constraint-aligner/train.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/constraint-aligner-sft \
bash scripts/run_train_sft.sh
```

The HuggingFace `constraint-aligner-training-dataset/train.parquet` file is Constraint Aligner SFT warmup data.

Run GRPO training with your local training file:

```bash
TRAIN_DATA=/path/to/train.parquet \
TEST_DATA=/path/to/val.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/grpo \
bash scripts/run_train_grpo.sh
```

## Benchmark Files

- `data/benchmark/effi-sql/eff-sql-pg.jsonl`: PostgreSQL benchmark examples used by the default evaluation command.
- `data/benchmark/effi-sql/eff-sql-pg-with-difficulty-level.jsonl`: the same benchmark with difficulty labels.
- `data/benchmark/effi-sql/benchmark.jsonl`: optional symlink/copy of the HuggingFace benchmark file.

Core fields include `id`, `db`, `base_sql`, `optimized_sql`, `base_time`, `fast_time`, `base_explain_analyze`, and `optimized_explain_analyze`.

## Notes

- This release is PostgreSQL benchmark-scale only.
- Training parquet files are ignored by Git because they are HuggingFace assets.
- Prepare the PostgreSQL scale BIRD-Interact databases and TPC-H 3G raw `.tbl` files locally; the PostgreSQL schema/import scripts stay in this repository.
- If Docker volumes were created with older assets, recreate them with:

```bash
PURGE_VOLUMES=1 bash scripts/db_down.sh
bash scripts/db_up.sh
```

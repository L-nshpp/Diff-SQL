# Diff-SQL

Diff-SQL is the code release for PostgreSQL SQL efficiency optimization. This repository keeps the runnable code and Docker setup lightweight. The finalized training datasets and Effi-SQL benchmark file are released on HuggingFace:

```text
https://huggingface.co/datasets/Lnsshp/Diff-SQL
```

The public package is organized for the benchmark-scale setting used in the paper:

- BIRD-Interact-style PostgreSQL scale databases prepared locally.
- TPC-H PostgreSQL 3G.
- Patch-style and end-to-end SQL evaluation.
- SFT warmup and GRPO training entry points.

## Repository Layout

```text
.
├── benchmarks/                     # PostgreSQL benchmark JSONL files
├── configs/
│   ├── db_mapping.json             # PostgreSQL scale DB mapping
│   ├── tpch_mapping.json           # PostgreSQL TPC-H 3G mapping
│   ├── eval.yaml
│   └── model_training/             # SFT/GRPO training configs
├── data/                           # HuggingFace training/benchmark placeholders
│   ├── patch-generator-training-dataset/
│   ├── constraint-aligner-training-dataset/
│   └── effi-sql/
├── postgre_scale_table_dumps/      # local PostgreSQL scale DB placeholder
├── scripts/
│   ├── benchmark_up.sh             # start PostgreSQL benchmark DBs
│   ├── benchmark_eval.sh           # run eval inside Docker
│   ├── benchmark_aggregate.sh      # aggregate EX and R-VES
│   ├── benchmark_down.sh
│   ├── run_eval.sh
│   ├── run_train_sft.sh
│   └── run_train_grpo.sh
├── src/
│   ├── evaluation/                 # PostgreSQL evaluator
│   └── training/model_training/    # SFT/GRPO training code
└── tpch/raw_data/                  # local/generated TPC-H 3G placeholder
```

Prompt construction, crawling, and intermediate data-generation scripts are intentionally not included in this release. Use the finalized HuggingFace training data for training.

## HuggingFace Assets

Download the HuggingFace dataset from `https://huggingface.co/datasets/Lnsshp/Diff-SQL` and place or symlink the assets into these paths:

```text
data/
  patch-generator-training-dataset/
    train.parquet                  # Patch Generator SFT
  constraint-aligner-training-dataset/
    train.parquet                  # Constraint Aligner SFT warmup
  effi-sql/
    benchmark.jsonl
```

Example symlinks:

```bash
ln -s /path/to/hf/data/patch-generator-training-dataset ./data/patch-generator-training-dataset
ln -s /path/to/hf/data/constraint-aligner-training-dataset ./data/constraint-aligner-training-dataset
ln -s /path/to/hf/data/effi-sql ./data/effi-sql
```

The HuggingFace dataset does not include database dumps. Prepare the evaluation databases locally before running execution-based evaluation.

## Database Assets

Place the local PostgreSQL benchmark-scale BIRD-Interact dumps here:

```text
postgre_scale_table_dumps/
  polar_equipment_template/
  robot_fault_prediction_template/
  solar_panel_template/
```

Place or generate TPC-H 3G raw data here:

```text
tpch/raw_data/3g/
  region.tbl
  nation.tbl
  supplier.tbl
  customer.tbl
  part.tbl
  partsupp.tbl
  orders.tbl
  lineitem.tbl
```

If you prefer to generate the TPC-H 3G raw data locally, download the official TPC-H Tools package from the TPC current specifications page:

```text
https://www.tpc.org/tpc_documents_current_versions/current_specifications5.asp
```

After accepting the TPC license, unzip the tools package and build `dbgen`. Then run:

```bash
mkdir -p tpch/raw_data/3g
cd /path/to/tpc-h-tools/dbgen
make
./dbgen -s 3 -f
mv *.tbl /path/to/diff-sql/tpch/raw_data/3g/
```

The generated directory should contain `region.tbl`, `nation.tbl`, `supplier.tbl`, `customer.tbl`, `part.tbl`, `partsupp.tbl`, `orders.tbl`, and `lineitem.tbl`.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Docker is required for execution evaluation.

## Evaluation

Start the PostgreSQL benchmark-scale databases and eval container:

```bash
bash scripts/benchmark_up.sh
```

On the first start, Docker automatically initializes TPC-H PostgreSQL:

```text
tpch/dialects/postgresql/init/01-bootstrap.sh
tpch/dialects/postgresql/import.sh
```

Those scripts create `tpch_3g`, create the TPC-H tables, import files from `tpch/raw_data/3g/`, and run `ANALYZE`.

To import only the TPC-H database after placing raw data:

```bash
SMALLDB_ONLY=0 BUILD_IMAGES=0 docker compose -f docker-compose.tpch.yml up -d tpch_postgresql_3g
```

If you replace the TPC-H raw data after the Docker volume has already been initialized, recreate the TPC-H volume and import again:

```bash
docker compose -f docker-compose.tpch.yml down -v
docker compose -f docker-compose.tpch.yml up -d tpch_postgresql_3g
```

Run patch-style evaluation on the bundled benchmark copy, `benchmarks/eff-sql-pg.jsonl`:

```bash
EVAL_SQL_MODE=patch \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_FILE=eff-sql-pg.jsonl \
bash scripts/run_eval.sh
```

For direct full-SQL outputs, use:

```bash
EVAL_SQL_MODE=end2end \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_FILE=eff-sql-pg.jsonl \
bash scripts/run_eval.sh
```

Aggregate metrics:

```bash
bash scripts/benchmark_aggregate.sh
```

Stop the databases:

```bash
bash scripts/benchmark_down.sh
```

By default, evaluation uses PostgreSQL scale databases and TPC-H 3G. Outputs are written to `outputs/postgres/`.

To evaluate the HuggingFace benchmark file directly, use:

```bash
EVAL_SQL_MODE=patch \
EVAL_RESPONSE_FIELD=prediction \
EVAL_INPUT_DIR=/workspace/data/effi-sql \
EVAL_INPUT_FILE=benchmark.jsonl \
bash scripts/run_eval.sh
```

## Training

After placing the HuggingFace parquet files under `data/`, run Patch Generator SFT:

```bash
bash scripts/run_train_sft.sh
```

To run Constraint Aligner SFT warmup, use the same SFT entry point with the constraint-aligner warmup data:

```bash
TRAIN_DATA=data/constraint-aligner-training-dataset/train.parquet \
DEV_DATA=data/constraint-aligner-training-dataset/train.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/constraint-aligner-sft \
bash scripts/run_train_sft.sh
```

The HuggingFace `constraint-aligner-training-dataset/train.parquet` file is SFT warmup data, not GRPO data. GRPO uses examples selected after warmup from cases that still fail execution or semantic-equivalence checks. That GRPO parquet is not included in this HuggingFace release. If you have constructed it locally, run:

```bash
TRAIN_DATA=/path/to/grpo_train.parquet \
TEST_DATA=/path/to/grpo_val.parquet \
MODEL_PATH=/path/to/base-model \
OUTPUT_DIR=checkpoints/grpo \
bash scripts/run_train_grpo.sh
```

The HuggingFace release provides one `train.parquet` file for each SFT stage. The wrappers use the training file as verl's validation file by default unless `DEV_DATA` is set.

## Benchmark Files

- `benchmarks/eff-sql-pg.jsonl`: PostgreSQL benchmark examples. The HuggingFace copy is `data/effi-sql/benchmark.jsonl`.
- `benchmarks/eff-sql-pg-with-difficulty-level.jsonl`: the same benchmark with difficulty labels.

Core fields include `id`, `db`, `base_sql`, `optimized_sql`, `base_time`, `fast_time`, `base_explain_analyze`, and `optimized_explain_analyze`.

## Notes

- This release is PostgreSQL benchmark-scale only.
- Training parquet files are ignored by Git because they are HuggingFace assets.
- Database dumps and TPC-H raw `.tbl` files are not included in the HuggingFace dataset. Prepare them locally; the PostgreSQL schema/import scripts stay in this repository.
- If Docker volumes were created with older assets, recreate them with:

```bash
PURGE_VOLUMES=1 bash scripts/benchmark_down.sh
bash scripts/benchmark_up.sh
```

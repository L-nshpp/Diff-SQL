# Diff-SQL

Diff-SQL is the code release for SQL efficiency optimization. This repository keeps the runnable code, benchmark files, and Docker setup lightweight; large database assets and finalized training data are released separately on HuggingFace:

```text
https://huggingface.co/datasets/Lnsshp/Diff-SQL
```

The public package is organized for the benchmark-scale setting used in the paper:

- BIRD-Interact-style PostgreSQL scale databases.
- TPC-H PostgreSQL 3G.
- Patch-style and end-to-end SQL evaluation.
- SFT and GRPO model training from finalized parquet files.

## Repository Layout

```text
.
├── benchmarks/                     # PostgreSQL benchmark JSONL files
├── configs/
│   ├── db_mapping.json             # PostgreSQL scale DB mapping
│   ├── tpch_mapping.json           # PostgreSQL TPC-H 3G mapping
│   ├── eval.yaml
│   └── model_training/             # SFT/GRPO training configs
├── data/train_dataset/             # HuggingFace training-data placeholder
├── postgre_scale_table_dumps/      # HuggingFace PostgreSQL scale DB placeholder
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
└── tpch/raw_data/                  # HuggingFace TPC-H 3G placeholder
```

Prompt construction, crawling, and intermediate data-generation scripts are intentionally not included in this release. Use the finalized HuggingFace training data for training.

## HuggingFace Assets

Download the HuggingFace dataset from `https://huggingface.co/datasets/Lnsshp/Diff-SQL` and place or symlink the assets into these paths:

```text
postgre_scale_table_dumps/
  polar_equipment_template/
  robot_fault_prediction_template/
  solar_panel_template/

tpch/raw_data/3g/
  region.tbl
  nation.tbl
  supplier.tbl
  customer.tbl
  part.tbl
  partsupp.tbl
  orders.tbl
  lineitem.tbl

data/train_dataset/
  train_sft.parquet
  test_sft.parquet
  train_grpo.parquet
  test_grpo.parquet
```

Example symlinks:

```bash
ln -s /path/to/hf/postgre_scale_table_dumps ./postgre_scale_table_dumps
ln -s /path/to/hf/tpch/raw_data ./tpch/raw_data
ln -s /path/to/hf/train_dataset ./data/train_dataset
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

Run patch-style evaluation on `benchmarks/eff-sql-pg.jsonl`:

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

## Training

After placing the HuggingFace parquet files under `data/train_dataset/`, run:

```bash
bash scripts/run_train_sft.sh
bash scripts/run_train_grpo.sh
```

Common overrides:

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

## Benchmark Files

- `benchmarks/eff-sql-pg.jsonl`: PostgreSQL benchmark examples.
- `benchmarks/eff-sql-pg-with-difficulty-level.jsonl`: the same benchmark with difficulty labels.

Core fields include `id`, `db`, `base_sql`, `optimized_sql`, `base_time`, `fast_time`, `base_explain_analyze`, and `optimized_explain_analyze`.

## Notes

- This release is PostgreSQL benchmark-scale only.
- Database dumps and training parquet files are ignored by Git because they are HuggingFace assets.
- TPC-H raw `.tbl` files live on HuggingFace; the PostgreSQL schema/import scripts stay in this repository.
- If Docker volumes were created with older assets, recreate them with:

```bash
PURGE_VOLUMES=1 bash scripts/benchmark_down.sh
bash scripts/benchmark_up.sh
```

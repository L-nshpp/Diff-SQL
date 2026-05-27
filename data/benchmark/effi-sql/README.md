# Effi-SQL Benchmark

This directory contains the PostgreSQL Effi-SQL benchmark files used by the default evaluation command.

```text
eff-sql-pg.jsonl
eff-sql-pg-with-difficulty-level.jsonl
```

The HuggingFace dataset provides the benchmark as:

```text
data/effi-sql/benchmark.jsonl
```

You can place or symlink that file here as `benchmark.jsonl` and evaluate it by setting `EVAL_INPUT_FILE=benchmark.jsonl`.

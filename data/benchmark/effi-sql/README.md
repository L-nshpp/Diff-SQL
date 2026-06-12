# Effi-SQL Benchmark

This directory contains the PostgreSQL Effi-SQL benchmark files used by the default evaluation command.

```text
eff-sql-pg.jsonl
eff-sql-pg-with-difficulty-level.jsonl
```

The HuggingFace dataset provides the benchmark as:

```text
https://huggingface.co/datasets/birdsql/Effi-SQL
effi-sql-pg.jsonl
```

You can place or symlink that file here as `effi-sql-pg.jsonl` and evaluate it by setting `EVAL_INPUT_FILE=effi-sql-pg.jsonl`.

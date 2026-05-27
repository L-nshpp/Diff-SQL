Place TPC-H raw data under `tpch/raw_data/3g/`.

Expected files:

```text
3g/region.tbl
3g/nation.tbl
3g/supplier.tbl
3g/customer.tbl
3g/part.tbl
3g/partsupp.tbl
3g/orders.tbl
3g/lineitem.tbl
```

Generate these files with the official TPC-H `dbgen` tool according to the TPC-H terms.

The GitHub repository keeps the PostgreSQL schema and import scripts under `tpch/dialects/postgresql/`; only the raw `.tbl` data files are external.

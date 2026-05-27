Place TPC-H 3G raw data here.

Expected files:

```text
region.tbl
nation.tbl
supplier.tbl
customer.tbl
part.tbl
partsupp.tbl
orders.tbl
lineitem.tbl
```

Generate these files with the official TPC-H `dbgen` tool according to the TPC-H terms.

The GitHub repository keeps the PostgreSQL schema and import scripts under `docker/tpch/postgresql/`; only the raw `.tbl` data files are external.

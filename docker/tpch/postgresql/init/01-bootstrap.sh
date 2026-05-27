#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${TPCH_DB:?TPCH_DB is required}"

echo "[tpch-postgresql] Creating database ${DB_NAME} if needed"
psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres <<SQL
SELECT 'CREATE DATABASE ${DB_NAME}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

/tpch/dialects/postgresql/import.sh

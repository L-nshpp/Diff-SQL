#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${TPCH_DB:?TPCH_DB is required}"
SCALE="${TPCH_SCALE:?TPCH_SCALE is required}"
RAW_DIR="/tpch/raw_data/${SCALE}"

SCHEMA_FILE="/tpch/dialects/postgresql/schema.sql"
if [[ "${USE_COMMON_TPCH_SCHEMA:-0}" == "1" && -f /tpch/dialects/common/tpch_schema.sql ]]; then
  SCHEMA_FILE="/tpch/dialects/common/tpch_schema.sql"
fi

psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${DB_NAME}" -f "${SCHEMA_FILE}"

if [[ ! -d "${RAW_DIR}" ]]; then
  echo "[tpch-postgresql] Raw data directory ${RAW_DIR} not found, schema-only init finished."
  exit 0
fi

tables=(region nation supplier customer part partsupp orders lineitem)

find_data_file() {
  local table="$1"
  for ext in tbl csv dat; do
    if [[ -f "${RAW_DIR}/${table}.${ext}" ]]; then
      echo "${RAW_DIR}/${table}.${ext}"
      return 0
    fi
  done
  return 1
}

for table in "${tables[@]}"; do
  if file_path="$(find_data_file "${table}")"; then
    case "${file_path}" in
      *.csv)
        echo "[tpch-postgresql] Loading ${table} from ${file_path} (CSV delimiter ',')"
        psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${DB_NAME}" -c "\\copy ${table} FROM '${file_path}' WITH (FORMAT csv, HEADER false, DELIMITER ',');"
        ;;
      *)
        echo "[tpch-postgresql] Loading ${table} from ${file_path} (TPCH delimiter '|' with trailing-pipe trim)"
        sed 's/|$//' "${file_path}" | psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${DB_NAME}" -c "\\copy ${table} FROM STDIN WITH (FORMAT text, DELIMITER '|');"
        ;;
    esac
  else
    echo "[tpch-postgresql] ${table} data file not found in ${RAW_DIR}, skipped."
  fi
done

psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${DB_NAME}" -c "ANALYZE;"

echo "[tpch-postgresql] Import completed for ${DB_NAME} (${SCALE})."

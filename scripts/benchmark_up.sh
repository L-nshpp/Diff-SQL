#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

SMALLDB_ONLY="${SMALLDB_ONLY:-0}"
BUILD_IMAGES="${BUILD_IMAGES:-1}"
DIALECT="${DIALECT:-postgres}"
BENCHMARK_SCALE="${BENCHMARK_SCALE:-scale}"

case "${BENCHMARK_SCALE}" in
  default|base|standard) BENCHMARK_SCALE="default" ;;
  scale|scaled) BENCHMARK_SCALE="scale" ;;
  *)
    echo "[benchmark_up] Unsupported BENCHMARK_SCALE=${BENCHMARK_SCALE}. Use one of: default, scale"
    exit 1
    ;;
esac

POSTGRES_DUMP_VARIANT="${POSTGRES_DUMP_VARIANT:-${BENCHMARK_SCALE}}"

case "${POSTGRES_DUMP_VARIANT}" in
  default|base|standard) POSTGRES_DUMP_VARIANT="default" ;;
  scale|scaled) POSTGRES_DUMP_VARIANT="scale" ;;
  *)
    echo "[benchmark_up] Unsupported POSTGRES_DUMP_VARIANT=${POSTGRES_DUMP_VARIANT}. Use one of: default, scale"
    exit 1
    ;;
esac

export BENCHMARK_SCALE
export POSTGRES_DUMP_VARIANT

POSTGRES_TPCH_SERVICE="tpch_postgresql_3g"

compose_files=(-f docker-compose.smalldb.yml)
if [[ "${SMALLDB_ONLY}" != "1" ]]; then
  compose_files+=(-f docker-compose.tpch.yml)
fi

up_args=(up -d)
if [[ "${BUILD_IMAGES}" == "1" ]]; then
  up_args+=(--build)
fi

services=()
case "${DIALECT}" in
  all|postgres|postgresql)
    services=(postgresql_small "${POSTGRES_TPCH_SERVICE}" so_eval_env)
    ;;
  *)
    echo "[benchmark_up] Unsupported DIALECT=${DIALECT}. Use one of: all, postgres"
    exit 1
    ;;
esac

if [[ "${SMALLDB_ONLY}" == "1" && ${#services[@]} -gt 0 ]]; then
  filtered=()
  for s in "${services[@]}"; do
    case "${s}" in
      tpch_*) ;;
      *) filtered+=("${s}") ;;
    esac
  done
  services=("${filtered[@]}")
fi

echo "[benchmark_up] DIALECT=${DIALECT}"
echo "[benchmark_up] BENCHMARK_SCALE=${BENCHMARK_SCALE}"
echo "[benchmark_up] POSTGRES_DUMP_VARIANT=${POSTGRES_DUMP_VARIANT}"
echo "[benchmark_up] BUILD_IMAGES=${BUILD_IMAGES}"
echo "[benchmark_up] Using compose files: ${compose_files[*]}"
if [[ ${#services[@]} -gt 0 ]]; then
  echo "[benchmark_up] Services: ${services[*]}"
fi

echo "[benchmark_up] PostgreSQL TPCH service: ${POSTGRES_TPCH_SERVICE}"
echo "[benchmark_up] If you changed BENCHMARK_SCALE or POSTGRES_DUMP_VARIANT, recreate PostgreSQL with PURGE_VOLUMES=1 bash scripts/benchmark_down.sh before starting."

docker compose "${compose_files[@]}" "${up_args[@]}" "${services[@]}"

echo "[benchmark_up] Current service status"
if [[ ${#services[@]} -gt 0 ]]; then
  docker compose "${compose_files[@]}" ps "${services[@]}"
else
  docker compose "${compose_files[@]}" ps
fi

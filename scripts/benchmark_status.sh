#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

SMALLDB_ONLY="${SMALLDB_ONLY:-0}"
DIALECT="${DIALECT:-postgres}"
BENCHMARK_SCALE="${BENCHMARK_SCALE:-scale}"

case "${BENCHMARK_SCALE}" in
  default|base|standard) BENCHMARK_SCALE="default" ;;
  scale|scaled) BENCHMARK_SCALE="scale" ;;
  *)
    echo "[benchmark_status] Unsupported BENCHMARK_SCALE=${BENCHMARK_SCALE}. Use one of: default, scale"
    exit 1
    ;;
esac

POSTGRES_TPCH_SERVICE="tpch_postgresql_3g"

compose_files=(-f docker-compose.smalldb.yml)
if [[ "${SMALLDB_ONLY}" != "1" ]]; then
  compose_files+=(-f docker-compose.tpch.yml)
fi

services=()
case "${DIALECT}" in
  all|postgres|postgresql)
    services=(
      postgresql_small
      "${POSTGRES_TPCH_SERVICE}"
      so_eval_env
    )
    ;;
  *)
    echo "[benchmark_status] Unsupported DIALECT=${DIALECT}. Use one of: all, postgres"
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

echo "[benchmark_status] BENCHMARK_SCALE=${BENCHMARK_SCALE}"
if [[ ${#services[@]} -gt 0 ]]; then
  docker compose "${compose_files[@]}" ps "${services[@]}"
else
  docker compose "${compose_files[@]}" ps
fi

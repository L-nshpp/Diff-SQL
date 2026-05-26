#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PURGE_VOLUMES="${PURGE_VOLUMES:-0}"
SMALLDB_ONLY="${SMALLDB_ONLY:-0}"
DIALECT="${DIALECT:-postgres}"
BENCHMARK_SCALE="${BENCHMARK_SCALE:-scale}"

case "${BENCHMARK_SCALE}" in
  default|base|standard) BENCHMARK_SCALE="default" ;;
  scale|scaled) BENCHMARK_SCALE="scale" ;;
  *)
    echo "[benchmark_down] Unsupported BENCHMARK_SCALE=${BENCHMARK_SCALE}. Use one of: default, scale"
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
      tpch_postgresql_3g
      so_eval_env
    )
    ;;
  *)
    echo "[benchmark_down] Unsupported DIALECT=${DIALECT}. Use one of: all, postgres"
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

echo "[benchmark_down] DIALECT=${DIALECT}"
echo "[benchmark_down] BENCHMARK_SCALE=${BENCHMARK_SCALE}"
echo "[benchmark_down] Using compose files: ${compose_files[*]}"

if [[ ${#services[@]} -eq 0 ]]; then
  echo "[benchmark_down] No service selected for DIALECT=${DIALECT}"
  exit 0
fi
volume_names=()
if [[ "${PURGE_VOLUMES}" == "1" ]]; then
  mapfile -t volume_names < <(
    for s in "${services[@]}"; do
      cid="$(docker compose "${compose_files[@]}" ps -a -q "${s}" 2>/dev/null || true)"
      if [[ -n "${cid}" ]]; then
        docker inspect "${cid}" --format '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}' 2>/dev/null || true
      fi
    done | sort -u
  )
fi
docker compose "${compose_files[@]}" stop "${services[@]}" || true
docker compose "${compose_files[@]}" rm -f "${services[@]}" || true
if [[ "${PURGE_VOLUMES}" == "1" && ${#volume_names[@]} -gt 0 ]]; then
  echo "[benchmark_down] Removing volumes: ${volume_names[*]}"
  docker volume rm -f "${volume_names[@]}" || true
fi

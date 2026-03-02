#!/usr/bin/env bash
# =============================================================================
# Reinicia o Celery worker diariamente às 06:00 (limpa processos órfãos)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/worker_restart_daily.log}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "$(TZ='America/Sao_Paulo' date '+%Y-%m-%d %H:%M:%S') [restart_daily] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"
log "Reiniciando worker (manutenção diária)..."
docker compose restart worker
log "Worker reiniciado."

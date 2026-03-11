#!/usr/bin/env bash
# =============================================================================
# Reinicia o Celery worker 3x/dia (06:04, 13:04, 22:04) - limpa processos órfãos
# =============================================================================

set -euo pipefail

# Cron tem PATH mínimo; garantir que docker seja encontrado
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/worker_restart_daily.log}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "$(TZ='America/Sao_Paulo' date '+%Y-%m-%d %H:%M:%S') [restart_daily] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"
log "Reiniciando worker (manutenção programada)..."
docker compose restart worker
log "Worker reiniciado."

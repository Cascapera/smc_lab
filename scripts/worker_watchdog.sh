#!/usr/bin/env bash
# =============================================================================
# Worker Watchdog - Reinicia o Celery worker quando parar ou ficar inativo
# =============================================================================
# Execute via cron a cada 5 minutos: */5 * * * * /home/user/app/scripts/worker_watchdog.sh
# Ou configure no setup: ./scripts/install_worker_watchdog.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/worker_watchdog.log}"
PING_TIMEOUT="${PING_TIMEOUT:-15}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "$(TZ='America/Sao_Paulo' date '+%Y-%m-%d %H:%M:%S') [watchdog] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"

# 1. Container parado?
if ! docker compose ps worker 2>/dev/null | grep -q "Up"; then
  log "Worker container parado. Iniciando..."
  docker compose up -d worker
  log "Worker iniciado."
  exit 0
fi

# 2. Worker respondendo? (celery inspect ping)
if ! timeout "$PING_TIMEOUT" docker compose exec -T worker celery -A trader_portal inspect ping 2>/dev/null | grep -q "pong"; then
  log "Worker não respondeu ao ping. Reiniciando..."
  docker compose restart worker
  log "Worker reiniciado."
  exit 0
fi

# Tudo ok
exit 0

#!/usr/bin/env bash
# =============================================================================
# Worker Watchdog - Reinicia o Celery worker quando parar ou ficar inativo
# =============================================================================
# Execute via cron a cada 5 minutos: */5 * * * * /home/user/app/scripts/worker_watchdog.sh
# Ou configure no setup: ./scripts/install_worker_watchdog.sh
# =============================================================================

set -euo pipefail

# Cron tem PATH mínimo; garantir que docker seja encontrado
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/worker_watchdog.log}"
PING_TIMEOUT="${PING_TIMEOUT:-15}"

mkdir -p "$(dirname "$LOG_FILE")"
# Redirecionar erros para o log (cron não mostra stderr)
exec 2>>"$LOG_FILE"

log() {
  echo "$(TZ='America/Sao_Paulo' date '+%Y-%m-%d %H:%M:%S') [watchdog] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR" || { log "ERRO: não foi possível cd para $PROJECT_DIR"; exit 1; }

# 1. Container parado?
if ! docker compose ps worker 2>/dev/null | grep -q "Up"; then
  log "Worker container parado. Iniciando..."
  docker compose up -d worker
  log "Worker iniciado."
  exit 0
fi

# 2. Worker respondendo? (celery inspect ping)
# -s 9 = SIGKILL após timeout (não pode travar; docker exec pode ignorar SIGTERM)
if ! timeout -s 9 "$PING_TIMEOUT" docker compose exec -T worker celery -A trader_portal inspect ping 2>/dev/null | grep -q "pong"; then
  log "Worker não respondeu ao ping. Reiniciando..."
  docker compose restart worker
  log "Worker reiniciado."
  exit 0
fi

# Tudo ok
exit 0

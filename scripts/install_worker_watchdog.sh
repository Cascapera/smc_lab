#!/usr/bin/env bash
# =============================================================================
# Instala o cron do Worker Watchdog e reinício diário no servidor
# =============================================================================
# Execute no servidor (via SSH): cd ~/app && bash scripts/install_worker_watchdog.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WATCHDOG_SCRIPT="$PROJECT_DIR/scripts/worker_watchdog.sh"
RESTART_SCRIPT="$PROJECT_DIR/scripts/restart_worker_daily.sh"
DOCKER_PRUNE_SCRIPT="$PROJECT_DIR/scripts/docker_prune.sh"
CRON_WATCHDOG="*/18 * * * * $WATCHDOG_SCRIPT"
CRON_RESTART="4 6,13,22 * * * $RESTART_SCRIPT"
CRON_DOCKER_PRUNE="0 3 * * 0 $DOCKER_PRUNE_SCRIPT"

# Tornar executáveis
chmod +x "$WATCHDOG_SCRIPT"
chmod +x "$RESTART_SCRIPT"
chmod +x "$DOCKER_PRUNE_SCRIPT"

CRONTAB_NEW="$(crontab -l 2>/dev/null || true)"

# Watchdog (a cada 18 min - evita coincidir com coleta de 5 em 5 min)
CRONTAB_NEW="$(echo "$CRONTAB_NEW" | grep -v "worker_watchdog" || true)"
CRONTAB_NEW="${CRONTAB_NEW}${CRONTAB_NEW:+$'\n'}$CRON_WATCHDOG"
echo "✓ Worker watchdog configurado (executa a cada 18 minutos)."

# Reinício do worker 3x/dia (06:04, 13:04, 22:04 - entre ciclos de 5 min)
CRONTAB_NEW="$(echo "$CRONTAB_NEW" | grep -v "restart_worker_daily" || true)"
CRONTAB_NEW="${CRONTAB_NEW}${CRONTAB_NEW:+$'\n'}$CRON_RESTART"
echo "✓ Reinício do worker configurado (06:04, 13:04, 22:04)."

# Limpeza Docker semanal (domingo 03:00)
if ! echo "$CRONTAB_NEW" | grep -q "docker_prune"; then
  CRONTAB_NEW="${CRONTAB_NEW}${CRONTAB_NEW:+$'\n'}$CRON_DOCKER_PRUNE"
  echo "✓ Limpeza Docker configurada (domingo 03:00)."
else
  echo "Limpeza Docker já está no crontab."
fi

echo "$CRONTAB_NEW" | crontab -
echo ""
echo "Logs:"
echo "  Watchdog: $PROJECT_DIR/logs/worker_watchdog.log"
echo "  Reinício diário: $PROJECT_DIR/logs/worker_restart_daily.log"
echo "  Docker prune: $PROJECT_DIR/logs/docker_prune.log"
echo ""
echo "Para remover: crontab -e  (e apague as linhas)"

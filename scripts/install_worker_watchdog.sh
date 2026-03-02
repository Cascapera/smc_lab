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
CRON_WATCHDOG="*/5 * * * * $WATCHDOG_SCRIPT"
CRON_RESTART="0 6 * * * $RESTART_SCRIPT"

# Tornar executáveis
chmod +x "$WATCHDOG_SCRIPT"
chmod +x "$RESTART_SCRIPT"

CRONTAB_NEW="$(crontab -l 2>/dev/null || true)"

# Watchdog (a cada 5 min)
if ! echo "$CRONTAB_NEW" | grep -q "worker_watchdog"; then
  CRONTAB_NEW="${CRONTAB_NEW}${CRONTAB_NEW:+$'\n'}$CRON_WATCHDOG"
  echo "✓ Worker watchdog adicionado (executa a cada 5 minutos)."
else
  echo "Watchdog já está no crontab."
fi

# Reinício diário às 06:00
if ! echo "$CRONTAB_NEW" | grep -q "restart_worker_daily"; then
  CRONTAB_NEW="${CRONTAB_NEW}${CRONTAB_NEW:+$'\n'}$CRON_RESTART"
  echo "✓ Reinício diário do worker adicionado (06:00)."
else
  echo "Reinício diário já está no crontab."
fi

echo "$CRONTAB_NEW" | crontab -
echo ""
echo "Logs:"
echo "  Watchdog: $PROJECT_DIR/logs/worker_watchdog.log"
echo "  Reinício diário: $PROJECT_DIR/logs/worker_restart_daily.log"
echo ""
echo "Para remover: crontab -e  (e apague as linhas)"

#!/usr/bin/env bash
# =============================================================================
# Instala o cron do Worker Watchdog no servidor
# =============================================================================
# Execute no servidor (via SSH): cd ~/app && bash scripts/install_worker_watchdog.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WATCHDOG_SCRIPT="$PROJECT_DIR/scripts/worker_watchdog.sh"
CRON_LINE="*/5 * * * * $WATCHDOG_SCRIPT"

# Tornar executável
chmod +x "$WATCHDOG_SCRIPT"

# Verificar se já está instalado
if crontab -l 2>/dev/null | grep -q "worker_watchdog"; then
  echo "Watchdog já está no crontab. Nada a fazer."
  exit 0
fi

# Adicionar ao crontab
(crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -
echo "✓ Worker watchdog instalado. Executa a cada 5 minutos."
echo "  Log: $PROJECT_DIR/logs/worker_watchdog.log"
echo ""
echo "Para remover: crontab -e  (e apague a linha do worker_watchdog)"

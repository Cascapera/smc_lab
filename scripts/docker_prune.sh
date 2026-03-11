#!/usr/bin/env bash
# =============================================================================
# Limpa imagens, containers e cache do Docker não utilizados
# =============================================================================
# Remove APENAS o que não está em uso - containers em execução não são afetados
# Execute via cron semanal: 0 3 * * 0 /path/to/docker_prune.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/docker_prune.log"

mkdir -p "$LOG_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "Iniciando limpeza Docker..."

# -f = não pedir confirmação
# -a = incluir imagens não usadas
docker system prune -a -f 2>&1 | tee -a "$LOG_FILE"
docker builder prune -a -f 2>&1 | tee -a "$LOG_FILE"

log "Limpeza Docker concluída."

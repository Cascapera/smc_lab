#!/usr/bin/env bash
# =============================================================================
# Worker Watchdog - reinicia o Celery worker quando ele realmente para.
#
# Instalado via cron pelo scripts/install_worker_watchdog.sh
#
# Por que não usa mais `celery inspect ping`:
#   Com `--pool=solo`, o worker não responde a comandos de controle. O ping
#   falhava SEMPRE - em 2 segundos, não por timeout -, então o watchdog
#   reiniciava o worker a cada verificação, incondicionalmente. Ficou registrado
#   no log: restarts às 17:00, 17:18, 17:36, 17:54, 18:00, 18:18...
#
#   O efeito prático não era perda de dado (o restart espera a tarefa terminar,
#   graças ao stop_grace_period), mas algo pior de outra forma: um monitor com
#   100% de falso positivo não detecta travamento nenhum. Um worker realmente
#   travado ficava indistinguível do normal.
#
# O que ele mede agora:
#   A task de coleta grava um carimbo de tempo no cache toda vez que executa,
#   inclusive quando pula por mercado fechado. Se esse carimbo está velho, o
#   worker parou de consumir tarefas - que é a falha que o watchdog existe para
#   pegar. Funciona com qualquer pool.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/worker_watchdog.log}"

# O Beat enfileira a coleta a cada 5 min. 15 min sem heartbeat significa três
# agendamentos seguidos sem execução: aí sim é travamento.
MAX_IDADE_SEGUNDOS="${MAX_IDADE_SEGUNDOS:-900}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "$(TZ='America/Sao_Paulo' date '+%Y-%m-%d %H:%M:%S') [watchdog] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR"

# -----------------------------------------------------------------------------
# 1. Container de pé?
# -----------------------------------------------------------------------------
if ! docker compose ps worker 2>/dev/null | grep -q "Up"; then
  log "Worker container parado. Iniciando..."
  docker compose up -d worker
  log "Worker iniciado."
  exit 0
fi

# -----------------------------------------------------------------------------
# 2. O worker executou a task recentemente?
# -----------------------------------------------------------------------------
# Management command, nao `python -c`: o one-liner precisava de django.setup()
# para os models carregarem. Sem ele, o import levantava excecao, a saida vinha
# vazia e o watchdog ficava inerte - foi o que aconteceu na primeira versao.
idade="$(docker compose exec -T worker python manage.py worker_heartbeat \
  2>/dev/null | tr -d '\r' | tail -n 1)"

# Sem resposta utilizável: pode ser container reiniciando ou erro de import.
# Não reiniciamos por isso - seria voltar ao falso positivo que estamos
# corrigindo. Registramos para aparecer no log.
if ! [[ "$idade" =~ ^-?[0-9]+$ ]]; then
  log "AVISO: nao consegui ler o heartbeat (resposta: '${idade:-vazia}'). Nao vou reiniciar."
  exit 0
fi

# -1 = nunca executou. Acontece logo após um restart, antes do primeiro ciclo.
# Como o Beat enfileira a cada 5 min, esperar é o certo.
if [ "$idade" -lt 0 ]; then
  log "Heartbeat ainda nao existe (worker recem-iniciado). Aguardando o primeiro ciclo."
  exit 0
fi

if [ "$idade" -gt "$MAX_IDADE_SEGUNDOS" ]; then
  log "Worker sem executar tarefa ha ${idade}s (limite ${MAX_IDADE_SEGUNDOS}s). Reiniciando..."
  docker compose restart worker
  log "Worker reiniciado."
  exit 0
fi

# Tudo certo. Sem log, para não encher o arquivo a cada verificação.
exit 0

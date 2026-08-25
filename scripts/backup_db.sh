#!/usr/bin/env bash
# =============================================================================
# Backup do banco (PostgreSQL) e da pasta media.
#
# Roda antes de todo deploy e antes de todo rollback. Se o backup do banco
# falhar, o script sai com erro e interrompe o deploy — é de propósito: não
# subimos versão nova sem ponto de retorno. Para forçar, use ALLOW_NO_BACKUP=1.
#
# Importante: este script NÃO faz `source .env`. O .env contém valores com
# parênteses, cifrões e aspas (ex.: SECRET_KEY) que o bash interpretaria,
# quebrando o deploy inteiro. As credenciais do Postgres são lidas de dentro
# do próprio container, que já as recebe via docker compose.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

# Lê UMA chave do .env sem interpretar o conteúdo (seguro para qualquer valor).
#
# Nunca retorna erro: chave ausente devolve string vazia. Isso é essencial
# porque o script roda com `set -euo pipefail` — uma versão anterior terminava
# em `grep | tail | cut | sed` e, quando a chave não existia (BACKUP_DIR,
# KEEP_BACKUPS e BACKUP_MEDIA normalmente não estão no .env), o grep retornava 1,
# o pipefail propagava e o deploy inteiro abortava no primeiro passo.
env_get() {
  [ -f "$ENV_FILE" ] || return 0
  linha="$(grep -E "^[[:space:]]*$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 || true)"
  [ -n "$linha" ] || return 0
  printf '%s' "${linha#*=}" \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/" || true
}

BACKUP_DIR="${BACKUP_DIR:-$(env_get BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
KEEP_BACKUPS="${KEEP_BACKUPS:-$(env_get KEEP_BACKUPS)}"
KEEP_BACKUPS="${KEEP_BACKUPS:-8}"
BACKUP_MEDIA="${BACKUP_MEDIA:-$(env_get BACKUP_MEDIA)}"
BACKUP_MEDIA="${BACKUP_MEDIA:-1}"   # 1 = backup media (imagens), 0 = só banco
ALLOW_NO_BACKUP="${ALLOW_NO_BACKUP:-0}"

mkdir -p "$BACKUP_DIR"

timestamp="$(TZ="America/Sao_Paulo" date +"%Y-%m-%d_%H-%M")"
backup_file="$BACKUP_DIR/backup_${timestamp}.sql"

cd "$PROJECT_DIR"

# -----------------------------------------------------------------------------
# 1. Backup do banco PostgreSQL
#    POSTGRES_USER/POSTGRES_DB vêm do ambiente do container (docker compose),
#    então não dependemos de parsear o .env aqui.
# -----------------------------------------------------------------------------
backup_ok=0
if docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
     > "$backup_file" 2>/tmp/backup_db_err.log; then
  if [ -s "$backup_file" ]; then
    backup_ok=1
    echo "Backup DB salvo: $backup_file ($(du -h "$backup_file" | cut -f1))"
  fi
fi

if [ "$backup_ok" != "1" ]; then
  echo "ERRO: backup do banco falhou ou saiu vazio." >&2
  if [ -f /tmp/backup_db_err.log ]; then sed 's/^/  pg_dump: /' /tmp/backup_db_err.log >&2 || true; fi
  rm -f "$backup_file"
  if [ "$ALLOW_NO_BACKUP" = "1" ]; then
    echo "AVISO: ALLOW_NO_BACKUP=1, seguindo sem backup." >&2
  else
    echo "Deploy interrompido: não há ponto de retorno." >&2
    echo "Se for intencional (ex.: banco fora do ar), rode com ALLOW_NO_BACKUP=1." >&2
    exit 1
  fi
fi

# -----------------------------------------------------------------------------
# 2. Backup da pasta media (imagens/screenshots dos trades)
# -----------------------------------------------------------------------------
if [ "$BACKUP_MEDIA" = "1" ]; then
  media_file="$BACKUP_DIR/media_${timestamp}.tar.gz"
  docker compose run --rm -v "$BACKUP_DIR:/backup" web \
    tar czf "/backup/media_${timestamp}.tar.gz" -C /app media 2>/dev/null || true
  if [ -f "$media_file" ]; then
    echo "Backup media salvo: $media_file"
  else
    echo "AVISO: backup de media falhou (container web pode estar parado)"
  fi
fi

# -----------------------------------------------------------------------------
# 3. Retenção: mantém apenas os N backups mais recentes
# -----------------------------------------------------------------------------
# `|| true` porque, sem nenhum arquivo, o `ls` retorna 1 e o pipefail derrubaria
# o script no ultimo passo, fazendo o deploy falhar depois de o backup ter dado certo.
ls -1t "$BACKUP_DIR"/backup_*.sql 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -- || true
ls -1t "$BACKUP_DIR"/media_*.tar.gz 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -- || true

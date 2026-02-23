#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load env vars if present
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$PROJECT_DIR/.env"
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
KEEP_BACKUPS="${KEEP_BACKUPS:-8}"
POSTGRES_DB="${POSTGRES_DB:-trader_portal}"
POSTGRES_USER="${POSTGRES_USER:-trader_user}"
BACKUP_MEDIA="${BACKUP_MEDIA:-1}"  # 1 = backup media (imagens), 0 = só banco

mkdir -p "$BACKUP_DIR"

timestamp="$(TZ="America/Sao_Paulo" date +"%Y-%m-%d_%H-%M")"
backup_file="$BACKUP_DIR/backup_${timestamp}.sql"

cd "$PROJECT_DIR"

# 1. Backup do banco PostgreSQL
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$backup_file"
echo "Backup DB saved: $backup_file"

# 2. Backup da pasta media (imagens/screenshots dos trades)
if [ "$BACKUP_MEDIA" = "1" ]; then
  media_file="$BACKUP_DIR/media_${timestamp}.tar.gz"
  docker compose run --rm -v "$BACKUP_DIR:/backup" web tar czf "/backup/media_${timestamp}.tar.gz" -C /app media 2>/dev/null || true
  if [ -f "$media_file" ]; then
    echo "Backup media saved: $media_file"
  else
    echo "AVISO: Backup media falhou (container web pode estar parado)"
  fi
fi

# Manter apenas os backups mais recentes
ls -1t "$BACKUP_DIR"/backup_*.sql 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm --
ls -1t "$BACKUP_DIR"/media_*.tar.gz 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm --

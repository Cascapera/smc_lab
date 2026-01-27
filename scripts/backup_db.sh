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

mkdir -p "$BACKUP_DIR"

timestamp="$(TZ="America/Sao_Paulo" date +"%Y-%m-%d_%H-%M")"
backup_file="$BACKUP_DIR/backup_${timestamp}.sql"

cd "$PROJECT_DIR"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$backup_file"

# Keep only the most recent backups
ls -1t "$BACKUP_DIR"/backup_*.sql 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm --

echo "Backup saved: $backup_file"

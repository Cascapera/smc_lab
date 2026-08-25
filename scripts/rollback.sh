#!/usr/bin/env bash
# =============================================================================
# Rollback do SMC Lab para uma versão estável anterior (tag ou SHA).
#
# Uso (no servidor, dentro do diretório do projeto):
#   bash scripts/rollback.sh                    # lista as versões disponíveis
#   bash scripts/rollback.sh estavel-pre-fase0  # volta para a tag informada
#   bash scripts/rollback.sh <sha> --yes        # sem confirmação (automação)
#
# O que ele faz:
#   1. Faz backup do banco antes de mexer em qualquer coisa
#   2. git reset --hard para a versão alvo
#   3. Rebuilda e sobe os containers
#   4. Roda collectstatic
#
# O que ele NÃO faz (de propósito):
#   - NÃO roda `migrate`. As migrações da Fase 0 são aditivas (coluna/tabela/
#     constraint nova), então o banco continuar à frente do código é seguro.
#     Reverter migração em produção é operação manual e deliberada.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

TARGET="${1:-}"
CONFIRM="${2:-}"

current_sha="$(git rev-parse --short HEAD)"
current_msg="$(git log -1 --format=%s)"

if [ -z "$TARGET" ]; then
  echo "Uso: bash scripts/rollback.sh <tag-ou-sha> [--yes]"
  echo ""
  echo "Versão rodando agora: ${current_sha} - ${current_msg}"
  echo ""
  echo "Versões estáveis marcadas:"
  git tag -l 'estavel-*' --sort=-creatordate | head -10 | sed 's/^/  /' || true
  echo ""
  echo "Últimos commits da main:"
  git log --oneline -10 origin/main 2>/dev/null | sed 's/^/  /' || true
  exit 1
fi

echo ">>> Buscando refs do origin"
git fetch origin --tags --quiet || echo "AVISO: git fetch falhou; usando refs locais"

if ! git rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null; then
  echo "ERRO: '${TARGET}' não é uma tag/commit conhecido neste repositório." >&2
  exit 1
fi

target_sha="$(git rev-parse --short "${TARGET}^{commit}")"
target_msg="$(git log -1 --format=%s "${TARGET}^{commit}")"

echo ""
echo "  DE:   ${current_sha} - ${current_msg}"
echo "  PARA: ${target_sha} - ${target_msg}"
echo ""

if [ "$current_sha" = "$target_sha" ]; then
  echo "Já está nessa versão. Nada a fazer."
  exit 0
fi

if [ "$CONFIRM" != "--yes" ] && [ -t 0 ]; then
  read -r -p "Confirmar rollback? Alterações locais não commitadas serão perdidas. [y/N] " answer
  case "$answer" in
    [yY]) ;;
    *) echo "Cancelado."; exit 1 ;;
  esac
fi

echo ">>> Backup do banco antes do rollback"
bash "$SCRIPT_DIR/backup_db.sh" || {
  echo "AVISO: backup falhou. Continuando com o rollback (o objetivo aqui é restabelecer o serviço)."
}

echo ">>> Voltando o código para ${TARGET}"
git reset --hard "${TARGET}"

echo ">>> Rebuild das imagens"
docker compose build web worker beat

echo ">>> Parando worker e beat antes de recriar"
docker compose stop worker beat || true

echo ">>> Subindo containers"
docker compose up -d

echo ">>> Aguardando containers"
sleep 10

echo ">>> Collectstatic"
docker compose exec -T web python manage.py collectstatic --noinput --clear || {
  echo "AVISO: collectstatic falhou; verifique os logs do container web."
}

echo ""
echo ">>> Rollback concluído. Versão atual: $(git rev-parse --short HEAD) - $(git log -1 --format=%s)"
echo ""
docker compose ps
echo ""
echo "Lembrete: o banco NÃO foi revertido. Se a versão anterior não for compatível"
echo "com o schema atual, restaure o dump em backups/ manualmente."

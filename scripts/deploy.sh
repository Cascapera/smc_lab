#!/bin/bash
# Deploy manual do SMC Lab, para quando o Actions nao estiver disponivel.
#
# O caminho normal e o workflow `Deploy` no GitHub Actions. Este script existe
# como plano B e PRECISA espelhar o que aquele faz: ja houve tres fluxos de
# deploy diferentes documentados ao mesmo tempo, e o que rodava no servidor nao
# era o que estava escrito aqui.
#
# Execute no servidor, a partir da pasta do projeto: bash scripts/deploy.sh

set -euo pipefail

cd "$(dirname "$0")/.."
echo ">>> Diretorio: $(pwd)"

echo ">>> Buscando a versao nova"
git fetch origin main
# Atualiza o script de backup ANTES de executa-lo: uma correcao no backup_db.sh
# so teria efeito no deploy seguinte, e depois de um rollback voltaria para a
# versao antiga do servidor.
git checkout origin/main -- scripts/backup_db.sh

echo ">>> Backup (DB + media)"
bash scripts/backup_db.sh

echo ">>> Atualizando o codigo"
git reset --hard origin/main

echo ">>> Build"
docker compose build web worker worker_interativo beat

echo ">>> Parando workers e beat antes de recriar"
docker compose stop worker worker_interativo beat || true

echo ">>> Subindo"
docker compose up -d

echo ">>> Aguardando containers"
sleep 15

echo ">>> Migrations"
docker compose exec -T web python manage.py migrate --noinput

echo ">>> Collectstatic"
docker compose exec -T web python manage.py collectstatic --noinput

echo ">>> Worker watchdog"
bash scripts/install_worker_watchdog.sh || true

echo ">>> Deploy concluido. Confira:"
echo "    docker compose ps                                   # seis servicos"
echo "    curl -s localhost:8000/healthz | head -c 400        # saude real"

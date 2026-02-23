#!/bin/bash
# Deploy SMC Lab: pull, build, migrate, collectstatic
# Execute no servidor a partir da pasta do projeto: ./scripts/deploy.sh

set -e

cd "$(dirname "$0")/.."
echo ">>> Diretório: $(pwd)"
echo ">>> Git pull..."
git pull
echo ">>> Docker build e up..."
docker-compose up -d --build
echo ">>> Migrations..."
docker-compose exec -T web python manage.py migrate --noinput
echo ">>> Collectstatic..."
docker-compose exec -T web python manage.py collectstatic --noinput
echo ">>> Deploy concluído."

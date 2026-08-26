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

# O passo seguinte faz `git reset --hard`. Se este script for movido para fora
# do repositorio, ele destroi o que houver na pasta em que cair.
git rev-parse --show-toplevel >/dev/null 2>&1 \
  || { echo "ERRO: $(pwd) nao e um repositorio git."; exit 1; }
test -f docker-compose.yml \
  || { echo "ERRO: nao ha docker-compose.yml em $(pwd)."; exit 1; }

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
SHA_CURTO="$(git rev-parse --short HEAD)"
echo ">>> Versao alvo: ${SHA_CURTO} - $(git log -1 --format=%s)"

echo ">>> Imagens de base (postgres, redis)"
docker compose pull --ignore-pull-failures

# Sem `--no-cache`: ele rebaixava a imagem base do Playwright (~2 GB) e
# reinstalava tudo a cada deploy, para resolver um problema que o cache do
# Docker nao tem - se o requirements.txt muda, a camada muda junto.
echo ">>> Build"
docker compose build web worker worker_interativo beat

# Migracoes num container efemero da imagem NOVA, com o codigo ANTIGO ainda
# servindo. Era o contrario (`up -d` -> `sleep 15` -> `migrate`), o que deixava
# codigo novo sobre schema antigo por uns 15s em todo deploy. Assim, migracao
# que falha aborta o deploy com a versao antiga intacta no ar.
echo ">>> Migrations (imagem nova, antes de trocar o que esta no ar)"
docker compose run --rm -T web python manage.py migrate --noinput

echo ">>> Parando workers e beat antes de recriar"
docker compose stop worker worker_interativo beat || true

echo ">>> Subindo"
docker compose up -d

# Sem `collectstatic` aqui: o Dockerfile ja o roda no build e falha se o
# staticfiles.json nao sair. STATIC_ROOT nao e volume, entao collectstatic em
# container rodando se perdia na recriacao seguinte.

# -----------------------------------------------------------------------------
# Validacao. HTTP sozinho nao basta: o site respondeu 200 durante um deploy em
# que a coleta estava completamente parada.
# -----------------------------------------------------------------------------
echo ">>> Esperando o gunicorn responder"
codigo=""
for _ in $(seq 1 30); do
  codigo="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/healthz || true)"
  # 503 conta como "de pe": e a resposta correta com o Redis fora ou a coleta
  # atrasada, e o site continua funcionando. 301 tambem, caso o
  # SECURE_PROXY_SSL_HEADER nao esteja no .env. O que se mede aqui e se o
  # processo responde; a saude real vem no /healthz logo abaixo.
  case "$codigo" in 200|301|302|503) break ;; esac
  codigo=""
  sleep 2
done

if [ -z "$codigo" ]; then
  echo "ERRO: o gunicorn nao respondeu em 60s."
  docker compose ps
  docker compose logs web --tail 50
  exit 1
fi
echo ">>> gunicorn respondeu (HTTP ${codigo})"

echo ">>> Servicos de pe"
docker compose ps
esperado=6
# `ps -q` conta so o que esta rodando e existe em toda versao do compose.
de_pe="$(docker compose ps -q | grep -c . || true)"
if [ "${de_pe:-0}" -ne "$esperado" ]; then
  echo "ERRO: ${de_pe:-0} de ${esperado} servicos rodando."
  docker compose logs --tail 30
  exit 1
fi

echo ">>> /healthz"
curl -s --max-time 5 -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8000/healthz | head -c 400
echo ""

# Nao aborta: logo depois de subir, o worker devolve -1 (ainda nao rodou task
# nenhuma) e o Beat so enfileira a coleta no proximo multiplo de 5.
echo ">>> Heartbeat do worker (segundos desde a ultima task; -1 = ainda nao rodou)"
docker compose exec -T worker python manage.py worker_heartbeat || true

# -----------------------------------------------------------------------------
# Marca as imagens com o SHA: serve para saber o que esta rodando e para voltar
# em segundos, sem rebuild -
#   docker tag smclab/web:<sha> smc_lab-web && docker compose up -d web
# -----------------------------------------------------------------------------
echo ">>> Marcando as imagens como ${SHA_CURTO}"
for svc in web worker worker_interativo beat; do
  cid="$(docker compose ps -q "$svc" || true)"
  [ -n "$cid" ] || continue
  docker tag "$(docker inspect --format '{{.Image}}' "$cid")" \
    "smclab/${svc}:${SHA_CURTO}"
  # Guarda as 5 marcas mais recentes por servico; o `docker images` ja lista da
  # mais nova para a mais velha. Elas nao sao dangling, entao o prune semanal
  # nao as recolheria sozinho.
  docker images --filter "reference=smclab/${svc}" \
    --format '{{.Repository}}:{{.Tag}}' | tail -n +6 \
    | xargs -r docker rmi >/dev/null 2>&1 || true
done

echo ">>> Worker watchdog"
bash scripts/install_worker_watchdog.sh || true

echo ">>> Deploy concluido: ${SHA_CURTO}"

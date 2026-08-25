#!/usr/bin/env bash
# =============================================================================
# Preflight de produção — diagnóstico ANTES do deploy de infraestrutura.
#
# Uso (no servidor, dentro do diretório do projeto):
#   bash scripts/preflight_prod.sh
#
# Só LÊ informação. Não altera nada, não reinicia nada.
#
# Serve para responder, com evidência, o que hoje é suposição:
#   - o worker/beat rodam com settings de dev? (hoje sim: nada define
#     DJANGO_SETTINGS_MODULE e o default do pacote é `dev`)
#   - o .env do servidor tem tudo que `settings.prod` EXIGE? Se faltar
#     SECRET_KEY, ALLOWED_HOSTS ou DATABASE_URL, trocar para prod derruba
#     worker e beat no boot;
#   - Postgres e Redis estão publicados na internet?
#
# IMPORTANTE: imprime apenas NOMES de variáveis e "definida/faltando".
# Nenhum valor de segredo é exibido, então a saída pode ser colada com segurança.
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
cd "$PROJECT_DIR"

ok()   { printf "  [ ok ]   %s\n" "$1"; }
warn() { printf "  [AVISO]  %s\n" "$1"; }
bad()  { printf "  [FALTA]  %s\n" "$1"; }

tem_chave() {
  [ -f "$ENV_FILE" ] || return 1
  grep -qE "^[[:space:]]*$1=..*" "$ENV_FILE" 2>/dev/null
}

echo "============================================================"
echo " PREFLIGHT DE PRODUÇÃO — SMC Lab"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo
echo "Versão em execução: $(git rev-parse --short HEAD) - $(git log -1 --format=%s)"
echo

# -----------------------------------------------------------------------------
echo "1) Variáveis EXIGIDAS por settings.prod (sem elas, worker/beat não sobem)"
# -----------------------------------------------------------------------------
faltando=0
for chave in DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS DATABASE_URL; do
  if tem_chave "$chave"; then ok "$chave definida"; else bad "$chave AUSENTE"; faltando=$((faltando + 1)); fi
done
echo

# -----------------------------------------------------------------------------
echo "2) Variáveis importantes para o comportamento em produção"
# -----------------------------------------------------------------------------
for chave in DJANGO_CSRF_TRUSTED_ORIGINS DJANGO_SECURE_PROXY_SSL_HEADER \
             CELERY_BROKER_URL CELERY_RESULT_BACKEND \
             POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
             MERCADOPAGO_ACCESS_TOKEN MERCADOPAGO_WEBHOOK_SECRET \
             DISCORD_BOT_TOKEN DISCORD_GUILD_ID OPENAI_API_KEY \
             DJANGO_EMAIL_HOST_USER DJANGO_EMAIL_HOST_PASSWORD; do
  if tem_chave "$chave"; then ok "$chave definida"; else warn "$chave ausente"; fi
done
echo

# -----------------------------------------------------------------------------
echo "3) Variáveis de DEV que não deveriam estar no servidor"
# -----------------------------------------------------------------------------
for chave in USE_SQLITE_LOCAL DATABASE_HOST DATABASE_PORT DJANGO_DEBUG; do
  if tem_chave "$chave"; then
    valor="$(grep -E "^[[:space:]]*$chave=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
    warn "$chave está definida (valor: $valor) — confira o efeito ao migrar para settings.prod"
  else
    ok "$chave não definida"
  fi
done
echo

# -----------------------------------------------------------------------------
echo "4) DJANGO_SETTINGS_MODULE em cada container"
# -----------------------------------------------------------------------------
if tem_chave DJANGO_SETTINGS_MODULE; then
  ok "DJANGO_SETTINGS_MODULE definido no .env: $(grep -E '^[[:space:]]*DJANGO_SETTINGS_MODULE=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
else
  warn "DJANGO_SETTINGS_MODULE NÃO definido no .env"
  echo "           web usa 'prod' (default do wsgi.py), mas worker, beat e o"
  echo "           'manage.py migrate' do deploy usam 'dev' (default do pacote)."
fi
for servico in web worker beat; do
  valor="$(docker compose exec -T "$servico" sh -c 'echo ${DJANGO_SETTINGS_MODULE:-<nao definido>}' 2>/dev/null | tr -d '\r')"
  if [ -n "$valor" ]; then
    printf "  %-8s DJANGO_SETTINGS_MODULE = %s\n" "$servico" "$valor"
  else
    printf "  %-8s (container não está rodando ou não respondeu)\n" "$servico"
  fi
done
echo
echo "  Settings efetivamente carregado por cada processo:"
for servico in web worker beat; do
  valor="$(docker compose exec -T "$servico" python -c 'from django.conf import settings; import os; print(os.environ.get("DJANGO_SETTINGS_MODULE", "(default do pacote)"))' 2>/dev/null | tr -d '\r')"
  printf "  %-8s %s\n" "$servico" "${valor:-(nao respondeu)}"
done
echo

# -----------------------------------------------------------------------------
echo "5) settings.prod carrega sem erro com o .env atual?"
# -----------------------------------------------------------------------------
saida="$(docker compose exec -T web sh -c 'DJANGO_SETTINGS_MODULE=trader_portal.settings.prod python manage.py check --deploy' 2>&1)"
codigo=$?
if [ $codigo -eq 0 ]; then
  ok "manage.py check --deploy passou com settings.prod"
  echo "$saida" | sed 's/^/         /' | tail -5
else
  bad "manage.py check --deploy FALHOU com settings.prod — NÃO faça o Deploy 4 antes de resolver"
  echo "$saida" | sed 's/^/         /' | tail -20
fi
echo

# -----------------------------------------------------------------------------
echo "6) Portas publicadas (Postgres/Redis expostos na internet?)"
# -----------------------------------------------------------------------------
docker compose ps --format '  {{.Service}}\t{{.Ports}}' 2>/dev/null || docker compose ps
echo
echo "  Bind 0.0.0.0 em 5432/6379 significa exposto conforme a regra de firewall"
echo "  do Lightsail. O Docker ignora o ufw."
echo

# -----------------------------------------------------------------------------
echo "7) Espaço em disco e tamanho dos logs de container"
# -----------------------------------------------------------------------------
df -h "$PROJECT_DIR" | sed 's/^/  /'
echo
du -sh "$PROJECT_DIR/backups" 2>/dev/null | sed 's/^/  backups: /' || echo "  backups: (não existe)"
echo

# -----------------------------------------------------------------------------
echo "8) Formatos de webhook que o Mercado Pago está enviando"
# -----------------------------------------------------------------------------
echo "  (aparece depois que o Deploy 2 estiver no ar; alimenta a Fase 1)"
docker compose logs web --since 168h 2>/dev/null | grep -c "topic desconhecido" \
  | sed 's/^/  ocorrencias de "topic desconhecido" nos ultimos 7 dias: /' || true
docker compose logs web --since 168h 2>/dev/null | grep "topic desconhecido" | tail -5 | sed 's/^/    /' || true
echo

echo "============================================================"
if [ "$faltando" -gt 0 ]; then
  echo " RESULTADO: $faltando variavel(is) obrigatoria(s) faltando."
  echo " NAO execute o Deploy 4 (settings.prod no worker/beat) antes de corrigir."
else
  echo " RESULTADO: variaveis obrigatorias presentes."
  echo " Confira ainda os itens 3, 5 e 6 antes do Deploy 4."
fi
echo "============================================================"

FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# deps do sistema (psql client, build essentials)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium já vêm no base image

COPY . .

# Settings de produção também aqui no build.
#
# Sem isto, `manage.py` usa o default do pacote (settings.dev) e o collectstatic
# roda com o StaticFilesStorage comum: a imagem sai SEM o staticfiles.json. O
# container então sobe com settings.prod, o storage de manifest carrega zero
# entradas e todo `{% static %}` estoura — o site inteiro responde 500. E como o
# manifest é lido uma única vez, na inicialização do processo, rodar
# collectstatic depois no container em execução não resolve: só reiniciando.
ENV DJANGO_SETTINGS_MODULE=trader_portal.settings.prod

# Valores só para o build: o collectstatic não toca no banco, mas o settings.prod
# valida a presença destas variáveis na importação.
RUN DJANGO_SECRET_KEY=chave-apenas-para-o-build-nao-usada-em-runtime \
    DJANGO_ALLOWED_HOSTS=build.local \
    DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    python manage.py collectstatic --noinput

# Trava de segurança: falha o build se o manifest não tiver sido gerado, em vez
# de descobrir isso com o site fora do ar.
RUN test -s /app/staticfiles/staticfiles.json \
    || (echo "ERRO: staticfiles.json nao foi gerado; a imagem quebraria em runtime" && exit 1)

CMD ["gunicorn", "trader_portal.wsgi:application", "-c", "gunicorn.conf.py", "--bind", "0.0.0.0:8000"]
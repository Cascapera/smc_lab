FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# deps do sistema (psql client, build essentials se precisar)
RUN apt-get update && apt-get install -y build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright (TradingView) + Chromium + dependências do sistema
RUN python -m playwright install --with-deps chromium

COPY . .

# coletar estáticos para servir com Whitenoise
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "trader_portal.wsgi:application", "--bind", "0.0.0.0:8000"]
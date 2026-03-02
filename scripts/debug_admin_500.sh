#!/usr/bin/env bash
# Debug do erro 500 no admin - executa no servidor e mostra o traceback
# Uso: bash scripts/debug_admin_500.sh

cd "$(dirname "$0")/.."
docker compose exec -T web python -c "
import os
import sys
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trader_portal.settings.prod')
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.filter(is_staff=True).first()
if not user:
    print('Nenhum usuário staff encontrado.')
    sys.exit(1)
print('Testando /admin/ com usuário:', user.email)
c = Client()
c.force_login(user)
# Usar host real para evitar DisallowedHost (testserver não está em ALLOWED_HOSTS)
host = os.environ.get('DEBUG_ADMIN_HOST', 'www.smclab.com.br')
# Client em DEBUG=False não expõe exceção; forçar captura via middleware
from django.conf import settings
old_debug = settings.DEBUG
settings.DEBUG = True
try:
    r = c.get('/admin/', HTTP_HOST=host, follow=True)
    print('Status final:', r.status_code, '(seguindo redirects)')
    if r.status_code == 500:
        # Com DEBUG=True o HTML da página de erro contém o traceback
        content = r.content.decode(errors='replace')
        if 'Traceback' in content:
            start = content.find('<pre class=\"exception_value\">')
            if start == -1:
                start = content.find('Traceback')
            if start != -1:
                excerpt = content[start:start+3000]
                print('Traceback (extraído):')
                print(excerpt)
        else:
            print('Resposta:', content[:1500])
finally:
    settings.DEBUG = old_debug
"

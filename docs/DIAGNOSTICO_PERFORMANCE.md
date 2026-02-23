# Diagnóstico de Performance

Guia para identificar se a lentidão vem do **servidor** ou do **sistema**.

---

## 1. Log de requests lentos (produção)

O middleware `RequestTimingMiddleware` registra no log qualquer request que leve **mais de 500ms**.

**Onde ver:** logs do Gunicorn/console em produção. Exemplo:

```
2025-02-18 14:32:01 [WARNING] trader_portal.middleware SLOW_REQUEST path=/trades/dashboard/ method=GET status=200 elapsed_ms=1203
```

**Interpretação:** Se aparecem muitos `SLOW_REQUEST` em horários normais, o sistema está pesado. Anote os `path` mais frequentes para otimizar.

---

## 2. Django Debug Toolbar (desenvolvimento)

Mostra **quantidade de queries SQL** e **tempo** de cada request.

**Como usar:**

```bash
# Instale a dependência (já em requirements.txt)
pip install django-debug-toolbar

# Rode com settings de dev
python manage.py runserver --settings=trader_portal.settings.dev
```

Acesse qualquer página. Um painel lateral aparece à direita com:

- **SQL**: número de queries e tempo total
- **Time**: tempo total do request

**Interpretação:** Se uma página faz 50+ queries ou >200ms em SQL, há N+1 ou queries pesadas para otimizar.

---

## 3. Teste de carga com Locust

Simula vários usuários acessando ao mesmo tempo.

**Como usar:**

```bash
# Instale
pip install locust

# Inicie o servidor em outro terminal
python manage.py runserver  # ou gunicorn -c gunicorn.conf.py trader_portal.wsgi:application

# Rode o Locust
locust -f locustfile.py --host=http://localhost:8000
```

Abra http://localhost:8089 e configure:

- **Number of users**: 10–20 para começar
- **Spawn rate**: 2 usuários/segundo
- Clique em **Start swarming**

**O que observar:**

| Métrica | Bom | Atenção |
|--------|-----|---------|
| RPS (requests/seg) | Estável | Cai com mais usuários |
| Latência mediana | < 500ms | > 1s |
| Taxa de falhas | 0% | > 1% |

**Interpretação:**

- **CPU/RAM do servidor sobem muito** com poucos usuários → aplicação pesada
- **CPU/RAM estáveis** mas latência alta → banco ou queries lentas
- **Tudo estável** até X usuários e depois degrada → limite do servidor

**Testar APIs do Painel SMC:**

```bash
locust -f locustfile.py --host=http://localhost:8000 -u 5 -r 1 --run-time 30s --headless
```

Para focar nas APIs de macro, edite o `locustfile.py` e use a classe `MacroAPIsUser`.

---

## 4. Log do Gunicorn com tempo

O `gunicorn.conf.py` inclui o tempo de resposta em cada linha de acesso.

**Como usar:**

```bash
gunicorn trader_portal.wsgi:application -c gunicorn.conf.py
```

Exemplo de linha:

```
127.0.0.1 - - [18/Feb/2025:14:32:01] "GET /trades/dashboard/ HTTP/1.1" 200 12345 "-" "Mozilla/5.0" 234000
```

O último valor está em **microsegundos** (234000 = 234ms). Divida por 1000 para obter milissegundos.

---

## 5. Monitorar o servidor

**CPU e memória (Linux):**

```bash
# Tempo real
top
# ou
htop

# Resumo
free -h        # memória
df -h          # disco
```

**Interpretação:**

- CPU perto de 100% em picos → servidor no limite
- RAM alta + swap ativo → falta de memória
- Disco I/O alto → leitura/escrita lenta (ex.: SQLite, logs)

---

## Resumo do fluxo

1. **Produção**: conferir logs de `SLOW_REQUEST` e do Gunicorn
2. **Dev**: usar Debug Toolbar para ver queries e tempo
3. **Teste**: rodar Locust e observar CPU/RAM + latência
4. **Servidor**: monitorar CPU, RAM e disco durante os testes

Com isso dá para saber se o gargalo é servidor ou aplicação.

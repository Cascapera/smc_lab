# Revisão de Código - App Macro

Revisão minuciosa do app `macro`, seguindo o checklist em `CHECKLIST_REVISAO_CODIGO.md`.

## Status das implementações

| Item | Status |
|------|--------|
| Scraping resiliente (timeout, retry) | ✅ Já implementado |
| Playwright usado de forma segura | ✅ Já implementado |
| Tasks Celery idempotentes | ✅ Já implementado |
| Dados coletados com integridade | ✅ Já implementado |
| Painel sem expor dados sensíveis | ✅ Já implementado |
| latest_scores/latest_variations restritos a staff | ❌ Revertido (mantido público) |
| Collector: extrair função score/variation (DRY) | ✅ Implementado |

---

## 1. `macro/models.py`

### Pontos positivos
- `MacroAsset` e `MacroVariation` bem estruturados
- `SourceChoices` com TextChoices
- Índices em `active`, `source_key`, `measurement_time`, `status`
- `unique_together` em `MacroVariation` (asset, measurement_time) evita duplicatas
- `__str__` definido em todos os modelos

### Pontos negativos / Melhorias

1. **FloatField** — `value_base`, `variation_decimal`, `variation_sum` usam `FloatField`. Para dados financeiros/métricos, `DecimalField` seria mais adequado para evitar erros de arredondamento. Porém, o painel exibe variações percentuais e scores inteiros; o impacto é baixo.

2. **MacroScore.variation_sum** — `FloatField`; consistente com `variation_decimal` em MacroVariation.

### Sugestões
- Considerar `DecimalField` em futuras migrações se precisão financeira for crítica.
- Manter como está para simplicidade; o uso atual (scores, variações %) é tolerante a float.

---

## 2. `macro/views.py`

### Pontos positivos
- `latest_scores` e `latest_variations` com `@require_GET`
- `_parse_limit` limita `max_limit=500` (evita abuso)
- `_parse_since` usa `parse_datetime` (seguro)
- `select_related("asset")` em `latest_variations` evita N+1
- `SMCDashboardView`, `SMCDashboardDemoView`, `SMCCleanView` protegidos por `PlanRequiredMixin` (Basic+)

### Pontos negativos / Melhorias

1. **Endpoints públicos** — `latest_scores` e `latest_variations` são acessíveis sem autenticação. Retornam dados agregados de mercado (scores, variações), não dados de usuário. **Aceitável** para consumo pelo painel (Basic+).

2. **Sem rate limiting** — Endpoints JSON públicos podem ser alvo de abuso. Considerar throttling se houver preocupação.

### Sugestões
- Manter público para o painel consumir via AJAX.

---

## 3. `macro/tasks.py`

### Pontos positivos
- `collect_macro_cycle` com `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3`
- Verificação `is_market_closed()` antes de executar (evita coleta fora do horário)
- Logging adequado (info, error com exc_info)
- Re-raise da exceção para o Celery fazer retry

### Pontos negativos / Melhorias

1. **Idempotência** — O ciclo usa `measurement_time` alinhado. `execute_cycle` faz `bulk_create(..., ignore_conflicts=True)` e `update_or_create` em MacroScore. Para o mesmo `measurement_time`, rodar duas vezes não duplica variações (unique_together + ignore_conflicts) e MacroScore é sobrescrito. **Idempotente.**

2. **Exception genérica** — `autoretry_for=(Exception,)` captura tudo. Poderia ser mais específico (ex.: `requests.RequestException`, `TimeoutError`), mas para uma task de coleta que deve ser resiliente, retentar em qualquer falha é razoável.

### Sugestões
- Manter como está. A task é bem configurada para resiliência.

---

## 4. `macro/services/collector.py`

### Pontos positivos
- `execute_cycle` verifica `is_market_closed` no início
- Fallback para TradingView fora do horário (usa última variação conhecida)
- `transaction.atomic()` para persistência (bulk_create + update_or_create)
- `bulk_create(..., ignore_conflicts=True)` evita duplicatas
- Delay entre fetches (`config.FETCH_DELAY_RANGE`) para não sobrecarregar fontes
- Tratamento de exceção por ativo: erro em um não interrompe os demais
- Logging detalhado

### Pontos negativos / Melhorias

1. **last_variations** — Query com `order_by("asset_id", "-measurement_time")` e iteração para pegar a primeira por asset. Poderia usar `distinct("asset_id")` (PostgreSQL) ou subquery para ser mais eficiente em muitos ativos. Para dezenas de ativos, é aceitável.

2. ~~**Código duplicado**~~ — **Corrigido**: Função `_compute_score_and_adjusted_variation(asset, variation_decimal)` extraída; usada no bloco de fallback TradingView e no bloco normal.

### Sugestões
- Considerar `distinct("asset_id")` se o número de ativos crescer muito.

---

## 5. `macro/services/network.py`

### Pontos positivos
- **Timeout** — `config.FETCH_TIMEOUT` (25s) em requests; `config.PLAYWRIGHT_TIMEOUT_MS` (60s) no Playwright
- **Retry** — `MAX_FETCH_ATTEMPTS` (3) com backoff entre tentativas
- **Fallback** — Investing: fallback para `r.jina.ai` em 403/429/503; depois Playwright; depois XHR discovery
- **Classificação de erros** — `_classify_playwright_error` para diagnóstico (timeout, proxy, IP block, etc.)
- **Proxy** — Suporte a proxy via env (PROXY_ENABLED, PROXY_SERVER, etc.)
- **Cache XHR** — Cache de endpoints XHR para Investing e TradingView (TTL configurável)
- **User-Agent rotativo** — Lista de USER_AGENTS para variar requisições
- Tratamento de captcha ("Just a moment", "Verify you are human")
- Logging de erros (warning) sem expor dados sensíveis

### Pontos negativos / Melhorias

1. **FALLBACK_HOST hardcoded** — `config.FALLBACK_HOST = "https://r.jina.ai"` está fixo. Jina AI é serviço externo; URL poderia vir de variável de ambiente para flexibilidade.

2. **Credenciais de proxy** — `PROXY_USERNAME` e `PROXY_PASSWORD` em env; não hardcoded. **Correto.**

3. **Playwright** — `browser.close()` é chamado; `sync_playwright()` usa context manager. Recursos são liberados. **Correto.**

4. **error_type não usado** — `_classify_playwright_error` retorna `(block_reason, error_type)` mas `error_type` só é usado em um log de discovery. Poderia ser usado em mais logs para diagnóstico.

### Sugestões
- Mover `FALLBACK_HOST` para variável de ambiente (ex.: `MACRO_FALLBACK_HOST`).
- Manter demais como está; a camada de rede está bem estruturada.

---

## 6. `macro/services/parsers.py`

### Pontos positivos
- Parsers separados por fonte (Investing, TradingView)
- `BeautifulSoup` com `html.parser` (seguro, sem execução de JS)
- Normalização de texto (unicode, espaços, vírgulas)
- Tratamento de JSON (Investing/TradingView podem retornar XHR em JSON)
- `parse_variation_percent` em utils com regex controlada

### Pontos negativos / Melhorias

1. **Nenhum dado sensível** — Parsers extraem apenas variação percentual e metadados de mercado. **Correto.**

2. **Recursão em _extract_*_json** — Busca em estruturas JSON aninhadas. Para payloads controlados (Investing, TradingView), profundidade limitada. Risco de stack overflow em JSON muito profundo é baixo.

### Sugestões
- Nenhuma alteração crítica.

---

## 7. `macro/services/utils.py`

### Pontos positivos
- `align_measurement_time` para alinhar horários ao intervalo
- `extract_relevant_text` remove scripts/estilos (segurança ao armazenar excerpt)
- `parse_variation_percent` com regex e tratamento de ValueError
- `is_market_closed` com lógica clara (sex 19h até dom 19h)

### Pontos negativos / Melhorias

1. **extract_relevant_text** — `max_chars=6000` limita tamanho. Evita armazenar HTML gigante. **Correto.**

### Sugestões
- Nenhuma alteração crítica.

---

## 8. `macro/services/config.py`

### Pontos positivos
- Timeouts e delays configuráveis
- Proxy via variáveis de ambiente
- `PLAYWRIGHT_TIMEOUT_MS` e `PLAYWRIGHT_WAIT_MS` configuráveis
- TTL de cache XHR configurável

### Pontos negativos / Melhorias

1. **FALLBACK_HOST** — Hardcoded. Sugerido mover para env.

2. **Valores padrão** — `FETCH_TIMEOUT=25`, `PLAYWRIGHT_TIMEOUT_MS=60000` são razoáveis.

### Sugestões
- Adicionar `FALLBACK_HOST = os.getenv("MACRO_FALLBACK_HOST", "https://r.jina.ai")`.

---

## 9. `macro/management/commands/import_macro_assets.py`

### Pontos positivos
- Validação de colunas obrigatórias
- `update_or_create` por nome (evita duplicatas)
- Tratamento de `pd.notna` para categoria opcional
- Detecção de source por URL (investing.com vs TradingView)

### Pontos negativos / Melhorias

1. **value_base como float** — `float(row["ValorBase"])` pode lançar se valor inválido. Considerar try/except com mensagem clara.

2. **truncate** — `MacroAsset.objects.all().delete()` em cascata remove `MacroVariation` (ForeignKey CASCADE). Correto, mas operação destrutiva; o flag `--truncate` deixa explícito.

### Sugestões
- Adicionar try/except em `value_base = float(...)` com CommandError em caso de valor inválido.

---

## 10. `macro/tests.py`

### Situação atual
- Testes implementados cobrindo: `parse_variation_percent`, `align_measurement_time`, `is_market_closed`, `parse_investing_variation`, `parse_tradingview_variation`, `_compute_score_and_adjusted_variation`, `execute_cycle` (com mock de fetch_html), `latest_scores`, `latest_variations` (limit, since), `SMCDashboardView` (PlanRequiredMixin).

---

## Resumo de Ações Prioritárias

| Prioridade | Arquivo | Ação | Status |
|------------|---------|------|--------|
| ~~Baixa~~ | ~~config.py~~ | ~~Mover FALLBACK_HOST para variável de ambiente~~ | Não implementado (conforme solicitado) |
| ~~Baixa~~ | ~~collector.py~~ | ~~Extrair função para cálculo de score/variation (DRY)~~ | ✅ Implementado |
| ~~Baixa~~ | ~~import_macro_assets.py~~ | ~~Try/except em value_base~~ | Não implementado (conforme solicitado) |
| ~~Média~~ | ~~views.py~~ | ~~Restringir latest_scores/latest_variations a staff~~ | ❌ Revertido |
| ~~Média~~ | ~~tests.py~~ | ~~Implementar testes para fluxos críticos~~ | ✅ Implementado |

---

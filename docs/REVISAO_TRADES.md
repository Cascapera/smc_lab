# Revisão de Código - App Trades

Revisão minuciosa do app `trades`, seguindo o checklist em `CHECKLIST_REVISAO_CODIGO.md`.

## Status das implementações (atualizado)

| Item | Status |
|------|--------|
| Extrair streaks, profit_factor, drawdown para analytics.py | ✅ Implementado |
| llm_service: timeout 90, retry, exceções, log, mensagem usuário | ✅ Implementado |
| admin.py: list_select_related | ✅ Implementado |
| reverse() nas mensagens customizadas | ✅ Implementado |
| user.profile em analytics | ✅ Implementado |
| forms.py: symbol em uppercase | ✅ Implementado |
| Testes | ✅ Implementado |

---

## 1. `trades/models.py`

### Pontos positivos
- Modelo `Trade` bem estruturado com `TextChoices` para enums
- Campos monetários com `Decimal` (evita float)
- `FileExtensionValidator` e `validate_image_file_size` no screenshot
- `MinValueValidator` em quantity
- `__str__` definido
- `AIAnalyticsRun` e `GlobalAIAnalyticsRun` para controle de limite semanal

### Pontos negativos / Melhorias

1. **Falta constraint de integridade** em `target_price` e `stop_price` — poderiam ter `MinValueValidator` se valores negativos não forem permitidos (em alguns mercados short, stop pode ser maior que entry).

2. **Índices** — `Trade` é filtrado frequentemente por `user`, `executed_at`, `market`, `result_type`. Considerar `db_index=True` ou `Meta.indexes` para consultas do dashboard.

3. **MuralView** — filtro de plano considera `plan_expires_at` (plan_expires_at__isnull ou plan_expires_at__gt=now). Correto.

### Sugestões
- Considerar índices compostos para consultas frequentes (user, executed_at).

---

## 2. `trades/views.py`

### Pontos positivos
- `TradeUpdateView` e `TradeDeleteView` filtram por `user` (ownership)
- `TradeScreenshotView` verifica owner, is_public ou staff
- `PlanRequiredMixin` e `StaffRequiredMixin` usados corretamente
- Tratamento de timezone em `executed_at`
- Mensagens de feedback

### Pontos negativos / Problemas

1. **TradeScreenshotView** — não usa `LoginRequiredMixin`; anônimo pode acessar se `is_public`. Isso é intencional (mural público). Mas `get_object_or_404(Trade, pk=pk)` não filtra user — qualquer um pode tentar ver screenshot de trade público pelo ID. Ok, a verificação is_owner/is_public/is_staff protege.

2. **Imports desorganizados** — `mark_safe` e `Profile` misturados; `_mural_display_name` definido antes dos imports de models (funciona por `from __future__ import annotations`).

3. **Código duplicado** — lógica de streaks (longest_win, longest_loss), profit_factor, payoff, drawdown repetida em `AdvancedDashboardView`, `AnalyticsIAView`, `GlobalDashboardView`, `GlobalAnalyticsIAView`. Extrair para `analytics.py`.

4. **AdvancedDashboardView.insufficient_message** — sobrescreve o mixin com mensagem customizada; link WhatsApp hardcoded. Mesmo padrão do PlanRequiredMixin.

5. **AnalyticsIAView.post** — `context = self.get_context_data()` sem `**kwargs` pode gerar erro; `get_context_data` espera `**kwargs`. Verificar: `get_context_data()` sem args funciona.

6. **Exception genérica** — `except Exception` no post da IA captura tudo; considerar logar e re-raise para erros inesperados, ou tratar apenas `OpenAIError`.

### Sugestões
- Extrair cálculo de streaks, profit_factor, payoff, drawdown para funções em `analytics.py`.
- Usar `reverse()` para URLs de planos nas mensagens customizadas.
- Melhorar tratamento de exceção na chamada LLM (logar traceback, tratar rate limit).

---

## 3. `trades/forms.py`

### Pontos positivos
- `TradeForm` com campos explícitos
- `clean()` para forçar `display_as_anonymous=True` quando `is_public=False`
- Widget `datetime-local` para `executed_at`

### Pontos negativos / Melhorias

1. **Validação de target/stop** — não há validação cruzada (ex.: target > stop em compra). Pode ser intencional (break even, etc.).

2. **Campo screenshot** — herda validadores do model; ok.

### Sugestões
- Considerar validação `clean` para consistência target/stop se regras de negócio exigirem.

---

## 4. `trades/analytics.py`

### Pontos positivos
- Separação clara entre `compute_user_dashboard` e `compute_global_dashboard`
- Uso de `Coalesce`, `Sum`, `Avg` para evitar None
- `_aggregate_by` reutilizável

### Pontos negativos / Melhorias

1. **compute_user_dashboard** — `Profile.objects.get_or_create(user=user)` pode ser substituído por `user.profile` (o signal de accounts já cria o profile). Redundante mas não incorreto.

2. **N+1** — `compute_user_dashboard` usa `Trade.objects.filter(user=user)`; se chamado em loop com muitos users, seria N+1. No contexto atual, é chamado por usuário logado, ok.

### Sugestões
- Usar `user.profile` se existir (evitar get_or_create desnecessário).

---

## 5. `trades/llm_service.py`

### Pontos positivos
- API key via settings (não hardcoded)
- Logging de erros
- Retorno vazio quando API key não configurada
- Model configurável

### Pontos negativos / Problemas

1. **Sem timeout** — chamada à OpenAI não tem timeout explícito; pode travar em rede lenta.

2. **Sem retry** — rate limit da OpenAI pode retornar 429; não há retry com backoff.

3. **Exception genérica** — `except Exception` engole tudo; considerar tratar `openai.RateLimitError`, `openai.APITimeoutError` com mensagens específicas.

### Sugestões
- Adicionar `timeout=60` (ou configurável) na chamada.
- Implementar retry com backoff para 429.
- Tratar exceções específicas da OpenAI.

---

## 6. `trades/ai_prompts.py`

### Pontos positivos
- Prompts bem estruturados
- Instruções claras para não inventar dados
- Sem dados sensíveis (apenas métricas agregadas, combinações)
- `build_analytics_user_prompt` e `build_global_analytics_user_prompt` separados

### Pontos negativos / Melhorias

1. **Nenhum dado de usuário identificável** nos prompts — correto para privacidade.

2. **Valores monetários** — `row.get('total', 0)` pode ser Decimal; conversão para string na formatação é implícita. Verificar se `f"R$ {row.get('total', 0)}"` funciona com Decimal (sim, funciona).

### Sugestões
- Nenhuma alteração crítica.

---

## 7. `trades/validators.py`

### Pontos positivos
- `validate_image_file_size` com limite configurável (1 MB)
- Tratamento de `image` None
- Mensagem de erro traduzível

### Pontos negativos / Melhorias

1. **validate_image_file_size** — recebe `image` que pode ser `UploadedFile`; `image.size` existe. Para `ImageField`, o Django passa o arquivo. Ok.

2. **Tipos de arquivo** — `FileExtensionValidator` no model cobre jpg, jpeg, png. O validator de tamanho não valida tipo; a combinação está correta.

### Sugestões
- Nenhuma alteração crítica.

---

## 8. `trades/signals.py`

### Pontos positivos
- `_recalculate_profile_balance` centraliza a lógica
- `post_save` e `post_delete` para manter saldo consistente
- Tratamento de `Profile.DoesNotExist`
- Uso de `last_reset_at` para filtrar trades

### Pontos negativos / Melhorias

1. **Performance** — a cada save/delete de Trade, recalcula o saldo com uma query de soma. Para usuário com muitos trades, pode ser lento. Considerar atualização incremental (somar/subtrair apenas o trade alterado) em cenários de alta carga.

### Sugestões
- Manter como está para simplicidade; otimizar apenas se houver problema de performance.

---

## 9. `trades/admin.py`

### Pontos positivos
- `list_display`, `list_filter`, `search_fields` bem configurados
- `screenshot_link` com `format_html` (seguro)
- `date_hierarchy` para navegação

### Pontos negativos / Melhorias

1. **TradeAdmin** — sem `list_select_related("user")`; pode haver N+1 ao listar.

2. **GlobalAIAnalyticsRunAdmin** — `readonly_fields` inclui `result`; o campo é editável no model. Se for intencional (não editar resultado), ok.

### Sugestões
- Adicionar `list_select_related = ("user",)` no TradeAdmin.

---

## 10. `trades/tests.py`

### Situação atual
- Testes implementados cobrindo: TradeForm (clean_symbol, clean), analytics (compute_streaks, compute_profit_factor_payoff, compute_drawdown_series, compute_advanced_metrics, compute_user_dashboard), views (CRUD, ownership, TradeScreenshotView, MuralView, DashboardView), llm_service (AnalyticsLLMError, run_analytics_llm sem API key, retry com exceção), tratamento de AnalyticsLLMError em AnalyticsIAView e GlobalAnalyticsIAView.

---

## 11. MuralView — filtro de plano

### Problema
O filtro em `MuralView.get_context_data` usa:
```python
Q(user__profile__plan__in=[Plan.BASIC, Plan.PREMIUM, Plan.PREMIUM_PLUS]),
Q(user__profile__plan_expires_at__isnull=True) | Q(user__profile__plan_expires_at__gt=now),
```
Isso está correto: considera expiração. Usuário com plano expirado tem `plan_expires_at < now`, então a segunda condição falha. **Correto.**

---

## Resumo de Ações Prioritárias

| Prioridade | Arquivo      | Ação                                                                 |
|------------|--------------|----------------------------------------------------------------------|
| Alta       | views.py     | Extrair lógica duplicada (streaks, profit_factor, drawdown) para analytics.py |
| Média      | llm_service  | Adicionar timeout e tratamento de rate limit/retry                   |
| Média      | admin.py     | list_select_related no TradeAdmin                                   |
| Média      | views.py     | Usar reverse() nas mensagens customizadas (AdvancedDashboardView, AnalyticsIAView) |
| Baixa      | tests.py     | Implementar testes para fluxos críticos                              |
| Baixa      | analytics.py | Usar user.profile em vez de get_or_create                           |

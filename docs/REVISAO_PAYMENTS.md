# Revisão de Código - App Payments

Revisão minuciosa do app `payments`, seguindo o checklist em `CHECKLIST_REVISAO_CODIGO.md`.

## Status das implementações

| Item | Status |
|------|--------|
| Webhook MercadoPago validado (assinatura x-signature) | ✅ Implementado |
| Valores em Decimal, nunca float | ✅ Já implementado |
| Idempotência em processamento de pagamento | ✅ _apply_plan idempotente |
| Logs de transações para auditoria | ✅ logger.exception no webhook e return |
| Sandbox vs produção claramente separados | ✅ MERCADOPAGO_USE_SANDBOX |
| Índices em mp_preapproval_id, external_reference | ✅ Implementado |
| Testes implementados | ✅ Implementado |

---

## 1. `payments/models.py`

### Pontos positivos
- `Payment` e `Subscription` com `DecimalField` para `amount` (evita float)
- `PaymentStatus` e `SubscriptionStatus` com TextChoices
- `raw_payload` (JSONField) para auditoria
- `__str__` definido
- ForeignKey para user com CASCADE

### Pontos negativos / Melhorias

1. **Índices** — Filtros frequentes por `user`, `status`, `mp_preapproval_id`, `external_reference`. Considerar `db_index=True` ou `Meta.indexes` para consultas do webhook e return.

2. **unique_together** — `mp_preapproval_id` e `mp_payment_id` podem ser únicos; evitar duplicatas se o webhook for chamado múltiplas vezes.

### Sugestões
- Adicionar índices em `mp_preapproval_id`, `external_reference` se houver muitas consultas.
- Manter como está se o volume for baixo.

---

## 2. `payments/views.py`

### Pontos positivos
- `CreateCheckoutView` e `PaymentReturnView` com `LoginRequiredMixin`
- Validação de plano em `CreateCheckoutView`
- Verificação de `MERCADOPAGO_BACK_URL` para localhost (orienta uso de ngrok)
- `external_reference` com user_id, plan_key e timestamp (rastreável)
- Tratamento de exceção em `create_preference` e `create_preapproval`
- `_apply_plan`, `_maybe_revoke_plan`, `_schedule_plan_end` centralizam lógica
- Sync de roles Discord após aplicar/revogar plano

### Pontos negativos / Problemas

1. ~~**Webhook sem validação de assinatura**~~ — **Corrigido**: Validação `x-signature` implementada em `validate_webhook_signature`. Quando `MERCADOPAGO_WEBHOOK_SECRET` está configurado, webhooks com assinatura inválida retornam 401. Secret vazio mantém comportamento anterior (retrocompatível).

2. ~~**Exception genérica**~~ — **Corrigido**: `logger.exception` no webhook e no return; exceções em `sync_user_roles` com `logger.debug`.

3. **Idempotência** — O webhook processa `payment_id`/`preapproval_id` e aplica plano. Se o mesmo webhook chegar duas vezes, `_apply_plan` é idempotente (aplicar o mesmo plano novamente não altera o resultado). Porém, criar `Subscription` no webhook quando não existe pode gerar duplicata se duas requisições chegarem em paralelo. Considerar `get_or_create` ou lock.

4. **Payment não persistido** — No fluxo `one_time`, o `Payment` não é criado no checkout; apenas no webhook/return quando há `payment_id`. O webhook cria `Subscription` mas não `Payment` para pagamento único. Verificar se o modelo `Payment` é usado em algum fluxo.

5. **float(amount)** — Em `CreateCheckoutView`, `unit_price` e `transaction_amount` usam `float(amount)`. O MercadoPago API aceita float; a conversão é necessária. O valor é armazenado como Decimal no modelo. **Aceitável.**

### Sugestões
- **Crítico**: Validar `x-signature` do webhook MercadoPago (secret em env).
- Logar exceções em vez de `pass`.
- Considerar `select_for_update()` ou transação para evitar race no webhook.

---

## 3. `payments/services/mercadopago.py`

### Pontos positivos
- `get_config()` centraliza configuração
- Timeout de 20s em todas as chamadas
- `raise_for_status()` ou verificação de `resp.ok`
- Token via `settings.MERCADOPAGO_ACCESS_TOKEN` (não hardcoded)
- `extract_payment_id` extrai de query params ou payload

### Pontos negativos / Melhorias

1. **URL fixa** — `https://api.mercadopago.com` está hardcoded. Em sandbox, a API é a mesma; o token define o modo. **Aceitável.**

2. **Sem retry** — Chamadas à API não têm retry para erros temporários (429, 503). Considerar retry com backoff para resiliência.

### Sugestões
- Adicionar retry para 429/503 se houver problemas de rate limit.
- Manter como está para simplicidade.

---

## 4. Sandbox vs Produção

### Pontos positivos
- `MERCADOPAGO_USE_SANDBOX = env.bool("MERCADOPAGO_USE_SANDBOX", default=DEBUG)` — em produção (DEBUG=False), sandbox é False por padrão.
- Token diferente para sandbox e produção (configurado via env).
- `MERCADOPAGO_TEST_PAYER_EMAIL` para sandbox (força email de teste no checkout).

### Sugestões
- Documentar no README ou env_production_template que em produção deve usar token de produção e `MERCADOPAGO_USE_SANDBOX=false`.

---

## 5. `payments/tests.py`

### Situação atual
- Testes implementados: `extract_payment_id`, `validate_webhook_signature`, PlanListView, CreateCheckoutView (mock), MercadoPagoWebhookView (assinatura, aceite sem secret), Payment e Subscription models.

---

## Resumo de Ações Prioritárias

| Prioridade | Arquivo | Ação | Status |
|------------|---------|------|--------|
| ~~**Alta**~~ | ~~views.py~~ | ~~Validar assinatura x-signature do webhook~~ | ✅ Implementado |
| ~~Média~~ | ~~views.py~~ | ~~Logar exceções em vez de pass~~ | ✅ Implementado |
| ~~Baixa~~ | ~~models.py~~ | ~~Índices em mp_preapproval_id, external_reference~~ | ✅ Implementado |
| ~~Média~~ | ~~tests.py~~ | ~~Implementar testes~~ | ✅ Implementado |

---

## Conclusão

O app **payments** está funcional, com modelos usando Decimal e separação sandbox/produção. O ponto crítico é a **falta de validação da assinatura do webhook**, que permite que terceiros enviem notificações falsas e ativem planos indevidamente. A implementação da validação `x-signature` é prioritária antes de produção.

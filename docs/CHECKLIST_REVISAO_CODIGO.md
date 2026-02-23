# Checklist de Revisão de Código - SMC Lab

Este documento guia a revisão completa do código do projeto, feita por **etapas/apps**. Use-o como guia para garantir qualidade, segurança e boas práticas.

---

## Estrutura do Projeto (Apps a Revisar)

| # | App | Descrição | Prioridade |
|---|-----|-----------|------------|
| 1 | **trader_portal** | Core do projeto (settings, URLs, Celery) | Alta |
| 2 | **accounts** | Autenticação, perfis, registro | Alta |
| 3 | **trades** | Operações, analytics, IA, dashboard | Alta |
| 4 | **macro** | Painel SMC, coletor, scraping | Alta |
| 5 | **payments** | Pagamentos, assinaturas, MercadoPago | Alta |
| 6 | **discord_integration** | Integração com Discord | Média |

---

## Checklist Geral (por App)

Use este checklist para **cada app** durante a revisão.

### 1. Segurança

- [ ] **Autenticação**: Rotas protegidas com `@login_required` ou `LoginRequiredMixin`
- [ ] **Autorização**: Verificação de permissão/ownership antes de operações sensíveis
- [ ] **CSRF**: Formulários com `{% csrf_token %}`
- [ ] **Injeção**: Uso de ORM/parametrização (evitar SQL raw ou concatenação)
- [ ] **Validação de entrada**: Dados validados em forms/serializers
- [ ] **Secrets**: Nenhuma chave/senha hardcoded
- [ ] **XSS**: Output escapado nos templates (`{{ }}` ou `escape`)

### 2. Arquitetura e Organização

- [ ] **Separação de responsabilidades**: Views finas, lógica em services/formatters
- [ ] **DRY**: Sem duplicação desnecessária de código
- [ ] **Imports**: Organizados, sem imports circulares
- [ ] **Nomenclatura**: Consistente, clara e em inglês (ou padrão do projeto)
- [ ] **Tamanho das funções**: Funções/métodos com responsabilidade única e tamanho razoável

### 3. Django / Padrões

- [ ] **Models**: `Meta` adequada, `__str__`, índices onde necessário
- [ ] **Queries**: Uso de `select_related`/`prefetch_related` para evitar N+1
- [ ] **Transações**: Operações críticas em `atomic()` quando apropriado
- [ ] **Forms**: Validação no form, não na view
- [ ] **URLs**: Padrões RESTful e nomes descritivos
- [ ] **Signals**: Uso correto, sem lógica pesada desnecessária

### 4. Performance

- [ ] **Consultas**: Sem N+1 queries
- [ ] **Cache**: Considerado onde aplicável (views, templates, dados externos)
- [ ] **Tasks assíncronas**: Operações pesadas em Celery
- [ ] **Arquivos estáticos**: Configuração adequada (WhiteNoise, etc.)

### 5. Tratamento de Erros

- [ ] **Exceções**: Capturadas e tratadas, quando necessário
- [ ] **Logging**: Erros e eventos importantes logados
- [ ] **Mensagens ao usuário**: Feedback adequado em falhas
- [ ] **404/500**: Páginas de erro configuradas (opcional em dev)

### 6. Testabilidade

- [ ] **Testes**: Cobertura mínima para fluxos críticos
- [ ] **Dependências injetáveis**: Facilitar mocks em testes
- [ ] **Fixtures/factories**: Dados de teste organizados

### 7. Código Legado e Manutenção

- [ ] **Documentação**: Docstrings em funções/classes complexas
- [ ] **Comentários**: Apenas onde agregam valor (evitar "comentários óbvios")
- [ ] **Tipos**: Type hints onde ajuda (Python 3.10+)
- [ ] **Código morto**: Sem funções/imports não utilizados

### 8. Específico por Domínio

- [ ] **Integrações externas**: Tratamento de timeout, retry, fallback
- [ ] **Webhooks**: Validação de assinatura/origem
- [ ] **Upload de arquivos**: Validação de tipo e tamanho
- [ ] **APIs de terceiros**: Chaves em variáveis de ambiente

---

## Checklist Específico por App

### App: trader_portal ✅ (concluído)

- [x] Settings divididos corretamente (base/dev/prod)
- [x] Variáveis sensíveis via `environ`
- [x] SECRET_KEY não default em produção
- [x] DEBUG=False em produção
- [x] ALLOWED_HOSTS configurado
- [x] CSRF/Session cookies seguros em produção
- [x] Celery beat schedule correto
- [x] CORS configurado se houver API externa

### App: accounts ✅ (concluído)

- [x] User model customizado (AbstractUser, email único)
- [x] Registro seguro (validação de email, senha forte via validators)
- [x] Profile com campos sensíveis protegidos (Discord excluído do ProfileEditForm)
- [x] Login/logout seguros
- [x] Mixins de permissão usados corretamente
- [x] Signals simplificados (create_or_update_profile)
- [x] Recuperação de senha apenas por e-mail
- [x] views.py usa get_user_model()
- [x] profile.html usa get_active_plan_display
- [x] set_plan.py inclui Plan.PREMIUM_PLUS
- [x] Testes implementados
- [x] Rate limiting em login e registro

### App: trades ✅ (concluído)

- [x] Model Trade com validações (FileExtensionValidator, MinValueValidator)
- [x] Analytics sem vazamento de dados entre usuários (compute_user_dashboard por user)
- [x] Integração OpenAI com timeout 90s, retry com backoff, AnalyticsLLMError, mensagem amigável
- [x] Screenshots/upload com validação (tipo e tamanho)
- [x] AI prompts sem dados sensíveis
- [x] Testes implementados (forms, analytics, views, llm_service)

### App: macro ✅ (concluído)

- [x] Scraping resiliente (timeout, retry)
- [x] Playwright usado de forma segura
- [x] Tasks Celery idempotentes quando possível
- [x] Dados coletados com integridade
- [x] Painel sem expor dados sensíveis
- [x] Collector: função _compute_score_and_adjusted_variation (DRY)
- [x] Testes implementados (utils, parsers, collector, views)

### App: payments ✅ (concluído)

- [x] Webhook MercadoPago validado (assinatura x-signature)
- [x] Valores em Decimal, nunca float
- [x] Idempotência em processamento de pagamento
- [x] Logs de transações para auditoria (logger.exception)
- [x] Sandbox vs produção claramente separados
- [x] Índices em mp_preapproval_id, external_reference
- [x] Testes implementados

### App: discord_integration ✅ (concluído)

- [x] OAuth flow seguro (state CSRF, validação de state/code)
- [x] Tokens armazenados/compartilhados com segurança (access_token não persistido)
- [x] Sincronização de roles sem sobrescrever incorretamente
- [x] Rate limit da API Discord respeitado
- [x] Testes implementados (services, views)

---

## Ordem Sugerida de Revisão

1. **trader_portal** – Base do projeto
2. **accounts** – Fundação de autenticação
3. **trades** – App principal de negócio
4. **macro** – Funcionalidade crítica (painel)
5. **payments** – Fluxo financeiro sensível
6. **discord_integration** – Integração auxiliar

---

## Como Usar Este Checklist

1. Escolha um app para revisar.
2. Leia o código do app (models, views, forms, services, etc.).
3. Marque os itens do checklist conforme for analisando.
4. Documente **pontos fracos** e **sugestões de melhoria** em um arquivo separado ou em comentários inline.
5. Priorize alterações: críticas (segurança) → importantes (performance/bugs) → melhorias (refatoração).

---

## Próximos Passos

1. **trader_portal** — Revisão concluída.
2. **accounts** — Revisão concluída. Ver `REVISAO_ACCOUNTS.md`.
3. **trades** — Revisão concluída. Ver `REVISAO_TRADES.md`.
4. **macro** — Revisão concluída. Ver `REVISAO_MACRO.md`.
5. **payments** — Revisão concluída. Ver `REVISAO_PAYMENTS.md`.
6. **discord_integration** — Revisão concluída. Ver `REVISAO_DISCORD_INTEGRATION.md`.

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

### App: trader_portal

- [ ] Settings divididos corretamente (base/dev/prod)
- [ ] Variáveis sensíveis via `environ`
- [ ] SECRET_KEY não default em produção
- [ ] DEBUG=False em produção
- [ ] ALLOWED_HOSTS configurado
- [ ] CSRF/Session cookies seguros em produção
- [ ] Celery beat schedule correto
- [ ] CORS configurado se houver API externa

### App: accounts

- [ ] User model customizado se necessário
- [ ] Registro seguro (validação de email, senha forte)
- [ ] Profile com campos sensíveis protegidos
- [ ] Login/logout seguros
- [ ] Mixins de permissão usados corretamente
- [ ] Signals sem efeitos colaterais pesados

### App: trades

- [ ] Model Trade com constraints e validações
- [ ] Analytics sem vazamento de dados entre usuários
- [ ] Integração OpenAI com tratamento de erro e rate limit
- [ ] Screenshots/upload com validação
- [ ] AI prompts sem dados sensíveis

### App: macro

- [ ] Scraping resiliente (timeout, retry)
- [ ] Playwright usado de forma segura
- [ ] Tasks Celery idempotentes quando possível
- [ ] Dados coletados com integridade
- [ ] Painel sem expor dados sensíveis

### App: payments

- [ ] Webhook MercadoPago validado (assinatura)
- [ ] Valores em Decimal, nunca float
- [ ] Idempotência em processamento de pagamento
- [ ] Logs de transações para auditoria
- [ ] Sandbox vs produção claramente separados

### App: discord_integration

- [ ] OAuth flow seguro
- [ ] Tokens armazenados/compartilhados com segurança
- [ ] Sincronização de roles sem sobrescrever incorretamente
- [ ] Rate limit da API Discord respeitado

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

Assim que você indicar qual app deseja revisar primeiro, iniciaremos a análise detalhada desse app usando este checklist.

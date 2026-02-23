# Revisão de Código - App Discord Integration

Revisão minuciosa do app `discord_integration`, seguindo o checklist em `CHECKLIST_REVISAO_CODIGO.md`.

## Status das implementações

| Item | Status |
|------|--------|
| OAuth flow seguro | Em análise |
| Tokens armazenados/compartilhados com segurança | Em análise |
| Sincronização de roles sem sobrescrever incorretamente | Em análise |
| Rate limit da API Discord respeitado | Em análise |

---

## 1. `discord_integration/views.py`

### Pontos positivos
- `DiscordLoginView`, `DiscordCallbackView`, `DiscordUnlinkView` com `LoginRequiredMixin`
- **State OAuth**: `secrets.token_urlsafe(16)` para CSRF no OAuth
- Validação de state: `state == expected_state` antes de trocar code por token
- Verificação de configuração (client_id, client_secret, redirect_uri) antes de iniciar OAuth
- Mensagens de erro adequadas ao usuário
- Logging de falhas em `sync_profile_roles` e `sync_user_roles.delay`

### Pontos negativos / Melhorias

1. **Exception genérica** — `except Exception` no DiscordLoginView engole erros. Considerar logar antes de redirecionar.

2. **Mensagem com exc** — `messages.error(request, f"Erro ao conectar com o Discord. {exc}")` pode expor detalhes internos ao usuário. Preferir mensagem genérica e logar o exc.

3. **Unlink expõe discord_id** — `messages.success(request, f"Discord desvinculado ({discord_id}).")` exibe o ID do Discord. Baixo risco, mas pode ser simplificado para "Discord desvinculado com sucesso."

### Sugestões
- Logar exceção no DiscordLoginView antes de redirecionar.
- Usar mensagem genérica no callback em vez de expor `exc`.
- Simplificar mensagem de unlink (opcional).

---

## 2. `discord_integration/services.py`

### Pontos positivos
- **RateLimiter** — 10 chamadas/segundo com deque e lock
- **Retry em 429** — `_bot_request` detecta 429, aguarda `retry_after` e retenta
- **Timeout** — 20s em todas as chamadas requests
- Credenciais via `settings` (não hardcoded)
- `scope="identify"` — mínimo necessário para OAuth
- `sync_profile_roles` — adiciona role desejada, remove as demais (Basic, Premium, Premium+)
- Logging de erros (401, 403, 404, falhas)
- `_validate_bot_config` antes de operações com bot

### Pontos negativos / Melhorias

1. **Tokens não armazenados** — O `access_token` é usado apenas para `fetch_discord_user` e descartado. Não é persistido. **Correto** para fluxo OAuth com scope identify.

2. **Sincronização de roles** — A lógica em `sync_profile_roles`:
   - Obtém `desired_role` para o plano ativo
   - Adiciona `desired_role` se não estiver em `current_roles`
   - Remove as outras roles (basic, premium, premium_plus) se estiverem em `current_roles`
   - **Correto**: não sobrescreve roles de outros bots/sistemas; apenas gerencia as 3 roles do SMC Lab.

3. **remove_all_roles** — Remove apenas as 3 roles configuradas. Não remove todas as roles do usuário. **Correto.**

4. **Hierarquia de planos** — `desired_role_for_plan` retorna uma role por plano. Premium+ tem role diferente de Premium e Basic. A sincronização garante que o usuário tenha apenas a role do plano ativo. **Correto.**

### Sugestões
- Nenhuma alteração crítica.

---

## 3. `discord_integration/tasks.py`

### Pontos positivos
- `sync_user_roles` e `sync_all_discord_roles` como tasks Celery
- Verificação de `discord_user_id` antes de sincronizar
- Logging de exceções com `exc_info=True`
- `sync_all_discord_roles` itera sobre perfis com Discord; cada falha não interrompe os demais

### Pontos negativos / Melhorias

1. **N+1** — `sync_all_discord_roles` faz um loop com `sync_profile_roles` por perfil. Cada perfil implica chamadas à API Discord. Para muitos usuários, pode ser lento. Considerar batch ou throttle entre perfis. Para uso típico (sync diário), é aceitável.

### Sugestões
- Manter como está; o rate limiter em services já controla a frequência.

---

## 4. `discord_integration/urls.py`

### Pontos positivos
- URLs descritivas: login, callback, unlink
- Namespace `discord`

### Sugestões
- Nenhuma alteração.

---

## 5. `discord_integration/tests.py` ✅

### Situação atual
- Testes implementados em `discord_integration/tests.py`.

### Cobertura
- **Services**: `build_oauth_url` (URL com state, client_id, scope), `desired_role_for_plan` (Basic, Premium, Premium+, Free), `sync_profile_roles` (adiciona role, sem discord_user_id não faz nada)
- **Views**: `DiscordLoginView` (anônimo → login, autenticado → OAuth, Discord não configurado → profile), `DiscordCallbackView` (state inválido, sem code, callback válido salva perfil), `DiscordUnlinkView` (remove Discord, sem vinculação retorna warning)

---

## Resumo de Ações Prioritárias

| Prioridade | Arquivo | Ação | Status |
|------------|---------|------|--------|
| Baixa | views.py | Logar exceção no DiscordLoginView | ✅ |
| Baixa | views.py | Mensagem genérica no callback (não expor exc) | ✅ |
| Baixa | views.py | Simplificar mensagem de unlink | ✅ |
| Média | tests.py | Implementar testes para fluxos críticos | ✅ |

---



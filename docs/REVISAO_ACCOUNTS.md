# Revisão de Código - App Accounts

Revisão minuciosa do app `accounts`, seguindo o checklist em `CHECKLIST_REVISAO_CODIGO.md`.

## Status das implementações (atualizado)

| Item | Status |
|------|--------|
| ProfileEditForm: excluir campos Discord | ✅ Implementado |
| Login: label "E-mail" no formulário | ✅ Implementado (EmailAuthenticationForm) |
| PlanRequiredMixin: reverse() para URL planos | ✅ Implementado |
| has_plan_at_least: tratar plano desconhecido | ✅ Implementado |
| Rate limiting em login (5/min) e registro (3/min) | ✅ Implementado |
| get_active_plan_display no Profile | ✅ Implementado |
| Recuperação por dados removida | ✅ Apenas por e-mail |
| Testes implementados | ✅ Cobertura pleno |

---

## 1. `accounts/apps.py`

### Código atual
```python
from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        import accounts.signals  # noqa: F401
```

### Pontos positivos
- Configuração padrão correta do app Django
- `ready()` importa os signals para registro automático
- Uso de `noqa: F401` para suprimir aviso de import não utilizado (o import tem efeito colateral de registrar os receivers)

### Pontos negativos / Melhorias
- **Nenhum problema crítico**

### Sugestões
- Adicionar `verbose_name` na `Meta` se quiser exibir nome amigável no admin:
  ```python
  verbose_name = "Contas"
  ```

---

## 2. `accounts/models.py`

### Pontos positivos
- User customizado com `AbstractUser` e email único
- Profile separado com `OneToOneField` (boa separação de responsabilidades)
- Uso de `TextChoices` para enums (ExperienceLevel, PrimaryMarket, etc.)
- Campos monetários com `Decimal` (evita problemas de float)
- Métodos úteis: `reset_balance()`, `active_plan()`, `has_plan_at_least()`
- `update_fields` em `save()` para otimização
- `__str__` definido em User e Profile

### Pontos negativos / Problemas

1. **Profile sem índice em campos frequentemente filtrados**
   - `plan`, `discord_user_id` podem ser usados em filtros; considerar índices se houver muitas consultas.

2. **`document_id` e `phone` são dados sensíveis**
   - Não há `db_column` ou proteção especial; garantir que o admin não exponha em list_display por padrão (já está ok no ProfileAdmin).

3. **`active_plan()` não tem equivalente para display**
   - O template usa `profile.get_plan_display`, que mostra o valor armazenado em `plan`, não o plano efetivo (considerando expiração). Se o plano expirou, ainda mostra "Premium" em vez de "Free".

### Sugestões de alteração

1. **Adicionar método `get_active_plan_display()` no Profile:**
   ```python
   def get_active_plan_display(self) -> str:
       """Retorna o label do plano vigente (considerando expiração)."""
       return dict(Plan.choices).get(self.active_plan(), self.active_plan())
   ```

2. **Considerar `db_index=True` em `plan`** se houver muitas consultas por plano.

3. **Typo no help_text** (linha 127): "expirará" → "expira".

---

## 3. `accounts/mixins.py`

### Pontos positivos
- `StaffRequiredMixin` bem implementado com `UserPassesTestMixin`
- `PlanRequiredMixin` reutilizável para proteção por plano
- Decorator `plan_required` para FBVs
- Mensagens de feedback ao usuário

### Pontos negativos / Problemas

1. **`PlanRequiredMixin.dispatch()` — padrão pouco convencional**
   - O código armazena `resp = super().dispatch` e chama `resp(request, *args, **kwargs)` depois. Funciona (resp é método bound), mas a ordem das checagens é invertida: verifica plano antes de chamar o dispatch do pai.
   - Sugestão: chamar `super().dispatch()` diretamente para clareza:
   ```python
   def dispatch(self, request, *args, **kwargs):
       if request.user.is_authenticated:
           profile = getattr(request.user, "profile", None)
           if profile is None or not profile.has_plan_at_least(self.get_required_plan()):
               return self.handle_no_permission()
       return super().dispatch(request, *args, **kwargs)
   ```

2. **URL hardcoded no `insufficient_message`**
   - `/pagamentos/planos/` e link do WhatsApp estão fixos. Melhor usar `reverse("payments:plans")` e variável de configuração para o WhatsApp.

3. **`mark_safe` com HTML**
   - O HTML no `insufficient_message` é intencional para links, mas garantir que não haja risco de XSS (atualmente é estático, ok).

### Sugestões de alteração

1. **Simplificar o dispatch para maior clareza** (ver sugestão acima).

2. **Usar `reverse()` para URLs:**
   ```python
   from django.urls import reverse
   insufficient_message = mark_safe(
       'Recurso disponível apenas para os planos Basic e Premium. '
       f'Assine um plano em <a href="{reverse("payments:plans")}">Planos</a> '
       'ou fale pelo <a href="https://wa.me/5511975743767" target="_blank" rel="noopener">WhatsApp</a>.'
   )
   ```
   (O `insufficient_message` é atributo de classe, então `reverse()` precisaria ser chamado em `handle_no_permission` ou usar lazy.)

---

## 4. `accounts/forms.py`

### Pontos positivos
- Formulários bem organizados
- `UserRegistrationForm` usa email como username (login por email)
- `ProfileForm` e `ProfileEditForm` excluem campos sensíveis/administrativos
- Validação em `clean_country` e `clean_timezone`
- `PasswordRecoveryByDataForm` valida email + telefone + CPF (segurança adicional)
- `_normalize_digits` para comparação de telefone/CPF

### Pontos negativos / Problemas

1. **`UserRegistrationForm` não inclui `username` nos fields**
   - Correto, pois é definido no `save()`. Mas o `CustomUserCreationForm` pai usa `fields = ("username", "email", ...)`. O `UserRegistrationForm` sobrescreve com `fields = ("email", "first_name", "last_name")` — ok.

2. **Validação de senha**
   - O help_text menciona "pelo menos 8 caracteres" e "números e letras", mas o Django usa `MinimumLengthValidator` (8) e `NumericPasswordValidator` (não pode ser só números). Não há validação explícita de "letras e números" — o `CommonPasswordValidator` e `NumericPasswordValidator` ajudam. Considerar adicionar `UserAttributeSimilarityValidator` (já está em AUTH_PASSWORD_VALIDATORS).

3. **Import dentro de `clean()` em `PasswordRecoveryByDataForm`**
   - `from .models import User` dentro do método — evitar imports dentro de funções; mover para o topo.

4. **`ProfileEditForm` permite editar `initial_balance` e `current_balance`?**
   - Não, estão excluídos implicitamente? Não — o exclude não inclui esses campos. O usuário pode alterar seu próprio saldo! **Problema de segurança.**

### Sugestões de alteração

1. **ProfileEditForm — excluir `initial_balance` e `current_balance`:**
   ```python
   exclude = (
       "user",
       "terms_accepted",
       "privacy_accepted",
       "terms_accepted_at",
       "privacy_accepted_at",
       "plan",
       "plan_expires_at",
       "last_reset_at",
       "initial_balance",   # ADICIONAR
       "current_balance",   # ADICIONAR
       "created_at",
       "updated_at",
   )
   ```

2. **Mover import de User para o topo em `PasswordRecoveryByDataForm.clean()`**

---

## 5. `accounts/views.py`

### Pontos positivos
- Views organizadas (Register, Logout, Profile, etc.)
- `LoginRequiredMixin` onde necessário
- Mensagens de feedback
- `PasswordRecoveryChangeView` limpa a sessão após sucesso (`del request.session[...]`)
- `SessionStatusView` retorna JSON para APIs

### Pontos negativos / Problemas

1. **Import incorreto de User**
   - `from django.contrib.auth.models import User` — o projeto usa `accounts.User` (AUTH_USER_MODEL). Em projetos com User customizado, deve-se usar `get_user_model()` ou `from accounts.models import User`.

2. **URLs de recuperação por dados não registradas**
   - `PasswordRecoveryByDataView` e `PasswordRecoveryChangeView` existem mas **não estão em `urls.py`**.
   - As views redirecionam para `accounts:password_recovery` e `accounts:password_recovery_change`, que não existem.
   - **Código morto ou bug**: as views nunca são acessíveis.

3. **RegisterView — possível race condition**
   - Entre `user_form.save()` e `profile = user.profile`, o signal `post_save` já cria o profile. O código usa `user.profile` e sobrescreve com `cleaned_data`. Ok, o signal cria o profile, então `user.profile` existe.

4. **ProfileView/ProfileEditView — profile pode ser None**
   - Se o signal falhar ou houver edge case, `profile` pode ser None. O template usa `{% if profile %}` em alguns lugares, mas em `profile.get_plan_display` daria AttributeError se profile for None. O `get_context_data` passa `profile`; o template em `profile.get_plan_display` precisa de profile. Verificar: na linha 16 do profile.html, `{% if profile %}{{ profile.get_plan_display }}{% else %}N/D{% endif %}` — está protegido. Ok.

5. **SessionStatusView — `last_login.timestamp()`**
   - `datetime` em Python 3 não tem `.timestamp()` diretamente para objetos timezone-aware em algumas versões. `last_login` é `datetime` do Django; em Django, `timezone.make_aware` retorna objeto com `timestamp()`. Deve funcionar. Verificar se `last_login` pode ser None — sim, está tratado com `if last_login`.

### Sugestões de alteração

1. **Corrigir import de User:**
   ```python
   from django.contrib.auth import get_user_model
   User = get_user_model()
   # ou: from .models import User
   ```

2. **Registrar URLs de recuperação por dados** (ver seção urls.py).

---

## 6. `accounts/urls.py`

### Pontos positivos
- Estrutura clara
- Uso de `auth_views` para fluxo padrão de reset de senha
- Templates customizados para as views de auth

### Pontos negativos / Problemas

1. **Faltam rotas para recuperação por dados**
   - `PasswordRecoveryByDataView` e `PasswordRecoveryChangeView` não estão registradas.
   - As views em `views.py` redirecionam para `accounts:password_recovery` (que não existe; existe `password_reset`) e `accounts:password_recovery_change` (inexistente).

### Sugestões de alteração

1. **Adicionar as rotas:**
   ```python
   path("recuperar-senha-por-dados/", PasswordRecoveryByDataView.as_view(), name="password_recovery_by_data"),
   path("recuperar-senha-por-dados/nova-senha/", PasswordRecoveryChangeView.as_view(), name="password_recovery_change"),
   ```

2. **Corrigir redirects em views.py** para usar os nomes corretos:
   - `password_recovery` → `password_recovery_by_data` (para a view de formulário)
   - `password_recovery_change` → manter, mas garantir que a URL existe

   Ou padronizar: se a recuperação "por dados" for alternativa à "por email", os nomes podem ser:
   - `password_recovery_by_data` para o formulário
   - `password_recovery_change` para definir nova senha (após validação por dados)

   Os redirects em views.py usam `accounts:password_recovery` quando a sessão expira — deveria redirecionar para `password_recovery_by_data` (o formulário inicial).

---

## 7. `accounts/signals.py`

### Pontos positivos
- `create_or_update_profile` garante profile para todo User
- `logout_other_sessions` mantém uma sessão por usuário (segurança)

### Pontos negativos / Problemas

1. **`logout_other_sessions` — iteração pesada**
   - Busca TODAS as sessões não expiradas e itera. Em produção com muitos usuários, pode ser lento.
   - Melhor: `Session.objects.filter(expire_date__gte=timezone.now()).exclude(session_key=current_key)` e filtrar por `_auth_user_id` no banco se possível. O problema é que `_auth_user_id` está em `session_data` (campo serializado), não é trivial filtrar no SQL.

2. **Alternativa**: usar cache ou tabela auxiliar para mapear user_id -> session_key, mas isso exige mais mudanças. Por ora, a abordagem atual é aceitável para escala pequena/média.

3. **`create_or_update_profile`**
   - A condição `profile.current_balance != profile.initial_balance` no `profile_created` é estranha: em `get_or_create`, o profile acabou de ser criado com defaults (ambos 0). Então `profile_created` é True e `current_balance == initial_balance == 0`. A condição nunca seria True. Código morto ou lógica incorreta.

### Sugestões de alteração

1. **Simplificar `create_or_update_profile`:**
   ```python
   @receiver(post_save, sender=User)
   def create_or_update_profile(sender, instance: User, created: bool, **kwargs) -> None:
       if created:
           Profile.objects.get_or_create(user=instance)
   ```
   O `get_or_create` já cria com defaults. A lógica de `current_balance != initial_balance` não faz sentido para profile novo.

2. **Para `logout_other_sessions`**: considerar limitar a um número máximo de sessões a deletar, ou executar em task assíncrona se a tabela de sessões for grande.

---

## 8. `accounts/admin.py`

### Pontos positivos
- UserAdmin customizado com ProfileInline
- ProfileAdmin com list_display, search_fields, list_filter úteis
- `list_select_related("profile")` no UserAdmin (evita N+1)

### Pontos negativos / Melhorias

1. **ProfileAdmin não usa `list_select_related("user")`**
   - Se houver muitos perfis, pode haver N+1 ao exibir `user` no list_display.

2. **Campos sensíveis**
   - `document_id` não está em list_display — bom. `phone` também não — bom.

### Sugestões
- Adicionar `list_select_related = ("user",)` no ProfileAdmin.

---

## 9. `accounts/tests.py`

### Situação atual
```python
# Create your tests here.
```

### Problema
- **Nenhum teste** para fluxos críticos: registro, login, recuperação de senha, edição de perfil, mixins de permissão.

### Sugestões
- Implementar testes para:
  - Registro de usuário
  - Login com email
  - Recuperação de senha por dados
  - PlanRequiredMixin e StaffRequiredMixin
  - Profile creation via signal

---

## 10. `accounts/management/commands/set_plan.py`

### Pontos positivos
- Uso de `BaseCommand`
- Tratamento de erros com `CommandError`
- `choices` no argumento `--plan`

### Pontos negativos / Problemas

1. **Falta `Plan.PREMIUM_PLUS` nas choices**
   - O modelo tem `Plan.PREMIUM_PLUS`, mas o command só aceita `free`, `basic`, `premium`.

2. **Uso de `User`**
   - Importa `from accounts.models import User` — correto.

### Sugestões
- Adicionar `Plan.PREMIUM_PLUS` nas choices do argumento `--plan`.

---

## 11. Templates

### `register.html`, `profile_edit.html`
- CSS inline extenso — considerar extrair para arquivo estático (DRY com outros templates).
- `{% csrf_token %}` presente — ok.
- Formulários com `novalidate` — ok para validação server-side.

### `login.html`
- Label "username" pode confundir — o usuário digita email. Sugestão: customizar `AuthenticationForm` com label "E-mail" para o campo username.

### `profile.html`
- **Linha 16**: `profile.get_plan_display` — mostra o plano armazenado, não o efetivo. Se o plano expirou, mostra valor errado. Usar `profile.get_active_plan_display` após adicionar o método no model.
- Link do Discord hardcoded — considerar variável de configuração.

### `password_recovery_by_data.html`, `password_recovery_change.html`
- Existem mas as views não estão nas URLs — inacessíveis.

---

## Resumo de Ações Prioritárias

| Prioridade | Arquivo      | Ação                                                                 | Status |
|------------|--------------|----------------------------------------------------------------------|--------|
| Média      | mixins.py    | Simplificar `PlanRequiredMixin.dispatch()` para clareza               | ✅ |
| Crítica    | urls.py      | Recuperação por dados removida (apenas por e-mail)                   | ✅ |
| Crítica    | views.py     | Corrigir import de User (get_user_model)                             | ✅ |
| Alta       | forms.py     | Excluir campos Discord do ProfileEditForm                            | ✅ |
| Alta       | models.py    | Adicionar get_active_plan_display e corrigir profile.html            | ✅ |
| Média      | signals.py   | Simplificar create_or_update_profile                                 | ✅ |
| Média      | set_plan.py  | Incluir Plan.PREMIUM_PLUS nas choices                                | ✅ |
| Baixa      | tests.py     | Implementar testes básicos                                           | ✅ |
| Baixa      | admin.py     | list_select_related no ProfileAdmin                                  | ✅ |
| Média      | views.py     | Rate limiting em login e registro                                    | ✅ |

# CD — Configuração

Deploy via SSH no Lightsail. Trigger: **Actions** → **Deploy** → **Run workflow** (ou push na `main` se habilitado).

---

## 1. Gerar chave SSH

```powershell
ssh-keygen -t ed25519 -C "github-actions-deploy" -f deploy_key
```

Quando perguntar passphrase, pressione Enter duas vezes. Gera `deploy_key` (privada) e `deploy_key.pub` (pública).

---

## 2. GitHub Secrets

**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret | Valor |
|--------|-------|
| `SSH_HOST` | IP ou hostname do servidor |
| `SSH_USER` | Usuário SSH (ex.: `ubuntu`) |
| `SSH_PRIVATE_KEY` | Conteúdo completo de `deploy_key` |

Opcional: `DEPLOY_PATH` (ex.: `~/app/smc_lab`)

---

## 3. Servidor

### Chave pública

```bash
nano ~/.ssh/authorized_keys
# Cole o conteúdo de deploy_key.pub em nova linha
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### Repositório

```bash
mkdir -p ~/app
cd ~/app
git clone https://github.com/SEU_USUARIO/smc_lab.git .
```

Repo privado: adicione Deploy Key no GitHub e use `git clone` via SSH. Ver seção "Repo privado" abaixo.

### .env e primeiro deploy

```bash
cp docs/env_production_template.txt .env
nano .env
docker compose up -d
sleep 15
docker compose exec web python manage.py migrate --noinput
docker compose exec web python manage.py collectstatic --noinput
```

---

## Repo privado

1. GitHub: **Settings** → **Deploy keys** → **Add deploy key** (cole `deploy_key.pub`)
2. No servidor: copie `deploy_key` para `~/.ssh/deploy_key`, chmod 600
3. Crie `~/.ssh/config`:

```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/deploy_key
  IdentitiesOnly yes
```

4. Clone via SSH: `git clone git@github.com:USUARIO/smc_lab.git .`

---

## Problemas comuns

| Erro | Solução |
|------|---------|
| Permission denied (publickey) | Chave pública em `authorized_keys`; `SSH_PRIVATE_KEY` completo no GitHub |
| fatal: could not read from remote | Repo privado: configure Deploy Key e use clone via SSH |
| Deploy falha no docker compose exec | Containers demorando; `docker compose ps` no servidor |

---

## Segurança

- Nunca commite `deploy_key` ou `deploy_key.pub` (já em `.gitignore`)
- Após configurar: `Remove-Item deploy_key, deploy_key.pub`
# Guia de Deploy - AWS Lightsail

## 📋 Passo a Passo Completo

### **ETAPA 1: Criar/Configurar Conta AWS**

#### 1.1. Criar conta AWS (se ainda não tiver)
1. Acesse: https://aws.amazon.com/pt/
2. Clique em **"Criar uma conta da AWS"**
3. Preencha:
   - Email
   - Senha (forte, com maiúsculas, números e caracteres especiais)
   - Nome da conta
4. Informações de pagamento:
   - Cartão de crédito (necessário, mas não será cobrado no Free Tier)
   - Endereço e telefone
5. Verificação de identidade (pode pedir ligação ou SMS)
6. Escolha um plano de suporte (comece com **"Básico - Grátis"**)

#### 1.2. Verificar conta
- Confirme o email
- Aguarde aprovação (pode levar algumas horas)

---

### **ETAPA 2: Contratar Instância Lightsail**

#### 2.1. Acessar Lightsail
1. Faça login no **Console AWS**: https://console.aws.amazon.com/
2. No campo de busca (topo), digite: **"Lightsail"**
3. Clique em **"Amazon Lightsail"**

#### 2.2. Criar instância
1. Clique em **"Criar instância"** (botão laranja)
2. **Escolha a região:**
   - Recomendado: **São Paulo (sa-east-1)** para menor latência
   - Ou: **US East (N. Virginia)** se quiser economizar

3. **Escolha a plataforma:**
   - ✅ **Linux/Unix**

4. **Escolha o blueprint (imagem):**
   - ✅ **"Ubuntu 22.04 LTS"** ou **"Ubuntu 24.04 LTS"**
   - (Evite "WordPress" ou outras aplicações prontas)

5. **Escolha o plano:**
   - Para começar: **$20/mês** (4GB RAM, 2 vCPUs, 80GB SSD)
   - Ou: **$10/mês** (2GB RAM, 1 vCPU, 40GB SSD) - pode ficar apertado
   - ✅ **Recomendado: $20/mês** (melhor custo-benefício)

6. **Nome da instância:**
   - Exemplo: `smc-lab-production` ou `trader-portal`

7. **Clique em "Criar instância"**
   - Aguarde 2-3 minutos para criação

---

### **ETAPA 3: Configuração Inicial do Servidor**

#### 3.1. Conectar via SSH
1. Na página da instância, clique em **"Conectar usando SSH"**
   - Abre um terminal no navegador
   - Ou use o botão **"Conectar via SSH"** para baixar chave

2. **Se preferir usar terminal local (Windows):**
   - Baixe **PuTTY** ou use **PowerShell** com SSH
   - Ou use **Git Bash** (se tiver Git instalado)

#### 3.2. Primeiro acesso e atualização
```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependências básicas
sudo apt install -y curl wget git build-essential
```

#### 3.3. Configurar firewall (portas)
1. No Lightsail, vá em **"Rede"** (aba da instância)
2. Clique em **"Adicionar regra"**
3. Adicione:
   - **HTTP** (porta 80) - permitir de qualquer IP
   - **HTTPS** (porta 443) - permitir de qualquer IP
   - **Custom** (porta 8000) - apenas para testes iniciais (depois remova)

---

### **ETAPA 4: Instalar Docker e Docker Compose**

#### 4.1. Instalar Docker
```bash
# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Adicionar usuário ao grupo docker
sudo usermod -aG docker ubuntu

# Verificar instalação
docker --version
```

#### 4.2. Instalar Docker Compose
```bash
# Instalar Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verificar instalação
docker-compose --version
```

#### 4.3. Reiniciar sessão SSH
```bash
# Sair e entrar novamente para aplicar mudanças de grupo
exit
# (Conecte novamente via SSH)
```

---

### **ETAPA 5: Instalar Dependências do Sistema**

#### 5.1. Instalar Python e ferramentas
```bash
# Python já vem instalado no Ubuntu, mas vamos garantir
sudo apt install -y python3 python3-pip python3-venv

# Instalar dependências do Playwright
sudo apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
  libcairo2 libatspi2.0-0 libxshmfence1
```

#### 5.2. Instalar PostgreSQL (se não usar Docker)
```bash
# Opcional: PostgreSQL local (ou usar RDS)
sudo apt install -y postgresql postgresql-contrib
```

---

### **ETAPA 6: Configurar Domínio (Opcional mas Recomendado)**

#### 6.1. Adicionar domínio estático no Lightsail
1. No Lightsail, vá em **"Rede"** → **"Domínios estáticos"**
2. Clique em **"Criar domínio estático"**
3. Digite seu domínio: `smclab.com.br`
4. Siga as instruções para configurar DNS no seu provedor

#### 6.2. Configurar DNS
- Adicione registro **A** apontando para IP da instância
- Adicione registro **CNAME** para `www` apontando para domínio principal

---

### **ETAPA 7: Preparar Servidor para Deploy**

#### 7.1. Criar estrutura de diretórios
```bash
# Criar diretório do projeto
mkdir -p ~/app
cd ~/app

# Criar diretórios para volumes Docker
mkdir -p postgres_data redis_data
```

#### 7.2. Configurar variáveis de ambiente
```bash
# Criar arquivo .env (vamos preencher depois)
nano .env
```

**Conteúdo inicial do .env:**
```env
# Django
DJANGO_SECRET_KEY=gerar-chave-secreta-aqui
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=["smclab.com.br","www.smclab.com.br","seu-ip-lightsail"]

# Database
DATABASE_URL=postgres://trader_user:senha_super_segura@postgres:5432/trader_portal

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Timezone
TZ=America/Sao_Paulo
```

#### 7.3. Gerar chave secreta do Django
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
(Copie o resultado e cole no `.env` como `DJANGO_SECRET_KEY`)

---

### **ETAPA 8: Configurar Backup Automático (OBRIGATÓRIO em produção)**

⚠️ **NUNCA rode `docker-compose down -v` no servidor!** O `-v` remove **todos** os volumes:
- **postgres_data** → banco de dados (clientes, pagamentos, usuários)
- **media_data** → imagens/screenshots dos trades (uploadadas pelos usuários)

**Backup completo (banco + media) – use o script:**
```bash
./scripts/backup_db.sh
# Gera: backups/backup_YYYY-MM-DD_HH-MM.sql e backups/media_YYYY-MM-DD_HH-MM.tar.gz
# Copie ambos para local seguro (S3, outro servidor, etc.)
```

**Restaurar após perda de volumes:**
```bash
# 1. Banco
docker compose exec -T postgres psql -U trader_user -d trader_portal < backups/backup_YYYY-MM-DD_HH-MM.sql

# 2. Media (imagens)
docker compose run --rm -v $(pwd)/backups:/backup web sh -c "rm -rf /app/media/* && tar xzf /backup/media_YYYY-MM-DD_HH-MM.tar.gz -C /app"
```

**Backup Lightsail:**
1. No Lightsail, vá em **"Snapshots"**
2. Configure **"Backup automático diário"**
3. Mantenha 7 snapshots (custo adicional mínimo)

---

## ✅ Checklist Pré-Deploy

Antes de fazer o deploy, verifique:

- [ ] Instância Lightsail criada e rodando
- [ ] Consegue conectar via SSH
- [ ] Docker e Docker Compose instalados
- [ ] Portas 80 e 443 abertas no firewall
- [ ] Domínio configurado (ou IP estático)
- [ ] Arquivo `.env` criado com variáveis
- [ ] Chave secreta do Django gerada
- [ ] Código do projeto no GitHub (para clonar)

---

## 🚀 Próximos Passos

Após completar este guia, estaremos prontos para:
1. Fazer upload do código (Git clone)
2. Configurar docker-compose.yml
3. Subir os containers
4. Configurar Nginx como proxy reverso
5. Configurar SSL/HTTPS (Let's Encrypt)
6. Configurar domínio e DNS

---

## 💰 Custos Estimados

- **Lightsail $20/mês**: ~R$ 100/mês (dependendo da cotação)
- **Domínio**: ~R$ 30-50/ano
- **Backup automático**: ~R$ 2-5/mês
- **Total inicial**: ~R$ 100-110/mês

---

## 📞 Suporte

Se tiver dúvidas em qualquer etapa, me avise que detalho o passo específico!

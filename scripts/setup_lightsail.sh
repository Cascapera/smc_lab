#!/bin/bash
# Script de configuração inicial para AWS Lightsail
# Execute com: bash setup_lightsail.sh

set -e  # Parar em caso de erro

echo "🚀 Configurando servidor Lightsail para SMC Lab..."
echo ""

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Atualizar sistema
echo -e "${YELLOW}[1/8]${NC} Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependências básicas
echo -e "${YELLOW}[2/8]${NC} Instalando dependências básicas..."
sudo apt install -y curl wget git build-essential python3 python3-pip python3-venv

# 3. Instalar Docker
echo -e "${YELLOW}[3/8]${NC} Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✓ Docker instalado${NC}"
else
    echo -e "${GREEN}✓ Docker já instalado${NC}"
fi

# 4. Instalar Docker Compose
echo -e "${YELLOW}[4/8]${NC} Instalando Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✓ Docker Compose instalado${NC}"
else
    echo -e "${GREEN}✓ Docker Compose já instalado${NC}"
fi

# 5. Instalar dependências do Playwright
echo -e "${YELLOW}[5/8]${NC} Instalando dependências do Playwright..."
sudo apt install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libxshmfence1

# 6. Criar estrutura de diretórios
echo -e "${YELLOW}[6/8]${NC} Criando estrutura de diretórios..."
mkdir -p ~/app/postgres_data
mkdir -p ~/app/redis_data
mkdir -p ~/app/logs
echo -e "${GREEN}✓ Diretórios criados${NC}"

# 7. Configurar timezone
echo -e "${YELLOW}[7/8]${NC} Configurando timezone para São Paulo..."
sudo timedatectl set-timezone America/Sao_Paulo
echo -e "${GREEN}✓ Timezone configurado${NC}"

# 8. Gerar chave secreta do Django
echo -e "${YELLOW}[8/8]${NC} Gerando chave secreta do Django..."
SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Configuração concluída!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "📝 PRÓXIMOS PASSOS:"
echo ""
echo "1. Copie esta chave secreta para seu arquivo .env:"
echo "   DJANGO_SECRET_KEY=$SECRET_KEY"
echo ""
echo "2. Configure o arquivo .env com todas as variáveis necessárias"
echo ""
echo "3. Faça clone do repositório:"
echo "   cd ~/app"
echo "   git clone <seu-repositorio> ."
echo ""
echo "4. Configure docker-compose.yml e faça o deploy"
echo ""
echo "⚠️  IMPORTANTE: Reinicie a sessão SSH para aplicar as mudanças do Docker:"
echo "   exit"
echo "   (e conecte novamente)"
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"

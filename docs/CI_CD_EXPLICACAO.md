# CI/CD — Explicação Passo a Passo

Este documento explica **como funciona** o pipeline de CI (Integração Contínua) do SMC Lab e **por que cada parte existe**.

---

## O que é CI/CD?

- **CI (Integração Contínua)**: rodar testes e verificações automaticamente a cada push/PR.
- **CD (Entrega Contínua)**: deploy automático após o CI passar (não implementado ainda).

O objetivo é **detectar problemas antes** de fazer merge ou deploy.

---

## Onde está o workflow?

O arquivo principal é:

```
.github/workflows/ci.yml
```

O GitHub Actions lê esse arquivo e executa o que está definido nele.

---

## Anatomia do arquivo `ci.yml`

### 1. Nome do workflow

```yaml
name: CI
```

- Define o nome que aparece na aba "Actions" do GitHub.
- Pode ser qualquer texto (ex: "Testes", "Pipeline Principal").

---

### 2. Gatilhos (`on`)

```yaml
on:
  push:
  pull_request:
```

**O que faz:** Define *quando* o workflow roda.

| Evento        | Significado                                                                 |
|---------------|-----------------------------------------------------------------------------|
| `push`        | Roda em **qualquer** push para qualquer branch                             |
| `pull_request`| Roda quando alguém abre ou atualiza um PR para **qualquer** branch       |

**Por que em todas as branches?** Assim você vê o resultado do CI em `feature/*`, `fix/*`, etc., antes de fazer merge.

---

### 3. Concorrência (`concurrency`)

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**O que faz:** Evita rodar vários workflows ao mesmo tempo para o mesmo commit.

- Se você fizer 3 pushes rápidos, o GitHub pode cancelar os 2 primeiros e rodar só o último.
- **Benefício:** economiza minutos de Actions e evita fila desnecessária.

---

### 4. Jobs e steps

```yaml
jobs:
  test:
    name: Testes
    runs-on: ubuntu-latest
    steps: ...
```

**Conceitos:**

- **Job:** um conjunto de passos que roda em um ambiente (ex: máquina Ubuntu).
- **Step:** uma ação individual (checkout, instalar Python, rodar comando).
- **runs-on: ubuntu-latest:** usa uma máquina virtual Ubuntu (Linux) para rodar tudo.

---

## Passo a passo dos `steps`

### Step 1: Checkout

```yaml
- name: Checkout do repositório
  uses: actions/checkout@v4
```

**O que faz:** Baixa o código do repositório para a máquina do GitHub.

- Sem isso, a máquina não teria seu código.
- `actions/checkout` é uma action oficial do GitHub.
- `@v4` fixa a versão (evita quebras se a action mudar).

---

### Step 2: Configurar Python

```yaml
- name: Configurar Python 3.13
  uses: actions/setup-python@v5
  with:
    python-version: "3.13"
    cache: "pip"
```

**O que faz:** Instala o Python 3.13 e configura o ambiente.

- `python-version`: deve bater com o que você usa localmente (veja `requirements.txt`).
- `cache: "pip"`: guarda o cache do `pip` entre execuções → instalação mais rápida.

---

### Step 3: Instalar dependências

```yaml
- name: Instalar dependências
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
```

**O que faz:** Instala as bibliotecas do projeto.

- `python -m pip`: garante que usa o pip do Python correto.
- `pip install -r requirements.txt`: instala exatamente o que está no projeto.

---

### Step 4: Verificar configuração

```yaml
- name: Verificar configuração (manage.py check)
  env:
    DJANGO_SETTINGS_MODULE: trader_portal.settings.ci
  run: python manage.py check
```

**O que faz:** Roda `manage.py check`, que valida:

- URLs, models, templates, etc.
- Se algo estiver quebrado na configuração, falha aqui.

**Por que `trader_portal.settings.ci`?**  
Existe um arquivo `trader_portal/settings/ci.py` que usa SQLite em memória e desabilita Redis/Celery. Assim o CI não depende de PostgreSQL ou Redis.

---

### Step 5: Verificar migrações

```yaml
- name: Verificar migrações (makemigrations --check)
  env:
    DJANGO_SETTINGS_MODULE: trader_portal.settings.ci
  run: python manage.py makemigrations --check
```

**O que faz:** Garante que não há mudanças em models sem migração.

- Se você alterou um model e esqueceu de rodar `makemigrations`, o comando falha.
- Evita que alguém faça merge sem criar as migrações.

---

### Step 6: Rodar testes

```yaml
- name: Executar testes
  env:
    DJANGO_SETTINGS_MODULE: trader_portal.settings.ci
  run: python manage.py test --verbosity=2
```

**O que faz:** Executa todos os testes do Django.

- `--verbosity=2`: mostra mais detalhes (útil para debug quando algo falha).
- Usa `settings.ci` (SQLite em memória) para ser rápido e sem dependências externas.

---

## O arquivo `trader_portal/settings/ci.py`

Esse arquivo existe só para o CI. Ele:

1. **Herda** de `base.py` (todas as configs padrão).
2. **Sobrescreve** o que precisa para rodar sem serviços externos:

| Configuração              | Valor              | Motivo                                      |
|---------------------------|--------------------|---------------------------------------------|
| `DATABASES`               | SQLite `:memory:`  | Não precisa de PostgreSQL                   |
| `CELERY_TASK_ALWAYS_EAGER`| `True`             | Tasks rodam síncronas, sem Redis            |
| `CACHES`                  | LocMemCache        | Cache em memória, sem Redis                 |

Assim o CI roda só com Python e `pip`, sem Docker, PostgreSQL ou Redis.

---

## Como ver o resultado

1. Acesse o repositório no GitHub.
2. Clique na aba **Actions**.
3. Cada execução aparece como um workflow.
4. Clique em uma execução para ver os logs de cada step.

**Cores:**

- Verde: passou.
- Vermelho: falhou (clique para ver qual step quebrou).

---

## Job de Lint (Ruff)

O CI inclui um job de lint que roda em paralelo com os testes:

```yaml
lint:
  name: Lint
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.13"
        cache: "pip"
    - run: pip install ruff
    - run: ruff check .
    - run: ruff format --check .
```

**O que faz:**
- `ruff check`: verifica erros de estilo (pycodestyle, pyflakes, isort).
- `ruff format --check`: verifica se o código está formatado (não altera, só checa).

**Rodar localmente antes do push:**
```bash
pip install -r requirements-dev.txt   # ou: pip install ruff
ruff check .
ruff format .
ruff check . --fix   # corrige o que for possível
```

**Configuração:** `pyproject.toml` — regras do Ruff (line-length, excludes, isort).

---

## Próximos passos (opcional)

Depois que o CI estiver estável, você pode adicionar:

1. **Cobertura de testes:** exigir X% de cobertura.
2. **CD (Deploy):** após o CI passar, fazer deploy automático (ex: Lightsail, Railway).

---

## Resumo visual

```
Push/PR → Checkout → Python 3.13 → pip install → manage.py check
                                              → makemigrations --check
                                              → manage.py test
                                                    ↓
                                            Verde = OK, Vermelho = Falhou
```

---

## Referência rápida: sintaxe YAML

| Símbolo | Significado |
|---------|-------------|
| `key: value` | Par chave-valor |
| `- item` | Item de lista |
| `\|` | Bloco de texto multilinha (para `run`) |
| `${{ expr }}` | Expressão do GitHub Actions |

---

## Blocos de código explicados (linha a linha)

### Bloco 1: Cabeçalho e nome

```yaml
name: CI
```

- **`name`**: Nome do workflow (aparece na aba Actions).
- **`CI`**: Pode ser qualquer texto descritivo.

---

### Bloco 2: Gatilhos

```yaml
on:
  push:
  pull_request:
```

- **`on`**: Define os eventos que disparam o workflow.
- **`push`**: Sem `branches`, roda em qualquer push.
- **`pull_request`**: Roda em qualquer PR (abertura ou novo commit).

**Se quiser limitar a branches:**
```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
```

---

### Bloco 3: Concorrência

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

- **`group`**: Agrupa execuções. `github.workflow` = nome do workflow, `github.ref` = branch (ex: `refs/heads/feature/x`).
- **`cancel-in-progress: true`**: Cancela execuções antigas quando uma nova do mesmo grupo começa.

---

### Bloco 4: Job e ambiente

```yaml
jobs:
  test:
    name: Testes
    runs-on: ubuntu-latest
```

- **`jobs`**: Lista de jobs (tarefas) do workflow.
- **`test`**: ID do job (usado em dependências entre jobs).
- **`name`**: Nome exibido na interface.
- **`runs-on`**: Sistema operacional da máquina virtual (`ubuntu-latest` = Ubuntu mais recente).

**Outras opções de `runs-on`:** `windows-latest`, `macos-latest`, `macos-14`.

---

### Bloco 5: Steps — Checkout

```yaml
    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4
```

- **`steps`**: Lista de passos executados em ordem.
- **`-`**: Início de cada step.
- **`name`**: Título do step (aparece no log).
- **`uses`**: Usa uma **action** (código reutilizável). `actions/checkout` é oficial do GitHub.
- **`@v4`**: Versão da action (evita quebras em atualizações).

---

### Bloco 6: Steps — Setup Python

```yaml
      - name: Configurar Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: "pip"
```

- **`with`**: Parâmetros passados para a action.
- **`python-version`**: Versão do Python (entre aspas quando tem ponto).
- **`cache: "pip"`**: Ativa cache do pip (acelera `pip install` em execuções seguintes).

---

### Bloco 7: Steps — Comandos shell

```yaml
      - name: Instalar dependências
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
```

- **`run`**: Comandos executados no shell (bash no Ubuntu).
- **`|`**: Permite múltiplas linhas. Cada linha é um comando.
- **`python -m pip`**: Garante uso do pip do Python correto.

---

### Bloco 8: Steps — Variáveis de ambiente

```yaml
      - name: Verificar configuração (manage.py check)
        env:
          DJANGO_SETTINGS_MODULE: trader_portal.settings.ci
        run: python manage.py check
```

- **`env`**: Variáveis de ambiente disponíveis só neste step.
- **`DJANGO_SETTINGS_MODULE`**: Django usa esse módulo de settings.
- **`trader_portal.settings.ci`**: Settings específicos para CI (SQLite, sem Redis).

---

### Bloco 9: Ordem de execução

Os steps rodam **em sequência**. Se um falhar, os seguintes não executam e o job falha.

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
    branches: [main, master, develop]
  pull_request:
    branches: [main, master, develop]
```

**O que faz:** Define *quando* o workflow roda.

| Evento        | Significado                                                                 |
|---------------|-----------------------------------------------------------------------------|
| `push`        | Roda quando alguém faz `git push` para `main`, `master` ou `develop`        |
| `pull_request`| Roda quando alguém abre ou atualiza um PR para essas branches             |

**Por que essas branches?** São as branches principais. Você pode adicionar outras (ex: `feature/*`) se quiser.

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

## Próximos passos (opcional)

Depois que o CI estiver estável, você pode adicionar:

1. **Lint (Ruff/Black):** rodar formatação e lint no CI.
2. **Cobertura de testes:** exigir X% de cobertura.
3. **CD (Deploy):** após o CI passar, fazer deploy automático (ex: Lightsail, Railway).

---

## Resumo visual

```
Push/PR → Checkout → Python 3.13 → pip install → manage.py check
                                              → makemigrations --check
                                              → manage.py test
                                                    ↓
                                            Verde = OK, Vermelho = Falhou
```

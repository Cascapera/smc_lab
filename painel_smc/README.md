# Painel Macro – Monitoramento de Sentimento de Mercado

Aplicação Python que coleta, consolida e apresenta a variação percentual de ativos globais a partir do Investing.com, transformando os dados em métricas acionáveis em tempo quase real. O objetivo é fornecer um panorama macro com foco em decisão rápida — perfeito para demonstrar habilidades de web scraping robusto, orquestração, persistência de dados e data viz.

---

## ✨ Destaques Técnicos

- **Scraping resiliente**: múltiplos user-agents, retentativas, fallback via proxy (`r.jina.ai`), mitigação de 403/503 e tratamento de timeouts.
- **Agendamento sob medida**: coleta a cada 5 minutos com lead de 2 minutos, garantindo que o dado esteja pronto no horário-alvo (ex.: 08:58 → 09:00).
- **Pipeline de dados completo**:
  - `historico_variacoes.csv`: tabela wide com % por ativo/medição.
  - `historico_variacoes_metadata.csv`: status detalhado, blocos e variação decimal.
  - `historico_scores.csv`: pontuação -1/0/1 por ativo + soma e variação total acumulada, respeitando ativos inversos via `ValorBase` negativo.
- **Visualizações dinâmicas**:
  - Ponteiro semicircular (tipo velocímetro) para o sentimento agregado.
  - Gráfico de tendência das últimas 60 medições com faixas de 2% e linha zero.
  - Painel ao vivo (`Painel Macro`) que se atualiza automaticamente.
- **Arquitetura modular**: `core/` segregado em `assets`, `network`, `data_sources`, `services`, `visuals`, etc., com `main.py` enxuto.
- **Documentação de onboarding**: `docs/overview.md` descreve o fluxo end-to-end e principais pontos de extensão.

---

## 🧱 Arquitetura em alto nível

```
planilha_referencia.xlsx  -->  core.assets.load_assets()
                                 │
Scheduler (5/5 min)  -->  core.services.scheduler.run_forever()
                                 │
Collector                 core.services.collector.execute_cycle()
└── network.fetch_html()  ├─ data_sources.(investing|tradingview)
└── utils.parse_%         └─ writers.write_(variations|metadata|scores|debug)

historico_scores.csv  -->  core.visuals.(gauge|trend)
                               ├─ scripts/render_gauge.py / render_trend.py
                               └─ scripts/dashboard_live.py  (Painel Macro)
```

Mais detalhes em [`docs/overview.md`](docs/overview.md).

---

## 🚀 Como rodar

1. **Clonar e instalar dependências**
   ```bash
   git clone <repo>
   cd projeto_macro
   python -m venv .venv
   .venv\Scripts\activate  # ou source .venv/bin/activate
   pip install -r requirements.txt
   python -m playwright install chromium  # necessário para TradingView
   ```

2. **Preparar a planilha de referência**
   - Atualize `data/planilha_referencia.xlsx` com colunas `Ativo`, `ValorBase`, `URL`.
   - Use `ValorBase` negativo para ativos que precisam de lógica invertida (ex.: dólar).

3. **Iniciar o monitoramento + painel ao vivo**
   ```bash
   python main.py
   ```
   - O agendador roda em background.
   - O painel “Painel Macro” abre automaticamente e exibe:
     - Gauge semicircular (sentimento agregado).
     - Linha de tendência (últimas 40 medições).

4. **Executar visualizações manualmente (opcional)**
   ```bash
   python scripts/render_gauge.py      # gera PNG em data/visualizacoes/
   python scripts/render_trend.py
   python scripts/dashboard_live.py    # painel isolado
   python scripts/recompute_scores.py  # reprocessa histórico textual -> scores
   ```

---

## 📁 Estrutura principal

```
core/
  assets.py          Carrega planilha e resolve fonte por domínio
  config.py          Caminhos, headers HTTP, política de retries e agenda
  data_sources/      Parsers Investing e TradingView
  models.py          Dataclasses Asset / VariationResult
  network.py         Requisições resilientes com fallback
  services/
    collector.py     Orquestra ciclo (fetch → parse → persistir)
    scheduler.py     Loop de agendamento na cadência 5 em 5 min
  visuals/
    gauge.py         Velocímetro de sentimento (+ utilidades)
    trend.py         Gráfico de tendência (máx. 60 pontos, faixas 2%)
    __init__.py      Facade para visualizações
  utils.py           Conversões de % e limpeza de HTML

data/
  planilha_referencia.xlsx   Fonte dos ativos
  historico_variacoes.csv    Percentuais por coluna/medição
  historico_variacoes_metadata.csv
  historico_scores.csv       Score -1/0/1 + soma + variação acumulada
  debug_fontes_investing.txt Trechos relevantes do HTML
  visualizacoes/             PNGs gerados

docs/overview.md             Resumo do fluxo e responsabilidades
scripts/                     Ferramentas auxiliares (render, painel, recompute)
main.py                      Entry-point: scheduler (thread) + painel ao vivo
```

---

## 🧪 Experimentos e extensões sugeridas

- Persistir dados em um data warehouse (DuckDB, BigQuery) e montar dashboards interativos (Streamlit, Dash).
- Adicionar autenticação por proxy próprio para lidar com CAPTCHAs agressivos.
- Módulo de alertas (Slack/Telegram) quando a soma atingir thresholds.
- Testes automatizados para parsers e writers usando HTML fixtures.
- **TradingView via Playwright**: já integrado para coleta; oportunidades:
  - Reusar browser/contexto e aplicar delays aleatórios entre ativos para reduzir risco de bloqueio.
  - Diminuir cadência (ex.: <~15 requisições/5min) ou adicionar cache curto.
  - Detectar falhas (`playwright_error` / spans vazios) e aplicar backoff.

---

## 📬 Contato & motivação

Este projeto nasceu para mostrar proficiência real em Python voltado a dados: scraping complexo, orquestração temporizada, processamento resiliente, persistência limpa e apresentação visual instantânea. Se você avalia talentos ou recruta para funções data-driven, este repositório é pensado para demonstrar as habilidades necessárias para construir soluções end-to-end com foco em confiabilidade e clareza arquitetural.

Sinta-se à vontade para abrir issues, sugestões ou entrar em contato!***


# Visão geral da aplicação de monitoramento de sentimento

Este documento resume o fluxo de dados, a arquitetura e os pontos de extensão do projeto para facilitar o onboarding de novas pessoas desenvolvedoras.

## Fluxo principal

1. **Entrada de referência**  
   `data/planilha_referencia.xlsx` define cada ativo monitorado com colunas:
   - `Ativo`: nome exibido.
   - `ValorBase`: limiar para pontuação (positivo = lógica direta; negativo = lógica invertida).
   - `URL`: página de referência (Investing.com).
2. **Agendamento**  
   `core.services.scheduler.run_forever()` calcula a próxima janela-alvo a cada cinco minutos, iniciando dois minutos antes para dar tempo de coleta/processamento.
3. **Coleta**  
   `core.services.collector.execute_cycle()` executa o ciclo:
   - Carrega ativos (`core.assets.load_assets()`).
   - Baixa HTML com retries e fallback (`core.network.fetch_html()`).
   - Usa parser da fonte (`core.data_sources.investing` ou `core.data_sources.tradingview`) para extrair a variação.
   - Normaliza texto/decimal (`core.utils`).
   - Monta `VariationResult` com status e trecho limpo de HTML.
4. **Persistência**  
   `core.writers` atualiza/gera:
   - `data/historico_variacoes.csv`: cada coluna = uma medição (% textual).
   - `data/historico_variacoes_metadata.csv`: linha por ativo com status, valor decimal, motivos de bloqueio.
   - `data/historico_scores.csv`: pontuações (-1/0/1), linha `Soma` e linha `Soma Acumulada`.
   - `data/debug_fontes_investing.txt`: trecho de HTML limpo para auditoria.
5. **Visualizações**  
   - Gauge semicircular (`core.visuals.gauge.render_market_sentiment_gauge`) mostra estado agregado do último score.
   - Gráfico de tendência (`core.visuals.trend.render_sentiment_trend`) exibe a evolução (até 40 medições recentes).
   - Scripts utilitários:
     - `scripts/render_gauge.py` → gera PNG em `data/visualizacoes/`.
     - `scripts/render_trend.py` → idem para a tendência.
     - `scripts/dashboard_live.py` → painel ao vivo (atualiza a cada 60s) combinando gauge e tendência.

## Arquitetura em módulos

| Módulo | Responsabilidade |
| --- | --- |
| `core/config.py` | Caminhos, headers HTTP, política de retries, parâmetros do agendador. |
| `core/assets.py` | Carrega planilha de referência, identifica parser pelo domínio. |
| `core/models.py` | Dataclasses `Asset` e `VariationResult`. |
| `core/network.py` | Requisições HTTP resilientes com fallback `r.jina.ai`. |
| `core/data_sources/` | Parsers específicos (Investing, TradingView). |
| `core/utils.py` | Conversões e limpeza de HTML. |
| `core/services/collector.py` | Execução end-to-end de um ciclo. |
| `core/services/scheduler.py` | Cálculo de horários e laço de execução. |
| `core/writers.py` | Persistência dos CSVs e logs de depuração. |
| `core/visuals/` | Renderização das duas visualizações e utilitários de leitura. |

## Sequência de execução típica

1. `python main.py` → inicializa scheduler (loop infinito).
2. Scheduler chama `execute_cycle()` na janela correta.
3. Coletor escreve/atualiza os arquivos em `data/`.
4. Scripts de visualização consomem `historico_scores.csv`:
   - Rodando isolados (`render_*.py`) criam imagens estáticas.
   - Painel (`dashboard_live.py`) observa o arquivo e redesenha automaticamente.

## Ajustes frequentes

- **Adicionar/editar ativos**: atualizar `data/planilha_referencia.xlsx`.
- **Inverter lógica de pontuação**: definir `ValorBase` negativo no Excel.
- **Explorar histórico antigo**: executar `python scripts/recompute_scores.py` após ajustes de lógica para recalcular `historico_scores.csv`.
- **Monitorar falhas**: conferir `data/debug_fontes_investing.txt` e a coluna `status` em `historico_variacoes_metadata.csv`.
- **Alterar intervalo ou lead time**: editar `TARGET_INTERVAL_MINUTES` / `LEAD_TIME_MINUTES` em `core/config.py`.
- **Ajustar visualizações**: modificar `core/visuals/gauge.py` e `core/visuals/trend.py` (ambas aceitam `ax` externo para uso em dashboards).

## Ambiente e dependências

- Dependências listadas em `requirements.txt` (instalar com `pip install -r requirements.txt`).
- `pandas`, `requests`, `beautifulsoup4` para coleta/processamento.
- `matplotlib` para visualizações estáticas e painel ao vivo.
- Estrutura de dados e arquivos assume diretório `data/` existente (criado automaticamente pelos writers).

## Scripts adicionais

- `scripts/render_gauge.py`: gera gauge mais recente em PNG.
- `scripts/render_trend.py`: gera gráfico de tendência mais recente em PNG.
- `scripts/dashboard_live.py`: painel interativo (matplotlib) que atualiza gauge + tendência.
- `scripts/recompute_scores.py`: reprocessa histórico textual para aplicar nova lógica de pontuação.

Use este documento como ponto de partida para localizar rapidamente onde cada regra está implementada e quais arquivos são afetados ao fazer alterações.


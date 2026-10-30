# CLAUDE.md — Dashboard Giaco · A Sala do Conselho (SDC · FORM7)

> Lido automaticamente pelo Claude Code ao abrir o repositório. Mantenha atualizado.
> Repositório: `scale-ag/dash-giaco-sdc-form7` · Pages: `https://scale-ag.github.io/dash-giaco-sdc-form7/`

## Configuração do cliente

- **Cliente:** Giaco · **Funil:** A Sala do Conselho (sigla **SDC**) · formulário **FORM7**.
- **Modelo:** mesmo layout/abas de `metrics-odr/dash-thata-opn` e `metrics-odr/dash-davi-fse`
  (**Visão Geral · Meta Ads · Insights de IA** — ids internos `geral`/`meta`/`rel`),
  adaptado a **formulário nativo do Meta (Lead Ad)**.
- **Leads:** planilha `1a-bUrbN8fuJWPBSEIc24Kp-h--xHeQLTFOLljS50NkQ`, gid `0` (export do Lead Ad).
- **Meta Ads:** planilha `1Uep5K2-fJqBxNX-j8rDa-7V-Q2-iCRlz9S6KzR37VsQ`, aba `QUERIES FORM7`, gid `1320534268`.
- **Sem qualificação:** decisão do cliente — **não** há MQL/Lead A nem critério de
  qualificação (as respostas do formulário só aparecem como distribuição: perfil
  profissional e área de atuação). Também não há agendamentos, vendas, faturamento,
  CAC ou ROAS. O funil termina no **Lead**. Não reintroduzir sem pedido + fonte de dados.
- `TAX_FACTOR = 1.13806` (toggle "Imposto Meta" ligado por padrão).
- O sandbox do agente costuma não alcançar `docs.google.com`; o runner do Actions alcança.

> Existe também a dash antiga `scale-ag/giaco---FORM7` (mesmas planilhas, template
> anterior). Esta aqui é independente — mudanças numa não afetam a outra.

---

## Funil (formulário nativo, sem landing page)

`Gasto → Impressões → Alcance → Cliques → Leads`, com
**CPM · Frequência (Impressões ÷ Alcance) · CTR · CPC · ConvForm (Leads ÷ Cliques) · CPL**.

- Não existe `Landing Page Views` → sem Page Views/CR/ConvLP/CPV.
- **Alcance** é a soma das linhas diárias por anúncio da aba de Queries (o Meta não
  deduplica entre dias/anúncios), então a Frequência é uma média aproximada.
- **CPL só existe com gasto > 0** (`derive()` em `app.js`, `derived()` em
  `relatorio_lib.py`): lead de um anúncio que não aparece na aba de Queries aparece
  com CPL "-" (nunca "R$ 0,00").
- A coluna `Leads` da aba de Queries (contagem do Meta) **não** é usada — a fonte de
  verdade é a planilha de leads (cadastros válidos).

## Regra de LEAD VÁLIDO (`build.py` → `lead_discard_reason`/`is_valid_lead`)

1. `is_organic` == `false`;
2. `campaign_name` começa com `MAIN_PRODUCT_PREFIX` (`SDC`);
3. `full_name`, `email` e `phone_number` preenchidos;
4. não é teste: linha com `<test lead`, e-mail `@meta.com`/`teste.com`/`test.com`/`example.com`,
   ou nome/e-mail cuja 1ª palavra é `teste`/`test` (ex.: "Teste ingenium").

Consequência: 100% dos leads da dash são de mídia paga — Visão Geral e Meta Ads olham
o mesmo universo (a aba Meta Ads acrescenta o filtro cruzado por Campanha/Conjunto/Anúncio).
O build loga descartes por motivo e quantos leads não têm anúncio na aba de Queries
(`leads_sem_meta`, também usado no KPI "% Eficácia Rastr.").

Casamento leads × Meta Ads **exato**: `campaign_name`/`adset_name`/`ad_name` ==
`Campaign Name`/`Ad Set Name`/`Ad Name`. `trk=1` no lead quando a tripla existe na aba de Queries.

### Fuso horário
`created_time` vem em ISO com offset; `parse_lead_date()` converte para
`ACCOUNT_TZ` (America/Sao_Paulo) antes de pegar o dia. O `Day` do Meta entra como está.

## Arquitetura / arquivos

```
build/build.py            # lê os 2 CSVs (read-only), aplica a regra de lead válido, emite REGISTROS BRUTOS (leads[]/meta[]); render() costura os arquivos abaixo
build/template.html       # esqueleto HTML. Placeholders __STYLES__, __APP_JS__, __DATA_JSON__, __BUILD_ID__, __GENERATED_BRT__
build/identidade-visual.css  # TODAS as cores (tema claro/escuro)
build/estilos.css         # layout/componentes (sidebar, topbar, period-picker, funil, tabelas, gráficos, aba Insights)
build/app.js              # lógica + renderização (KPIs, funil, tabelas, filtro cruzado, period-picker, heatmap, Insights)
build/relatorios.json     # Insights de Tráfego por período — VERSIONADO; hoje {} (Routine não criada)
build/relatorios_dados.json      # números brutos por período (insumo da Routine) — não lido pelo site. Hoje {}.
build/relatorio_lib.py           # datas/agregação compartilhadas (usada por coletar_dados_relatorio.py)
build/coletar_dados_relatorio.py # gera relatorios_dados.json (só números) — roda no briefing.yml (agendamento DESLIGADO)
build/GUIA-RELATORIOS.md            # formato dos Insights (contexto do funil SDC/FORM7)
build/GUIA-INTERPRETACAO-METRICAS.md # regras de diagnóstico por métrica
.github/workflows/deploy.yml    # roda build.py e publica no Pages (workflow_dispatch + schedule + push)
.github/workflows/briefing.yml  # roda coletar_dados_relatorio.py (só workflow_dispatch por enquanto)
dist/index.html           # saída gerada (gitignored; o Actions reconstrói)
GUIA-REPLICACAO.md        # como replicar este modelo
SETUP-CRON.md             # valores exatos do cron-job.org
```

O `build.py` **não agrega**: exporta as linhas cruas e TODA a lógica (filtros de
data, filtro cruzado, KPIs, tabelas, gráficos, heatmap, imposto) roda no navegador.

## Especificação funcional

1. **Visão Geral** (`geral`) — funil vertical (Gasto → Impressões → Alcance → Cliques → Leads);
   evolução diária (Leads barras · Gasto · CPL) + tabela diária com heatmap
   (`DAILY_COLS`: Data · Dia · Gasto · CPM · Freq. · CTR · CPC · ConvForm · Leads · CPL;
   heatmap Gasto=vermelho · Leads=azul); 8 KPIs secundários (Leads/dia, Melhor CPL
   (anúncio), Top anúncio, Concentração, Anúncios ativos, % Eficácia Rastr., Melhor dia
   (CPL), Proporção IG:FB); distribuição por conjunto · perfil profissional · plataforma ·
   área de atuação.
2. **Meta Ads** (`meta`) — mesmo funil; combinação diária; indicadores por dia
   (CPM/CTR · ConvForm/CPC · CPL/Frequência); leads por anúncio; donut de conversão do
   formulário; compilado de anúncios (menor CPL, só com gasto e lead); 3 tabelas
   hierárquicas Campanha → Conjunto → Anúncio (dim + Gasto sticky) com gráfico de CPL por
   dia e legenda clicável; lista de leads do período (nome abreviado, e-mail/telefone mascarados).
3. **Insights de IA** (`rel`) — espelha a Visão Geral + painel de Metas (Meta CPL,
   volume mín. amostral em leads, N dias p/ corte; `localStorage` com chave por repo) +
   **Top Anúncios** (todos com gasto; amostra relevante primeiro, depois mais leads e
   menor CPL) com status **Escalar** (CPL ≤ meta) · **Manter** (até +30% ou meta não
   definida) · **Cortar** (acima) · **Observar** (gasto < `SAMPLE_MIN_SPEND` ou leads <
   volume mínimo) + Insights de Tráfego (lidos de `build/relatorios.json`).

**Regras obrigatórias das tabelas:** cabeçalho sticky; ordenação tri‑state; colunas
redimensionáveis (persist localStorage); linha "Total Geral" fixa; dimensão nunca
truncada; seleção com toggle + Ctrl multi; filtro cruzado bidirecional; tabela diária
com último dia no topo; heatmap de cor fixa por métrica.

`localStorage`: `dm_metas:<repo>` e `dm_colw:<repo>` (chave com o nome do repo, porque
`scale-ag.github.io` é a mesma origem para todas as dashs da conta); `dm_theme` é global.

## Briefing automático (Insights de IA) — INATIVO

`build/relatorios.json`/`build/relatorios_dados.json` estão `{}` e o `schedule` do
`briefing.yml` está comentado. Para ativar: (1) descomentar o `schedule`, (2) criar a
Routine do Claude que lê `build/relatorios_dados.json` + os 2 guias e escreve
`build/relatorios.json` na `main`.

## Rodar/testar local

```bash
python build/build.py --leads-file leads.csv --meta-file queries.csv --out dist/index.html
```

## Publicação — problemas conhecidos
1. **cron-job.org só funciona na `main`** (`workflow_dispatch` só existe na branch padrão).
2. **Pages** está em modo "GitHub Actions" (ligado via API na criação do repo).
3. **Token exposto:** se um token foi colado no chat, **revogar e gerar um novo**.

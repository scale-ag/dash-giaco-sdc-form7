# Dashboard de Captação de Leads · Giaco · A Sala do Conselho (SDC · FORM7)

Dashboard **100% na nuvem** do funil **A Sala do Conselho · FORM7**, cruzando a
mídia paga (Meta Ads) com os leads capturados pelo **formulário nativo (Lead Ad)**
do Meta. Mesmo modelo/abas das dashs `dash-thata-opn` e `dash-davi-fse`
(Visão Geral · Meta Ads · Insights de IA), adaptado ao formulário nativo.
Build estático (HTML/CSS/JS puro + Chart.js via CDN) publicado no **GitHub Pages**
e reconstruído a cada ~30 min pelo GitHub Actions (disparado pelo cron-job.org).

**URL pública:** https://scale-ag.github.io/dash-giaco-sdc-form7/

Somente leitura das planilhas. O build **nunca** escreve de volta.

---

## O que a dash mostra

Funil: **Gasto → Impressões → Alcance → Cliques → Leads**, com CPM, Frequência,
CTR, CPC, ConvForm (Leads/Cliques) e CPL. Três páginas:

1. **Visão Geral** — funil + evolução diária (Leads × Gasto × CPL) + tabela
   diária com heatmap, 8 KPIs secundários e 4 distribuições (conjunto, perfil
   profissional, plataforma, área de atuação).
2. **Meta Ads** — mesmo funil + combinação diária, indicadores por dia
   (CPM/CTR · ConvForm/CPC · CPL/Frequência), leads por anúncio, donut de
   conversão do formulário, compilado de anúncios por CPL, as 3 tabelas
   hierárquicas (Campanha → Conjunto → Anúncio) com gráfico de CPL por dia e
   filtro cruzado bidirecional, e a lista de leads do período (mascarada).
3. **Insights de IA** — espelha a Visão Geral + painel editável de metas (Meta
   CPL, volume mínimo, N dias p/ corte) + **Top Anúncios** com status
   Escalar/Manter/Observar/Cortar + bloco "Insights de Tráfego" (vazio até a
   Routine do Claude ser criada — ver `CLAUDE.md`).

### Formulário nativo: o que muda em relação às dashs de LP
Não existe landing page, logo **não há** Page Views, CR, ConvLP nem CPV. No lugar
entram **Alcance** (Reach) e **Frequência** (Impressões ÷ Alcance), e a conversão
é **ConvForm = Leads ÷ Cliques**. Esta dash vai até o **Lead**: sem MQL/qualificação,
agendamentos, vendas, faturamento, CAC ou ROAS (decisão do cliente).

### Regra de LEAD VÁLIDO (`build/build.py` → `is_valid_lead`)
1. `is_organic` == `false` (mídia paga);
2. `campaign_name` começa com `SDC`;
3. `full_name`, `email` e `phone_number` preenchidos;
4. não é teste (dummy data do Meta, e-mail `@meta.com`/`test.com`…, nome começando com "Teste").

O build imprime no log quantos leads foram descartados e por quê.

### Imposto da mídia paga
`TAX_FACTOR = 1.13806` (13,806%) aplicado **somente** ao gasto do Meta Ads. O
toggle "Imposto Meta" **já vem ligado**; desligá-lo mostra o gasto bruto.

## Fontes de dados (Google Sheets, somente leitura)

| Planilha | ID | Aba (gid) | Colunas usadas |
|---|---|---|---|
| Leads (Lead Ad) — `SDC FORM 7 NOVOOO` | `1a-bUrbN8fuJWPBSEIc24Kp-h--xHeQLTFOLljS50NkQ` | `0` | `created_time` · `campaign_name` · `adset_name` · `ad_name` · `platform` · `is_organic` · `full_name` · `email` · `phone_number` · perguntas "papel como profissional" e "área de especialidade/atuação" |
| Meta Ads — `Giaco \| SDC \| Planilha Central`, aba `QUERIES FORM7` | `1Uep5K2-fJqBxNX-j8rDa-7V-Q2-iCRlz9S6KzR37VsQ` | `1320534268` | `Day` · `Campaign Name` · `Ad Set Name` · `Ad Name` · `Amount Spent` · `Impressions` · `Link Clicks` · `Reach` |

Casamento **exato**: `campaign_name` = `Campaign Name` · `adset_name` = `Ad Set Name` · `ad_name` = `Ad Name`.

URL de export CSV: `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>`

## Rodar/testar local

```bash
python build/build.py --leads-file leads.csv --meta-file queries.csv --out dist/index.html
```

Sem `--leads-file`/`--meta-file` o script busca os CSVs públicos direto do Google Sheets.

## Automação

- `.github/workflows/deploy.yml` — roda `build/build.py` e publica no Pages.
  Dispara por `workflow_dispatch` (cron-job.org a cada 30 min), `schedule` de
  backup e `push` na `main`.
- `.github/workflows/briefing.yml` — coleta os números dos Insights. Agendamento
  **desligado** até existir a Routine do Claude que escreve os textos.

Valores exatos para o cron-job.org: **`SETUP-CRON.md`**.

# AGENTS.md — Dash Captação de Leads · Giaco (A Sala do Conselho · FORM7)

> Contexto completo em **`CLAUDE.md`** (mesma pasta) — leia-o antes de mexer no
> projeto. Este arquivo é um resumo para agentes/ferramentas que seguem a
> convenção `AGENTS.md`.

## O essencial

- **Repo:** `scale-ag/dash-giaco-sdc-form7` · **Pages:** https://scale-ag.github.io/dash-giaco-sdc-form7/
- **Modelo:** mesmas abas/layout de `dash-thata-opn`/`dash-davi-fse` (Visão Geral · Meta Ads · Insights de IA).
- **Fontes:** duas planilhas Google (Leads do Lead Ad + aba `QUERIES FORM7` do Meta Ads), somente leitura. IDs/gids no topo de `build/build.py`.
- **Funil:** `Gasto → Impressões → Alcance → Cliques → Leads`. Termina no lead.
- **Formulário NATIVO (Lead Ad):** sem landing page → sem Page Views/CR/ConvLP/CPV. Entram Alcance + Frequência; conversão = ConvForm (Leads/Cliques).
- **Sem qualificação** (decisão do cliente): nada de MQL/Lead A, agendamentos, vendas, faturamento, CAC, ROAS.
- **Lead válido:** não orgânico **e** campanha começando com `SDC` **e** nome/e-mail/telefone preenchidos **e** não é teste.
- **Casamento:** `campaign_name`/`adset_name`/`ad_name` iguais a `Campaign/Ad Set/Ad Name` do Meta.
- **Imposto:** `TAX_FACTOR=1.13806`; toggle "Imposto Meta" ligado por padrão.
- **Build:** `python build/build.py --leads-file leads.csv --meta-file queries.csv --out dist/index.html`.

## Onde mexer

| Quero mudar… | Arquivo |
|---|---|
| IDs/gids das planilhas, regra de lead válido, imposto, limiares de amostra, fuso | `build/build.py` |
| Só as cores (tema claro/escuro) | `build/identidade-visual.css` |
| Layout/componentes | `build/estilos.css` |
| KPIs, funil, tabelas, gráficos, filtro cruzado | `build/app.js` |
| Título, logo, textos fixos da página | `build/template.html` |
| Publicação | `.github/workflows/deploy.yml` · `SETUP-CRON.md` |

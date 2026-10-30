#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera a dashboard estatica (index.html) de Captacao de Leads do funil
"A Sala do Conselho" (SDC · FORM7) a partir de DUAS planilhas do Google Sheets
(somente leitura):

  - "SDC FORM 7 NOVOOO" (gid 0): fonte PRINCIPAL de leads — cada linha e uma
    submissao do FORMULARIO NATIVO (Lead Ad / Instant Form) do Meta, ja com a
    atribuicao de campanha/conjunto/anuncio e a plataforma (Instagram/Facebook).
  - "Giaco | SDC | Planilha Central", aba "QUERIES FORM7" (gid 1320534268):
    investimento/impressoes/cliques/alcance do gerenciador (Meta Ads), uma linha
    por dia x campanha x conjunto x anuncio.

LEAD VALIDO (mesma regra ja usada para este formulario): so entra na dashboard
o lead que veio de MIDIA PAGA e esta completo — ver is_valid_lead():
  1. is_organic == false  (veio de anuncio, nao de alcance organico);
  2. campaign_name comeca com MAIN_PRODUCT_PREFIX ("SDC");
  3. nome, e-mail e telefone preenchidos;
  4. nao e cadastro de teste (dummy data do Meta, @meta.com, nome "Teste ...").

O casamento com o Meta Ads e EXATO, sem heuristica (os nomes do gerenciador
vem iguais nos dois lados):
    campaign_name == Campaign Name · adset_name == Ad Set Name · ad_name == Ad Name

FUNIL DESTA CONTA (formulario nativo, sem landing page):
    Gasto -> Impressoes -> Alcance -> Cliques -> Leads
com CPM · Frequencia (Impressoes/Alcance) · CTR · CPC · ConvForm (Leads/Cliques) · CPL.
Nao ha Page Views/ConvLP/CPV (nao existe LP) nem MQL/qualificacao, agendamentos,
vendas ou faturamento (fora do escopo desta dash — decisao do cliente). A coluna
"Leads" da aba de Queries (contagem do proprio Meta) NAO e usada: a fonte de
verdade dos leads e a planilha de leads (cadastros validos).

Este script apenas LE as planilhas (export CSV publico) e emite os REGISTROS
BRUTOS (leads[] e meta[]) dentro do HTML. Todos os filtros, agregacoes, KPIs,
tabelas e graficos sao calculados no navegador (client-side). Nunca escreve
nada de volta.

Teste local: --leads-file / --meta-file apontando para CSVs baixados.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# Planilha de Leads ("SDC FORM 7 NOVOOO") — fonte principal (formulario nativo do Meta).
SPREADSHEET_ID_LEADS = "1a-bUrbN8fuJWPBSEIc24Kp-h--xHeQLTFOLljS50NkQ"
GID_LEADS = "0"
# Planilha central ("Giaco | SDC | Planilha Central"), aba "QUERIES FORM7" — midia paga.
SPREADSHEET_ID_META = "1Uep5K2-fJqBxNX-j8rDa-7V-Q2-iCRlz9S6KzR37VsQ"
GID_META = "1320534268"
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"

# Identificação do cliente/conta (usada só em textos/relatórios — não afeta o cruzamento de dados).
CLIENT_NAME = "Giaco"
MAIN_PRODUCT = "A Sala do Conselho · FORM7"
# Sigla do funil / prefixo comum a TODAS as campanhas da conta:
#   SDC | E2-CAP | P1-FRIO | | 2026-07-22 | PFRIO|  FORM7
#   ^^^ sigla (SDC = "Sala do Conselho") — é ela que valida o lead (is_valid_lead).
MAIN_PRODUCT_PREFIX = "SDC"

# --------------------------------------------------------------------------- #
# Fusos horarios — "created_time" vem em ISO com offset (ex.: -03:00) e o "Day"
# do Meta Ads ja vem fechado no fuso da conta. O padrao e a conta em
# America/Sao_Paulo: o dia do lead e convertido para ACCOUNT_TZ antes de virar
# data (leads gravados com outro offset, ex. -05:00, caem no dia certo). Se a
# conta de anuncios estiver em outro fuso, troque ACCOUNT_TZ_NAME.
LEADS_TZ_NAME = "America/Sao_Paulo"    # fuso assumido quando created_time vier SEM offset
ACCOUNT_TZ_NAME = "America/Sao_Paulo"  # fuso da conta de anuncios (dia de referencia da dash)
try:                                    # tzdata do sistema (runner do Actions tem)
    from zoneinfo import ZoneInfo
    LEADS_TZ = ZoneInfo(LEADS_TZ_NAME)
    ACCOUNT_TZ = ZoneInfo(ACCOUNT_TZ_NAME)
except Exception:                       # sem tz database: offset fixo equivalente
    LEADS_TZ = timezone(timedelta(hours=-3))
    ACCOUNT_TZ = timezone(timedelta(hours=-3))

BRT = timezone(timedelta(hours=-3))   # horario de Brasilia (so p/ o carimbo "ultima atualizacao")
TAX_FACTOR = 1.13806   # fator de imposto/taxa sobre o gasto de mídia paga (Meta Ads) = 13,806%.
                       # O toggle "Imposto Meta" ja vem LIGADO (app.js STATE.tax=true): gasto e
                       # derivados (CPM, CPC, CPL) saem com o imposto. Desligar mostra o gasto bruto.

# --------------------------------------------------------------------------- #
# Regras da aba Insights de IA (Top Anúncios)
# --------------------------------------------------------------------------- #
# Amostra mínima para JULGAR um anúncio (Escalar/Manter/Cortar). Abaixo disso ele
# fica "Observar" — nunca é classificado só porque teve 1 lead com pouco gasto.
SAMPLE_MIN_SPEND = 100.0   # gasto mínimo (R$, sem imposto) para amostra relevante
SAMPLE_MIN_LEADS = 3       # leads mínimos para julgar o anúncio
TOP_ADS_N = 10             # nº de linhas de referência dos rankings

# Metas & parâmetros da conta (DEFAULTS do painel editável da aba Insights de IA).
# São só o valor inicial: o gestor edita no navegador (localStorage) e a tabela
# de anúncios recolore o CPL e reavalia o Status ao vivo. None = "não definida".
META_CPL = None            # meta de CPL (R$/lead); None = não definida
VOLUME_MIN_AMOSTRAL = SAMPLE_MIN_LEADS  # leads mínimos p/ amostra confiável
N_DIAS_CORTE = 5           # dias consecutivos acima do teto p/ considerar corte


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
FETCH_RETRIES = 3       # tentativas totais em caso de timeout/erro de rede no export CSV
FETCH_RETRY_DELAY = 15  # segundos entre tentativas (o Google Sheets às vezes trava a resposta)


def fetch_csv(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "dash-giaco-sdc-form7-bot/1.0"})
    last_err: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return list(csv.reader(io.StringIO(raw)))
        except (TimeoutError, urllib.error.URLError) as exc:
            last_err = exc
            if attempt < FETCH_RETRIES:
                print(f"[fetch_csv] tentativa {attempt}/{FETCH_RETRIES} falhou ({exc!r}); "
                      f"tentando de novo em {FETCH_RETRY_DELAY}s...", file=sys.stderr)
                time.sleep(FETCH_RETRY_DELAY)
    raise last_err


def read_csv_file(path: str) -> list[list[str]]:
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.reader(f))


def load_rows(url: str, local: str | None) -> list[list[str]]:
    return read_csv_file(local) if local else fetch_csv(url)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str | None) -> str:
    return strip_accents((s or "").strip().lower())


def to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v).strip())
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(v: str) -> str | None:
    """Dia SEM conversao de fuso — usado no "Day" do Meta Ads, que ja vem fechado
    no fuso da conta. Para os leads use parse_lead_date()."""
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    s = s.split()[0]          # "08/09/2026 15:15" -> "08/09/2026"
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_lead_date(v: str) -> str | None:
    """Dia do lead no fuso da conta de anuncios (ACCOUNT_TZ).

    created_time vem em ISO com offset, ex.: "2026-08-31T07:56:55-03:00".
    Convertemos para ACCOUNT_TZ antes de extrair o dia; sem offset, assume
    LEADS_TZ. Devolve "YYYY-MM-DD"."""
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.astimezone(ACCOUNT_TZ).strftime("%Y-%m-%d")
        return dt.replace(tzinfo=LEADS_TZ).astimezone(ACCOUNT_TZ).strftime("%Y-%m-%d")
    except ValueError:
        pass
    s2 = re.sub(r"\s+", " ", s)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s2, fmt)
        except ValueError:
            continue
        return dt.replace(tzinfo=LEADS_TZ).astimezone(ACCOUNT_TZ).strftime("%Y-%m-%d")
    return parse_date(s)


# --------------------------------------------------------------------------- #
# Regra de LEAD VÁLIDO
# --------------------------------------------------------------------------- #
# Cadastro de teste: dummy data do próprio Meta ("<test lead: ...>"), e-mail de
# domínio de teste (o "Testar lead" do Meta usa @meta.com) ou nome/e-mail que
# começa com a palavra "teste"/"test" (ex.: "Teste ingenium"). Nunca bate em nome
# real que só contenha essas letras no meio (ex.: "Celeste").
_TEST_WORD_RE = re.compile(r"^(teste|test)\d*$")
_TEST_EMAIL_DOMAINS = ("teste.com", "test.com", "example.com", "meta.com")


def is_organic(v: str) -> bool:
    return norm(v) in ("true", "1", "sim", "yes", "verdadeiro")


def is_test_lead(name: str, email: str, rowtext: str = "") -> bool:
    if "<test lead" in (rowtext or "").lower():
        return True
    first = (norm(name).split() or [""])[0]
    if _TEST_WORD_RE.match(first):
        return True
    e = norm(email)
    if "@" in e:
        local, _, domain = e.partition("@")
        if domain in _TEST_EMAIL_DOMAINS or _TEST_WORD_RE.match(local):
            return True
    return False


def lead_discard_reason(organic: str, campaign: str, name: str, email: str, phone: str,
                        rowtext: str) -> str | None:
    """None = lead válido. Senão, o motivo do descarte (para o log do build)."""
    if is_organic(organic):
        return "organico"
    if not norm(campaign).startswith(norm(MAIN_PRODUCT_PREFIX)):
        return "fora_da_campanha"
    if not (name.strip() and email.strip() and phone.strip()):
        return "incompleto"
    if is_test_lead(name, email, rowtext):
        return "teste"
    return None


def is_valid_lead(organic: str, campaign: str, name: str, email: str, phone: str,
                  rowtext: str = "") -> bool:
    return lead_discard_reason(organic, campaign, name, email, phone, rowtext) is None


def first_last_initial(name: str) -> str:
    parts = (name or "").strip().split()
    if not parts:
        return "—"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][:1]}."


def mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return "—"
    user, dom = e.split("@", 1)
    keep = user[:2] if len(user) > 2 else user[:1]
    return f"{keep}****@{dom}"


def mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")   # tira o prefixo "p:" e o "+", sobra só dígito
    return f"…{digits[-4:]}" if len(digits) >= 4 else "—"


# Plataforma (coluna "platform" do Lead Ad) -> rótulo legível.
PLATFORM_LABELS = {
    "ig": "Instagram",
    "instagram": "Instagram",
    "fb": "Facebook",
    "facebook": "Facebook",
    "msg": "Messenger",
    "an": "Audience Network",
    "audience_network": "Audience Network",
}


def pretty_platform(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return "Não informado"
    return PLATFORM_LABELS.get(norm(s), s)


def pretty_answer(v: str) -> str:
    """Resposta do formulário nativo vem em snake_case minúsculo
    ("empresário_/_sócio_/_dono_de_empresa") -> "Empresário / sócio / dono de empresa"."""
    s = (v or "").strip()
    if not s or s.lower().startswith("<test lead"):
        return "Sem resposta"
    s = re.sub(r"\s+", " ", s.replace("_", " ")).strip().rstrip(" .")
    return (s[:1].upper() + s[1:]) if s else "Sem resposta"


# --------------------------------------------------------------------------- #
# Indexacao das colunas
# --------------------------------------------------------------------------- #
def header_index(header, wanted, fallback):
    """1º passe: nome exato (normalizado); 2º passe: cabeçalho que CONTÉM o alias."""
    idx = {}
    hn = [norm(h) for h in header]
    for key, aliases in wanted.items():
        found = None
        for a in aliases:
            a = norm(a)
            for i, h in enumerate(hn):
                if h == a:
                    found = i
                    break
            if found is not None:
                break
        if found is None:
            for a in aliases:
                a = norm(a)
                for i, h in enumerate(hn):
                    if a and a in h:
                        found = i
                        break
                if found is not None:
                    break
        idx[key] = found if found is not None else fallback.get(key)
    return idx


def cell(row, i):
    if i is None or i < 0 or i >= len(row):
        return ""
    return (row[i] or "").strip()


# --------------------------------------------------------------------------- #
# Processamento -> registros brutos
# --------------------------------------------------------------------------- #
def process(leads_rows, meta_rows):
    # ---- Meta Ads (Queries FORM7) ----
    mheader = meta_rows[0] if meta_rows else []
    midx = header_index(
        mheader,
        {"day": ["day", "data"], "campaign": ["campaign name", "campaign"],
         "adset": ["ad set name", "adset name", "adset"], "ad": ["ad name"],
         "spent": ["amount spent", "valor gasto", "gasto"], "impr": ["impressions", "impressoes"],
         "clicks": ["link clicks", "cliques no link", "clicks"], "reach": ["reach", "alcance"]},
        {"day": 0, "campaign": 1, "adset": 2, "ad": 3, "spent": 4, "impr": 5, "clicks": 6, "reach": 8},
    )
    print(f"  [meta] colunas mapeadas: {midx}", file=sys.stderr)

    meta = []
    meta_keys: set[tuple[str, str, str]] = set()
    for row in meta_rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        day = parse_date(cell(row, midx["day"]))
        camp = cell(row, midx["campaign"])
        if not day and not camp:
            continue
        adset = cell(row, midx["adset"]) or "(sem conjunto)"
        ad = cell(row, midx["ad"]) or "(sem anúncio)"
        camp = camp or "(sem campanha)"
        meta_keys.add((camp, adset, ad))
        meta.append({
            "d": day,
            "camp": camp,
            "adset": adset,
            "ad": ad,
            "sp": round(to_float(cell(row, midx["spent"])), 4),
            "im": to_float(cell(row, midx["impr"])),
            "cl": to_float(cell(row, midx["clicks"])),
            "rc": to_float(cell(row, midx["reach"])),
        })

    # ---- Leads (formulário nativo) ----
    lheader = leads_rows[0] if leads_rows else []
    lidx = header_index(
        lheader,
        {"created": ["created_time"], "name": ["full_name", "nome completo", "nome"],
         "email": ["email", "e-mail"], "phone": ["phone_number", "telefone"],
         "organic": ["is_organic"], "campaign": ["campaign_name"],
         "adset": ["adset_name"], "ad": ["ad_name"], "platform": ["platform", "plataforma"],
         # perguntas do formulário usadas como dimensão nos gráficos de distribuição
         "perfil": ["papel_como_profissional"], "area": ["area_de_especialidade"]},
        {"created": 1, "name": 22, "email": 21, "phone": 23, "organic": 10,
         "campaign": 7, "adset": 5, "ad": 3, "platform": 11},
    )
    print(f"  [leads] colunas mapeadas: {lidx}", file=sys.stderr)

    leads = []
    descartados = {"organico": 0, "fora_da_campanha": 0, "incompleto": 0, "teste": 0}
    sem_meta = 0
    for row in leads_rows[1:]:
        if not any((c or "").strip() for c in row):
            continue
        organic = cell(row, lidx["organic"])
        campaign = cell(row, lidx["campaign"])
        name = cell(row, lidx["name"])
        email = cell(row, lidx["email"])
        phone = cell(row, lidx["phone"])
        why = lead_discard_reason(organic, campaign, name, email, phone, " ".join(row))
        if why:
            descartados[why] += 1
            continue
        adset = cell(row, lidx["adset"]) or "(sem conjunto)"
        ad = cell(row, lidx["ad"]) or "(sem anúncio)"
        trk = 1 if (campaign, adset, ad) in meta_keys else 0
        sem_meta += 1 - trk
        leads.append({
            "d": parse_lead_date(cell(row, lidx["created"])),
            # Todo lead que chega aqui é, por definição, de mídia paga (Meta Ads).
            "src": "meta",
            "plat": pretty_platform(cell(row, lidx["platform"])),
            "camp": campaign,
            "adset": adset,
            "ad": ad,
            # 1 = o anúncio (campanha+conjunto+anúncio) existe na aba de Queries
            # (tem gasto/impressões rastreados); 0 = lead sem mídia correspondente.
            "trk": trk,
            "perfil": pretty_answer(cell(row, lidx["perfil"])),
            "area": pretty_answer(cell(row, lidx["area"])),
            "nm": first_last_initial(name),
            "em": mask_email(email),
            "ph": mask_phone(phone),
        })

    dates = sorted({d for d in ([l["d"] for l in leads if l["d"]] + [m["d"] for m in meta if m["d"]])})
    now_brt = datetime.now(BRT)              # carimbo "ultima atualizacao" (hora local do gestor)
    hoje_conta = datetime.now(ACCOUNT_TZ)    # "hoje" do funil = dia no fuso da conta de anuncios
    return {
        "build": {
            "generated_at_brt": now_brt.strftime("%d/%m/%Y %H:%M"),
            "build_id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "today": hoje_conta.strftime("%Y-%m-%d"),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "tax_factor": TAX_FACTOR,
            "account_tz": ACCOUNT_TZ_NAME,
            "client_name": CLIENT_NAME,
            "main_product": MAIN_PRODUCT,
            # config da aba Insights de IA (lida pelo front)
            "sample_min_spend": SAMPLE_MIN_SPEND,
            "sample_min_leads": SAMPLE_MIN_LEADS,
            "top_ads_n": TOP_ADS_N,
            # metas & parâmetros (defaults do painel editável; None = não definida)
            "meta_cpl": META_CPL,
            "volume_min_amostral": VOLUME_MIN_AMOSTRAL,
            "n_dias_corte": N_DIAS_CORTE,
            # diagnóstico (log do build)
            "leads_descartados": descartados,
            "leads_sem_meta": sem_meta,
        },
        "leads": leads,
        "meta": meta,
        # Insights de Tráfego (texto pré-escrito, lido de relatorios.json). Preenchido
        # em main() via load_briefings(); fica {} se relatorios.json não existir.
        "briefings": {},
    }


# --------------------------------------------------------------------------- #
# Insights de Tráfego (aba Insights de IA)
# --------------------------------------------------------------------------- #
def load_briefings(path: str) -> dict:
    """Lê build/relatorios.json. Estrutura:
        {"generated_at": "...", "periodos": {"<preset>": {...}, ...}}
    Retorna o dict inteiro (ou {} se o arquivo não existir/for inválido).
    A geração NÃO acontece aqui — este build só lê o texto já pronto, sem
    chamar nenhuma API (custo zero no build/no navegador)."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (ValueError, OSError):
        return {}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(data, template_path):
    # A dashboard e montada a partir de arquivos separados (visual x logica):
    #   template.html          -> esqueleto HTML (placeholders __STYLES__/__APP_JS__)
    #   identidade-visual.css  -> TODAS as cores (edite aqui p/ mexer so em cor)
    #   estilos.css            -> layout/componentes
    #   app.js                 -> logica + renderizacao
    # Esta funcao so COSTURA os arquivos e injeta os dados; nao altera nada deles.
    base = os.path.dirname(os.path.abspath(template_path))

    def readf(name):
        with open(os.path.join(base, name), "r", encoding="utf-8") as f:
            return f.read()

    with open(template_path, "r", encoding="utf-8") as f:
        tpl = f.read()
    styles = readf("identidade-visual.css") + "\n" + readf("estilos.css")
    # "</" dentro do JSON fecharia o <script> do payload antes da hora
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tpl = tpl.replace("__STYLES__", styles)
    tpl = tpl.replace("__APP_JS__", readf("app.js"))
    tpl = tpl.replace("__DATA_JSON__", payload)
    tpl = tpl.replace("__BUILD_ID__", data["build"]["build_id"])
    tpl = tpl.replace("__GENERATED_BRT__", data["build"]["generated_at_brt"])
    return tpl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leads-file", help="CSV local da planilha de Leads (fonte principal)")
    ap.add_argument("--meta-file", help="CSV local da aba QUERIES FORM7 (Meta Ads)")
    ap.add_argument("--template", default="build/template.html")
    ap.add_argument("--out", default="dist/index.html")
    args = ap.parse_args()

    leads_rows = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID_LEADS, gid=GID_LEADS), args.leads_file)
    meta_rows = load_rows(EXPORT_URL.format(sid=SPREADSHEET_ID_META, gid=GID_META), args.meta_file)

    data = process(leads_rows, meta_rows)

    # Insights de Tráfego (texto pré-escrito) — lidos do arquivo versionado ao
    # lado do template. Sem chamada de API no build.
    briefings_path = os.path.join(os.path.dirname(os.path.abspath(args.template)), "relatorios.json")
    data["briefings"] = load_briefings(briefings_path)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(data, args.template))

    b = data["build"]
    d = b["leads_descartados"]
    sp = sum(m["sp"] for m in data["meta"])
    print("== build ok ==", file=sys.stderr)
    print(f"  periodo    : {b['date_min']} -> {b['date_max']} (hoje {b['today']})", file=sys.stderr)
    print(f"  leads      : {len(data['leads'])} válidos "
          f"(mídia paga + campanha {MAIN_PRODUCT_PREFIX} + cadastro completo)", file=sys.stderr)
    print(f"  descartados: {d['organico']} orgânicos · {d['fora_da_campanha']} fora da campanha · "
          f"{d['incompleto']} incompletos · {d['teste']} de teste", file=sys.stderr)
    print(f"  sem mídia  : {b['leads_sem_meta']} lead(s) cujo anúncio não aparece na aba de Queries",
          file=sys.stderr)
    print(f"  meta       : {len(data['meta'])} linhas · gasto R$ {sp:,.2f} "
          f"(sem imposto; fator {TAX_FACTOR})", file=sys.stderr)
    print(f"  out        : {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

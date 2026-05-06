#!/usr/bin/env python3
"""
Fase A v2: Scraping de CNPJ dos 50 leads.
Estratégia em 3 camadas:
  1. requests  — GET rápido em subpáginas estáticas (rodapé, politica, termos)
  2. Playwright — renderiza JS; clica em itens de nav (Sobre, Termos, Contato)
  3. Econodata  — busca por nome da empresa como último recurso
Output: cnpj_encontrados.json
"""
import csv, json, os, re, sys, io, time, unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests as req_lib

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE   = Path(__file__).parent
CSV_IN = BASE / "leads_merged.csv"
OUT    = BASE / "cnpj_encontrados.json"

CNPJ_REGEX = re.compile(r"\b(\d{2})[\.\-]?(\d{3})[\.\-]?(\d{3})[\/\-]?(\d{4})[\-\.]?(\d{2})\b")

SUBPAGES = [
    "", "/contato", "/sobre", "/sobre-nos", "/quem-somos",
    "/politica-de-privacidade", "/politica-privacidade",
    "/termos", "/termos-de-uso", "/empresa", "/info",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# CNPJ de plataformas de delivery — ignorar
CNPJ_BLACKLIST = {
    "14380200000121",  # iFood
    "00776574000135",  # iFood (alt)
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def normalize_cnpj(groups):
    return f"{groups[0]}.{groups[1]}.{groups[2]}/{groups[3]}-{groups[4]}"

def cnpj_valido(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    def calc(d, weights):
        s = sum(int(d[i]) * weights[i] for i in range(len(weights)))
        r = s % 11
        return 0 if r < 2 else 11 - r
    return (int(digits[12]) == calc(digits, [5,4,3,2,9,8,7,6,5,4,3,2]) and
            int(digits[13]) == calc(digits, [6,5,4,3,2,9,8,7,6,5,4,3,2]))

def find_cnpj(text: str):
    for m in CNPJ_REGEX.finditer(text):
        cnpj  = normalize_cnpj(m.groups())
        digits = re.sub(r"\D", "", cnpj)
        if cnpj_valido(digits) and digits not in CNPJ_BLACKLIST:
            return cnpj
    return None

def get_root(url: str):
    if not url: return None
    try:
        p = urlparse(url if url.startswith("http") else "http://" + url)
        return f"{p.scheme}://{p.netloc}"
    except: return None

def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s

def cidade_slug(endereco: str) -> str:
    """Extrai cidade do endereço e transforma em slug para Econodata."""
    m = re.search(r"-\s*([^,-]+?)\s*-\s*SP", endereco)
    cidade = m.group(1).strip() if m else "SAO-PAULO"
    return slugify(cidade).upper().replace("-", "-")


# ─── Camada 1: requests ────────────────────────────────────────────────────────

def scrape_requests(lead: dict):
    site  = (lead.get("site") or "").strip()
    root  = get_root(site)
    if not root:
        return None, []
    tentadas = []
    for sub in SUBPAGES:
        url = root + sub
        tentadas.append(url)
        try:
            r = req_lib.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if r.status_code != 200: continue
            cnpj = find_cnpj(r.text)
            if cnpj:
                return cnpj, tentadas
        except: continue
    return None, tentadas


# ─── Camada 2: Playwright ──────────────────────────────────────────────────────

NAV_CLICK_TEXTS = ["sobre", "sobre nós", "sobre nos", "quem somos",
                   "termos", "termos de uso", "politica", "empresa", "info"]

def scrape_playwright(page, lead: dict):
    site = (lead.get("site") or "").strip()
    root = get_root(site)
    if not root: return None

    try:
        page.goto(root, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2500)

        # Tenta no conteúdo atual
        cnpj = find_cnpj(page.content())
        if cnpj: return cnpj
        cnpj = find_cnpj(page.inner_text("body"))
        if cnpj: return cnpj

        # Tenta clicar em links de nav que parecem "Sobre/Termos"
        links = page.locator("a, button").all()
        for link in links[:40]:
            try:
                txt = (link.inner_text() or "").lower().strip()
                if any(t in txt for t in NAV_CLICK_TEXTS):
                    link.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    cnpj = find_cnpj(page.content())
                    if cnpj: return cnpj
                    cnpj = find_cnpj(page.inner_text("body"))
                    if cnpj: return cnpj
                    page.go_back(timeout=3000)
                    page.wait_for_timeout(1000)
            except: continue

        # Tenta subpáginas via Playwright
        for sub in ["/sobre", "/termos", "/politica-de-privacidade", "/contato"]:
            try:
                page.goto(root + sub, wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(1500)
                cnpj = find_cnpj(page.content())
                if cnpj: return cnpj
            except: continue

    except Exception as e:
        pass

    return None


# ─── Camada 3: Econodata ───────────────────────────────────────────────────────

def scrape_econodata(lead: dict):
    nome     = lead.get("nome", "")
    endereco = lead.get("endereco", "")
    cidade   = cidade_slug(endereco)

    # Tenta variações do nome (nome completo → primeira palavra → duas primeiras)
    palavras = [w for w in re.split(r"[\s\-–|/]", nome) if len(w) > 2]
    tentativas_nome = [
        slugify(nome),
        slugify(" ".join(palavras[:3])) if len(palavras) >= 3 else None,
        slugify(" ".join(palavras[:2])) if len(palavras) >= 2 else None,
        slugify(palavras[0]) if palavras else None,
    ]
    tentativas_nome = list(dict.fromkeys(n for n in tentativas_nome if n))

    cidades_tentar = [cidade, "SAO-PAULO"]

    for nome_slug in tentativas_nome:
        for cid in cidades_tentar:
            url = f"https://www.econodata.com.br/empresas/SP--{cid}/{nome_slug}"
            try:
                r = req_lib.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
                if r.status_code != 200: continue
                cnpj = find_cnpj(r.text)
                if cnpj:
                    return cnpj, url
            except: continue
            time.sleep(0.3)

    return None, None


# ─── Pipeline principal ────────────────────────────────────────────────────────

def process_lead(page, lead: dict) -> dict:
    nome = lead.get("nome", "")
    lid  = lead["id"]
    site = (lead.get("site") or "").strip()

    # --- Camada 1: requests ---
    cnpj, tentadas = scrape_requests(lead)
    if cnpj:
        return {"id": lid, "nome": nome, "site": site,
                "cnpj": cnpj, "metodo": "requests",
                "pagina_origem": tentadas[-1], "paginas_tentadas": tentadas}

    # --- Camada 2: Playwright ---
    if page and site and "instagram.com" not in site and "ifood.com" not in site:
        cnpj = scrape_playwright(page, lead)
        if cnpj:
            return {"id": lid, "nome": nome, "site": site,
                    "cnpj": cnpj, "metodo": "playwright",
                    "paginas_tentadas": tentadas}

    # --- Camada 3: Econodata ---
    cnpj, src_url = scrape_econodata(lead)
    if cnpj:
        return {"id": lid, "nome": nome, "site": site,
                "cnpj": cnpj, "metodo": "econodata",
                "pagina_origem": src_url, "paginas_tentadas": tentadas}

    return {"id": lid, "nome": nome, "site": site,
            "cnpj": None, "paginas_tentadas": tentadas}


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    leads = []
    with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh), 1):
            if i > 50: break
            row["id"] = i
            leads.append(row)

    print(f"Buscando CNPJ de {len(leads)} leads (requests + Playwright + Econodata)...\n")

    results = []
    start = time.time()

    try:
        from playwright.sync_api import sync_playwright
        pw_disponivel = True
    except ImportError:
        pw_disponivel = False
        print("[aviso] Playwright não instalado — pulando camada 2")

    def run(page_ctx):
        for lead in leads:
            r = process_lead(page_ctx, lead)
            results.append(r)
            status = f"  [{r['id']:2d}] {r['nome'][:45]:45s} | "
            if r.get("cnpj"):
                status += f"✓ {r['cnpj']}  [{r.get('metodo','')}]"
            else:
                status += "—"
            print(status)

    if pw_disponivel:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(user_agent=HEADERS["User-Agent"], locale="pt-BR")
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()
            run(page)
            browser.close()
    else:
        run(None)

    elapsed = time.time() - start
    results.sort(key=lambda x: x["id"])

    com_cnpj = [r for r in results if r.get("cnpj")]
    por_metodo = {}
    for r in com_cnpj:
        m = r.get("metodo", "?")
        por_metodo[m] = por_metodo.get(m, 0) + 1

    print(f"\n{'='*50}")
    print(f"Tempo: {elapsed:.1f}s")
    print(f"CNPJs encontrados: {len(com_cnpj)}/{len(results)}")
    for m, n in por_metodo.items():
        print(f"  via {m}: {n}")
    print(f"CNPJs únicos: {len(set(r['cnpj'] for r in com_cnpj))}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"Salvo: {OUT}")


if __name__ == "__main__":
    main()

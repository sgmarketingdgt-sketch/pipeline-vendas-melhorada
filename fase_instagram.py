"""
fase_instagram.py — Fase 8b: Busca Instagram do local e dos responsáveis

Estratégia (sem login):
  1. Site do lead → raspa links instagram.com → instagram_local_url
  2. Google via Playwright → busca "<nome_dono> <empresa> instagram" → extrai usernames
  3. Perfil público do Instagram → extrai bio (sem autenticação, apenas head HTML)

Campos adicionados ao lead:
  instagram_local_url       str  URL do perfil da empresa
  instagram_dono_url        str  URL do perfil do dono/CEO
  instagram_dono_nome       str  Nome exibido no Instagram do dono
  instagram_dono_bio        str  Bio do perfil do dono
  instagram_decisor_url     str  URL do decisor de marketing
  instagram_decisor_nome    str  Nome exibido do decisor
  instagram_decisor_bio     str  Bio do decisor

Cache: instagram_validado.json  (chave: lead id, str)
Roda depois de: fase_email.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
LEADS_FILE   = "leads_final.json"
CACHE_FILE   = "instagram_validado.json"
DELAY        = 1.5     # segundos entre requisições simples
DELAY_GOOGLE = 3.0     # segundos entre buscas Google (evitar bloqueio)
REQUEST_TIMEOUT = 8    # segundos para requests HTTP

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Perfis de proxy (marcas de domínio protegido) — ignorar
PROXY_KEYWORDS = {"markmonitor", "domainsbyproxy", "godaddy", "privacyprotect", "whoisguard"}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def load_cache() -> dict:
    if Path(CACHE_FILE).exists():
        try:
            return json.loads(Path(CACHE_FILE).read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    Path(CACHE_FILE).write_text(json.dumps(cache, ensure_ascii=False, indent=2), "utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
IG_URL_RE = re.compile(
    r'https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,30})(?:/|\b)',
    re.IGNORECASE,
)


def normalize_ig_url(url: str) -> str:
    """Retorna URL canônica https://www.instagram.com/username/"""
    m = IG_URL_RE.search(url)
    if not m:
        return ""
    username = m.group(1).lower().strip(".")
    if username in ("p", "reel", "reels", "stories", "tv", "explore", "accounts"):
        return ""
    return f"https://www.instagram.com/{username}/"


def extract_ig_links_from_html(html: str) -> list[str]:
    """Extrai todos os links do Instagram encontrados no HTML."""
    found = []
    for m in IG_URL_RE.finditer(html):
        url = normalize_ig_url(m.group(0))
        if url and url not in found:
            found.append(url)
    return found


def scrape_site_for_ig(site_url: str) -> str:
    """Raspa o site do lead em busca de link do Instagram. Retorna URL ou ''."""
    if not site_url or not site_url.startswith("http"):
        return ""
    try:
        r = requests.get(site_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return ""
        links = extract_ig_links_from_html(r.text)
        # Preferir links no footer/rodapé (aparecem mais perto do final)
        if links:
            return links[-1]
    except Exception:
        pass
    return ""


def fetch_ig_profile_bio(ig_url: str, browser_page) -> dict:
    """
    Obtém bio e nome exibido de um perfil público do Instagram.
    Usa Playwright sem login — funciona para perfis públicos via meta tags.
    Retorna {'nome': str, 'bio': str}
    """
    if not ig_url:
        return {"nome": "", "bio": ""}
    try:
        browser_page.goto(ig_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(1.5)

        html = browser_page.content()

        # Tenta meta og:description (costuma ter "bio" pública)
        bio = ""
        nome = ""

        og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if og_desc:
            bio = og_desc.group(1).strip()
            # Instagram formata: "X Followers, Y Following, Z Posts - See Instagram photos..."
            # Remove essa parte padrão
            bio = re.sub(r'\d[\d,]*\s+Followers.*$', '', bio, flags=re.IGNORECASE).strip()
            bio = re.sub(r'\d[\d,]*\s+seguidores.*$', '', bio, flags=re.IGNORECASE).strip()
            bio = bio.rstrip(" -|·")

        og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if og_title:
            nome = og_title.group(1).strip()
            # Remove sufixo padrão " (@username) • Instagram photos and videos"
            nome = re.sub(r'\s*\(@[^)]+\).*$', '', nome).strip()
            nome = re.sub(r'\s*•.*$', '', nome).strip()

        return {"nome": nome, "bio": bio}
    except Exception:
        return {"nome": "", "bio": ""}


def google_search_ig(query: str, browser_page) -> str:
    """
    Busca no Google via Playwright e extrai o primeiro username do Instagram
    encontrado nos resultados.
    """
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=10&hl=pt-BR"
    try:
        browser_page.goto(url, timeout=20000, wait_until="domcontentloaded")
        time.sleep(DELAY_GOOGLE)
        html = browser_page.content()
        links = extract_ig_links_from_html(html)
        if links:
            return links[0]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Lógica principal por lead
# ---------------------------------------------------------------------------
def process_lead(lead: dict, cache: dict, page) -> dict | None:
    """
    Processa um lead e retorna os campos de Instagram encontrados.
    Retorna None se o lead já estava no cache.
    """
    lid = str(lead.get("id", ""))
    if lid in cache:
        return None  # já processado

    result: dict = {
        "instagram_local_url":    "",
        "instagram_dono_url":     "",
        "instagram_dono_nome":    "",
        "instagram_dono_bio":     "",
        "instagram_decisor_url":  "",
        "instagram_decisor_nome": "",
        "instagram_decisor_bio":  "",
    }

    # 1. Instagram do local — já temos em lead.instagram.url?
    existing_ig = ""
    if isinstance(lead.get("instagram"), dict):
        existing_ig = lead["instagram"].get("url", "")
    result["instagram_local_url"] = normalize_ig_url(existing_ig) if existing_ig else ""

    # Se não tem, tenta raspar o site
    if not result["instagram_local_url"] and lead.get("site"):
        print(f"  [{lead['nome']}] Raspando site em busca de Instagram…")
        found = scrape_site_for_ig(lead["site"])
        if found:
            result["instagram_local_url"] = found
            print(f"  → Instagram local: {found}")
        time.sleep(DELAY)

    # 2. Instagram do dono/CEO
    # Candidatos: whois_nome, primeiro sócio do CNPJ, lead.dono
    candidatos = []
    if lead.get("whois_nome"):
        candidatos.append(lead["whois_nome"])
    socios = lead.get("socios_cnpj", [])
    if socios:
        for s in socios[:2]:
            nome_socio = s.get("nome", "").strip()
            if nome_socio and nome_socio not in candidatos:
                candidatos.append(nome_socio)
    if lead.get("dono") and lead["dono"] not in candidatos:
        candidatos.append(lead["dono"])

    empresa = lead.get("nome", "")
    nicho   = lead.get("segmento", "")

    if candidatos:
        nome_busca = candidatos[0]
        query = f'site:instagram.com "{nome_busca}" "{empresa}"'
        print(f"  [{lead['nome']}] Google → dono: {nome_busca}")
        ig_url = google_search_ig(query, page)

        if not ig_url and nicho:
            # Tenta com nicho ao invés do nome da empresa
            query2 = f'site:instagram.com "{nome_busca}" {nicho}'
            ig_url = google_search_ig(query2, page)

        if ig_url:
            result["instagram_dono_url"] = ig_url
            print(f"  → Dono Instagram: {ig_url}")
            profile = fetch_ig_profile_bio(ig_url, page)
            result["instagram_dono_nome"] = profile["nome"]
            result["instagram_dono_bio"]  = profile["bio"]

        # 3. Decisor: segundo candidato (ex: sócio de marketing ou whois secundário)
        if len(candidatos) > 1:
            nome_dec = candidatos[1]
            if nome_dec != nome_busca:
                query_dec = f'site:instagram.com "{nome_dec}" "{empresa}"'
                print(f"  [{lead['nome']}] Google → decisor: {nome_dec}")
                ig_dec = google_search_ig(query_dec, page)
                if ig_dec and ig_dec != ig_url:
                    result["instagram_decisor_url"] = ig_dec
                    print(f"  → Decisor Instagram: {ig_dec}")
                    profile_dec = fetch_ig_profile_bio(ig_dec, page)
                    result["instagram_decisor_nome"] = profile_dec["nome"]
                    result["instagram_decisor_bio"]  = profile_dec["bio"]

    cache[lid] = result
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not Path(LEADS_FILE).exists():
        print(f"[ERRO] {LEADS_FILE} não encontrado. Rode consolidate_v2.py primeiro.")
        return

    data = json.loads(Path(LEADS_FILE).read_text("utf-8"))
    leads = data.get("leads", [])
    cache = load_cache()

    pendentes = [l for l in leads if str(l.get("id", "")) not in cache]
    print(f"Instagram: {len(pendentes)} leads para processar ({len(leads) - len(pendentes)} já em cache)")

    if not pendentes:
        print("Nada a processar.")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        # Aceita cookie do Google se aparecer
        try:
            page.goto("https://www.google.com", timeout=10000)
            time.sleep(1)
            accept = page.query_selector("button:has-text('Accept'), button:has-text('Aceitar'), #L2AGLb")
            if accept:
                accept.click()
                time.sleep(0.5)
        except Exception:
            pass

        for i, lead in enumerate(pendentes, 1):
            print(f"\n[{i}/{len(pendentes)}] {lead.get('nome', '?')} — {lead.get('cidade', '?')}")
            try:
                result = process_lead(lead, cache, page)
                if result:
                    # Aplica ao lead
                    for k, v in result.items():
                        if v:
                            lead[k] = v
            except Exception as e:
                print(f"  [ERRO] {e}")
                cache[str(lead.get("id", ""))] = {}

            # Salva cache a cada lead para não perder progresso
            save_cache(cache)
            time.sleep(DELAY)

        browser.close()

    # Persiste leads_final.json com campos novos
    Path(LEADS_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
    )

    total_local   = sum(1 for l in leads if l.get("instagram_local_url"))
    total_dono    = sum(1 for l in leads if l.get("instagram_dono_url"))
    total_decisor = sum(1 for l in leads if l.get("instagram_decisor_url"))
    print(f"\n✦ Instagram local: {total_local}  |  Dono: {total_dono}  |  Decisor: {total_decisor}")
    print(f"✦ Cache salvo em {CACHE_FILE}")


if __name__ == "__main__":
    main()

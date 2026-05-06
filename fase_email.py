#!/usr/bin/env python3
"""
fase_email.py
=============
Coleta emails de decisores/empresa por 3 fontes públicas:
  1. Registro.br RDAP  → dominios .br (registrant/admin contact)
  2. Scraping do site   → regex em homepage + /contato + /sobre
  3. BrasilAPI CNPJ     → campo email da Receita Federal (fallback)

Saída: email_validado.json  →  [{id, nome, email, email_fonte, whois_nome}, ...]
Integrado ao consolidate_v2.py via EMAILS_CACHE.
"""

import json, re, time, sys, io
from pathlib import Path
from urllib.parse import urlparse, urljoin

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE       = Path(__file__).parent
LEADS_JSON = BASE / "leads_final.json"
OUT        = BASE / "email_validado.json"

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Instale requests: pip install requests")
    sys.exit(1)

# ── Sessão HTTP com retry suave ───────────────────────────────────────────────
def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    return s

SESSION = make_session()

# ── Helpers ───────────────────────────────────────────────────────────────────
BR_TLDS    = (".com.br", ".net.br", ".org.br", ".edu.br", ".ind.br", ".adv.br", ".tur.br")
EMAIL_RE   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Emails a ignorar (genéricos, plataformas, CMS)
IGNORE_PAT = re.compile(
    r"(noreply|no-reply|example|wordpress|sentry|wix|hostinger|"
    r"uol\.com\.br|terra\.com\.br|bol\.com\.br|godaddy|registro\.br|"
    r"icann|rdap|dnssec|abuse@|postmaster@|webmaster@|support@|"
    r"info@example|test@|"
    # Proxies de privacidade WHOIS e registradores
    r"markmonitor|domainsbyproxy|whoisguard|privacyguard|"
    r"contactprivacy|domains\.google|domainprotect|"
    r"registrar-abuse|registrant@|privacy@|protect@)",
    re.I,
)

def clean_domain(site: str) -> str | None:
    """Extrai domínio limpo de uma URL."""
    if not site:
        return None
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    try:
        parsed = urlparse(site)
        host = parsed.netloc.lower().lstrip("www.")
        return host or None
    except Exception:
        return None

def is_br_domain(domain: str) -> bool:
    return any(domain.endswith(t) for t in BR_TLDS)

def filter_emails(emails: list[str]) -> list[str]:
    seen, result = set(), []
    for e in emails:
        e = e.lower().strip()
        if e in seen or IGNORE_PAT.search(e):
            continue
        seen.add(e)
        result.append(e)
    return result


# ── Fonte 1: Registro.br RDAP ─────────────────────────────────────────────────
def _parse_vcard(vcard_array):
    result = {}
    if not vcard_array or len(vcard_array) < 2:
        return result
    for field in vcard_array[1]:
        if len(field) < 4:
            continue
        ftype, val = field[0].lower(), field[3]
        if ftype == "fn" and not result.get("nome"):
            result["nome"] = str(val).strip()
        elif ftype == "email" and not result.get("email"):
            result["email"] = (val[0] if isinstance(val, list) else str(val)).strip().lower()
    return result

def rdap_lookup(domain: str) -> dict:
    """Consulta RDAP do Registro.br. Retorna {email, nome, fonte}."""
    url = f"https://rdap.registro.br/domain/{domain}"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return {}
        data = r.json()
    except Exception:
        return {}

    emails_found, nome_found = [], ""

    for ent in data.get("entities", []):
        info = _parse_vcard(ent.get("vcardArray", []))
        if info.get("email"):
            emails_found.append(info["email"])
        if info.get("nome") and not nome_found:
            nome_found = info["nome"]
        # sub-entities (administrative, technical)
        for sub in ent.get("entities", []):
            sub_info = _parse_vcard(sub.get("vcardArray", []))
            if sub_info.get("email"):
                emails_found.append(sub_info["email"])
            if sub_info.get("nome") and not nome_found:
                nome_found = sub_info["nome"]

    emails_found = filter_emails(emails_found)
    if emails_found:
        return {"email": emails_found[0], "nome": nome_found, "fonte": "registrobr_rdap"}
    return {}


# ── Fonte 2: Scraping do site ─────────────────────────────────────────────────
CONTACT_PATHS = ["/", "/contato", "/contact", "/sobre", "/about",
                 "/fale-conosco", "/atendimento", "/quem-somos"]

def scrape_site(site: str) -> dict:
    """Raspa páginas do site em busca de email. Retorna {email, fonte}."""
    if not site.startswith(("http://", "https://")):
        site = "https://" + site
    base = site.rstrip("/")
    found = []

    for path in CONTACT_PATHS:
        url = base + path if path != "/" else base
        try:
            r = SESSION.get(url, timeout=10, allow_redirects=True)
            if r.status_code != 200:
                continue
            # Filtra só texto (evita binários/JS muito grandes)
            ct = r.headers.get("content-type", "")
            if "text" not in ct and "html" not in ct:
                continue
            emails = EMAIL_RE.findall(r.text)
            found.extend(emails)
            if found:
                break   # achou na primeira página com resultado
        except Exception:
            continue
        time.sleep(0.3)

    found = filter_emails(found)
    if found:
        return {"email": found[0], "fonte": "site_scraping"}
    return {}


# ── Fonte 3: BrasilAPI CNPJ ───────────────────────────────────────────────────
def cnpj_email(cnpj: str) -> dict:
    """Consulta email registrado na Receita Federal via BrasilAPI."""
    if not cnpj:
        return {}
    raw = re.sub(r"\D", "", cnpj)
    if len(raw) != 14:
        return {}
    try:
        r = SESSION.get(f"https://brasilapi.com.br/api/cnpj/v1/{raw}", timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        email = (data.get("email") or "").strip().lower()
        if email and not IGNORE_PAT.search(email):
            return {"email": email, "fonte": "cnpj_receita"}
    except Exception:
        pass
    return {}


# ── Pipeline principal ────────────────────────────────────────────────────────
def main():
    if not LEADS_JSON.exists():
        print("leads_final.json não encontrado. Rode consolidate_v2.py primeiro.")
        sys.exit(1)

    with open(LEADS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    leads  = data.get("leads", [])
    limit  = int(sys.argv[1]) if len(sys.argv) > 1 else len(leads)
    leads  = leads[:limit]

    # Carrega cache existente para não repetir trabalho
    cache = {}
    if OUT.exists():
        with open(OUT, "r", encoding="utf-8") as f:
            for entry in json.load(f):
                cache[entry["id"]] = entry

    results = list(cache.values())
    ids_done = {e["id"] for e in results}

    novos = [l for l in leads if l["id"] not in ids_done]
    print(f"Email lookup: {len(novos)} leads novos | {len(ids_done)} em cache\n")

    for i, lead in enumerate(novos, 1):
        nome = lead.get("nome", "")[:50]
        site = lead.get("site") or ""
        cnpj = lead.get("cnpj") or ""
        domain = clean_domain(site) if site else None

        print(f"  [{i:3d}/{len(novos)}] {nome[:45]:45s}", end=" ", flush=True)

        entry = {"id": lead["id"], "nome": lead.get("nome"), "email": None,
                 "email_fonte": None, "whois_nome": None}

        # 1) RDAP Registro.br
        if domain and is_br_domain(domain):
            rdap = rdap_lookup(domain)
            if rdap.get("email"):
                entry["email"]       = rdap["email"]
                entry["email_fonte"] = rdap["fonte"]
                entry["whois_nome"]  = rdap.get("nome")
                print(f"✓ RDAP   → {entry['email']}")
                results.append(entry)
                time.sleep(0.8)
                continue

        # 2) Scraping do site
        if site and "instagram" not in site and "facebook" not in site and "ifood" not in site:
            scraped = scrape_site(site)
            if scraped.get("email"):
                entry["email"]       = scraped["email"]
                entry["email_fonte"] = scraped["fonte"]
                print(f"✓ Scrape → {entry['email']}")
                results.append(entry)
                time.sleep(0.4)
                continue

        # 3) CNPJ Receita Federal
        if cnpj:
            cf = cnpj_email(cnpj)
            if cf.get("email"):
                entry["email"]       = cf["email"]
                entry["email_fonte"] = cf["fonte"]
                print(f"✓ CNPJ   → {entry['email']}")
                results.append(entry)
                time.sleep(0.5)
                continue

        print("– sem email")
        results.append(entry)
        time.sleep(0.4)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Stats
    com_email = [e for e in results if e.get("email")]
    by_fonte  = {}
    for e in com_email:
        by_fonte[e["email_fonte"]] = by_fonte.get(e["email_fonte"], 0) + 1

    print(f"\n{'='*50}")
    print(f"Emails encontrados: {len(com_email)}/{len(results)} ({100*len(com_email)//max(len(results),1)}%)")
    for fonte, n in sorted(by_fonte.items(), key=lambda x: -x[1]):
        print(f"  {fonte}: {n}")
    print(f"Salvo: {OUT}")

if __name__ == "__main__":
    main()

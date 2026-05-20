#!/usr/bin/env python3
"""
Fase E (CMD-3): valida anuncios REAIS via Playwright (nao WebFetch).
- Meta Ad Library (publica)
- Google Ads Transparency Center (best-effort)

Rate limit: delay entre requests pra evitar bloqueio. Rodar 1x, salva em cache.
"""
import json, os, sys, io, re, time
from urllib.parse import quote

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
BASE = Path(__file__).parent
CSV_IN = BASE / "leads_merged.csv"
LEADS_JSON = BASE / "leads_final.json"
OUT = BASE / "anuncia_validado.json"

from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

def clean_name_for_search(nome):
    """Limpa nome pra busca melhor no Meta/Google Ads."""
    # Tira sufixos comuns + caracteres especiais
    name = re.sub(r'\s*[-—–|/]\s*.*$', '', nome)  # tira "- Centro - BH"
    name = re.sub(r'\s*\(.*?\)', '', name)  # tira "(Matriz)"
    name = re.sub(r'[!.]+$', '', name.strip())  # remove !! e .
    return name.strip()

def check_meta_ads(page, nome):
    """Checa Meta Ad Library. Retorna dict com sim/nao/nao_verificado + count."""
    q = clean_name_for_search(nome)
    url = (f"https://www.facebook.com/ads/library/"
           f"?active_status=active&ad_type=all&country=BR&q={quote(q)}"
           f"&search_type=keyword_unordered&media_type=all")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(3500)  # deixa JS carregar
        content = page.content()
        # Sinais de "nenhum resultado"
        if "0 resultados" in content or "nenhum anúncio" in content.lower() or "no ads found" in content.lower():
            return {"status": "nao", "count": 0, "metodo": "texto_pagina"}
        # Sinais de Cloudflare ou bloqueio
        if "Checking your browser" in content or "cf-challenge" in content.lower():
            return {"status": "nao_verificado", "count": 0, "metodo": "cloudflare"}
        # Conta quantos cards de anuncio aparecem
        # Meta Ad Library mostra cards em grid. Seletor pode mudar.
        # Tenta tambem pegar texto "~ X resultados"
        m = re.search(r'~?\s*(\d+[\.\d]*)\s+resultad', content, re.IGNORECASE)
        if m:
            count = int(m.group(1).replace('.', '').replace(',', ''))
            if count > 0:
                return {"status": "sim", "count": count, "metodo": "contador_pagina"}
            return {"status": "nao", "count": 0, "metodo": "contador_pagina"}
        # Fallback: count de elementos tipo cards
        try:
            cards = page.locator('div[role="article"]').count()
        except:
            cards = 0
        if cards > 0:
            return {"status": "sim", "count": cards, "metodo": "count_cards"}
        return {"status": "nao", "count": 0, "metodo": "fallback"}
    except Exception as e:
        return {"status": "nao_verificado", "count": 0, "metodo": "erro", "erro": str(e)[:120]}

def _extrair_dominio(site: str) -> str | None:
    """Extrai domínio limpo de uma URL de site."""
    if not site:
        return None
    m = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})', site)
    return m.group(1).lower() if m else None


def _gatc_search(page, query: str, by_domain: bool) -> dict:
    """Faz uma busca no Google Ads Transparency Center e retorna resultado."""
    kind = "dominio" if by_domain else "nome"
    if by_domain:
        url = f"https://adstransparency.google.com/?region=BR&domain={quote(query)}"
    else:
        url = f"https://adstransparency.google.com/advertiser?region=BR&q={quote(query)}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Aguarda React/SPA carregar — tenta networkidle, cai para timeout fixo
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(5000)

        content = page.content()
        if "Checking your browser" in content or "cf-challenge" in content.lower():
            return {"status": "nao_verificado", "metodo": "bloqueio"}

        texto = content.lower()

        # Sinais textuais de ausência de resultados
        sem_resultado_patterns = [
            "no results", "sem resultados", "nenhum resultado",
            "no ads found", "no advertisers found",
            "couldn't find any", "não encontramos",
        ]
        if any(p in texto for p in sem_resultado_patterns):
            return {"status": "nao", "count": 0, "metodo": f"texto_{kind}"}

        # Contador textual — ex: "123 anunciantes" ou "45 results"
        m = re.search(r'(\d[\d\.,]*)\s+(?:anunciante|advertiser|result)', texto, re.IGNORECASE)
        if m:
            count = int(re.sub(r"[^\d]", "", m.group(1)))
            if count > 0:
                return {"status": "sim", "count": count, "metodo": f"contador_texto_{kind}"}
            return {"status": "nao", "count": 0, "metodo": f"contador_texto_{kind}"}

        # Seletores CSS atualizados (GATC usa Angular/Shadow DOM + atributos custom)
        selectors = [
            'a[href*="/advertiser/AR"]',           # links de anunciantes (IDs começam com AR)
            'mat-card',                             # Angular Material cards
            '[class*="advertiser-card"]',
            '[class*="AdCard"]',
            'tpc-advertiser-result',               # custom element do GATC
            'div[role="listitem"]',
        ]
        total = 0
        for sel in selectors:
            try:
                n = page.locator(sel).count()
                if n > 0:
                    total = n
                    break
            except Exception:
                continue

        if total > 0:
            return {"status": "sim", "count": total, "metodo": f"cards_{kind}"}

        # Se a página tem conteúdo substancial mas sem sinais claros → nao_verificado
        if len(texto) < 500:
            return {"status": "nao_verificado", "metodo": f"pagina_vazia_{kind}"}

        return {"status": "nao", "count": 0, "metodo": f"texto_sem_resultado_{kind}"}
    except Exception as e:
        return {"status": "nao_verificado", "metodo": "erro", "erro": str(e)[:120]}


def check_google_ads_transparency(page, nome, site=None):
    """Google Ads Transparency Center.
    Tenta por domínio do site primeiro (mais preciso), depois por nome.
    Retorna nao_verificado se bloquear.
    """
    dominio = _extrair_dominio(site)
    if dominio:
        result = _gatc_search(page, dominio, by_domain=True)
        if result["status"] != "nao_verificado":
            return result
        time.sleep(1.0)
    # Fallback: busca por nome
    return _gatc_search(page, clean_name_for_search(nome), by_domain=False)

def main():
    import csv

    # ── Carrega cache existente (para não re-verificar leads já processados) ──
    cache: dict[int, dict] = {}
    if OUT.exists():
        with open(OUT, "r", encoding="utf-8") as fh:
            for r in json.load(fh):
                cache[r["id"]] = r

    # ── Fonte de leads: CSV da rodada (preferência) ou leads_final.json ──
    if CSV_IN.exists():
        leads_raw = []
        with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
            for i, row in enumerate(csv.DictReader(fh), 1):
                if i > 50: break
                leads_raw.append({"id": i, "nome": row["nome"], "site": row.get("site", "")})
    elif LEADS_JSON.exists():
        with open(LEADS_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        leads_raw = [{"id": l["id"], "nome": l.get("nome",""), "site": l.get("site","")} for l in data.get("leads", [])]
    else:
        leads_raw = []

    # CLI: python fase_e_anuncia_real.py 10 -> testa so 10 leads
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(leads_raw)
    leads_raw = leads_raw[:limit]

    # Separa: já verificados (anuncia_google != nao_verificado/None) vs. pendentes
    pendentes = []
    for lead in leads_raw:
        cached = cache.get(lead["id"])
        ja_ok = (cached
                 and cached.get("anuncia_google") in ("sim", "nao")
                 and not cached.get("google_metodo", "").startswith("fallback"))
        if ja_ok:
            pass  # mantém do cache, não refaz
        else:
            pendentes.append(lead)

    pulados = len(leads_raw) - len(pendentes)
    print(f"Validando anúncios REAIS via Playwright")
    print(f"  Total leads : {len(leads_raw)}")
    print(f"  Já verificados (cache): {pulados}")
    print(f"  A processar agora : {len(pendentes)}\n")

    novos: list[dict] = []
    if pendentes:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent=UA,
                locale="pt-BR",
                viewport={"width": 1366, "height": 900},
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US']});
            """)
            page = context.new_page()

            for i, lead in enumerate(pendentes, 1):
                nome = lead["nome"]
                site = lead.get("site") or ""
                print(f"  [{i:2d}/{len(pendentes)}] {nome[:50]:50s}", end=" ", flush=True)
                meta = check_meta_ads(page, nome)
                time.sleep(2.0)
                goog = check_google_ads_transparency(page, nome, site=site)
                time.sleep(1.5)
                row = {
                    "id": lead["id"],
                    "nome": nome,
                    "anuncia_meta": meta["status"],
                    "meta_ads_count": meta.get("count", 0),
                    "meta_metodo": meta["metodo"],
                    "anuncia_google": goog["status"],
                    "google_metodo": goog.get("metodo", ""),
                }
                novos.append(row)
                cache[lead["id"]] = row
                m_tag = meta["status"][:3].upper()
                g_tag = goog["status"][:3].upper()
                extra = f"({meta.get('count',0)})" if meta["status"] == "sim" else ""
                print(f"Meta: {m_tag}{extra:<6} Google: {g_tag}")

            browser.close()

    # Reconstrói lista final (cache completo, ordem original)
    results = []
    for lead in leads_raw:
        if lead["id"] in cache:
            results.append(cache[lead["id"]])

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    # Stats apenas dos novos processados agora
    src = novos if novos else results
    n_meta_sim = sum(1 for r in src if r["anuncia_meta"] == "sim")
    n_meta_nao = sum(1 for r in src if r["anuncia_meta"] == "nao")
    n_meta_nv  = sum(1 for r in src if r["anuncia_meta"] == "nao_verificado")
    n_goog_sim = sum(1 for r in src if r["anuncia_google"] == "sim")
    n_goog_nao = sum(1 for r in src if r["anuncia_google"] == "nao")
    n_goog_nv  = sum(1 for r in src if r["anuncia_google"] == "nao_verificado")
    print(f"\n==========")
    print(f"META:   sim={n_meta_sim} | nao={n_meta_nao} | nao_verificado={n_meta_nv}")
    print(f"GOOGLE: sim={n_goog_sim} | nao={n_goog_nao} | nao_verificado={n_goog_nv}")
    print(f"Salvo : {OUT} ({len(results)} leads no cache)")

if __name__ == "__main__":
    main()

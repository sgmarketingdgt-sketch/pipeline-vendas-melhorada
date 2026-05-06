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

def check_google_ads_transparency(page, nome):
    """Google Ads Transparency Center. Se bloquear, retorna nao_verificado."""
    q = clean_name_for_search(nome)
    url = f"https://adstransparency.google.com/?region=BR&domain=&authuser=0"  # homepage
    # O GATC nao tem URL direta de busca na homepage. Vou buscar via input.
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2000)
        # Tenta achar campo de busca e digitar
        search_url = f"https://adstransparency.google.com/advertiser?region=BR&domain=&q={quote(q)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)
        content = page.content()
        if "Checking your browser" in content or "sorry" in content.lower()[:200]:
            return {"status": "nao_verificado", "metodo": "bloqueio"}
        # Google mostra "No results" se nao achou
        if "no results" in content.lower() or "sem resultados" in content.lower() or "nao encontramos" in content.lower():
            return {"status": "nao", "metodo": "texto"}
        # Se mostra cards de anunciante, marca sim
        try:
            n = page.locator('a[href*="/advertiser/"]').count()
        except:
            n = 0
        if n > 0:
            return {"status": "sim", "count": n, "metodo": "links_anunciantes"}
        return {"status": "nao", "count": 0, "metodo": "fallback"}
    except Exception as e:
        return {"status": "nao_verificado", "metodo": "erro", "erro": str(e)[:120]}

def main():
    import csv
    # Sempre prefere leads_merged.csv (rodada atual); leads_final.json pode ter outro segmento
    if CSV_IN.exists():
        leads = []
        with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
            for i, row in enumerate(csv.DictReader(fh), 1):
                if i > 50: break
                leads.append({"id": i, "nome": row["nome"]})
    elif LEADS_JSON.exists():
        with open(LEADS_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        leads = data["leads"]
    else:
        leads = []
    # CLI: python fase_e_anuncia_real.py 10 -> testa so 10 leads
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(leads)
    leads = leads[:limit]
    print(f"Validando anuncios REAIS de {len(leads)} leads via Playwright (modo {'TESTE' if limit < 50 else 'COMPLETO'})...\n")

    results = []
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
        # anti-detect basico
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US']});
        """)
        page = context.new_page()

        for i, lead in enumerate(leads, 1):
            nome = lead["nome"]
            print(f"  [{i:2d}/{len(leads)}] {nome[:55]:55s}", end=" ", flush=True)
            meta = check_meta_ads(page, nome)
            time.sleep(2.0)  # anti-detect
            goog = check_google_ads_transparency(page, nome)
            time.sleep(1.5)
            results.append({
                "id": lead["id"],
                "nome": nome,
                "anuncia_meta": meta["status"],
                "meta_ads_count": meta.get("count", 0),
                "meta_metodo": meta["metodo"],
                "anuncia_google": goog["status"],
                "google_metodo": goog.get("metodo", ""),
            })
            m = meta["status"][:3].upper()
            g = goog["status"][:3].upper()
            extra = f"({meta.get('count', 0)})" if meta["status"] == "sim" else ""
            print(f"Meta: {m}{extra:<6} Google: {g}")

        browser.close()

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    # Stats
    n_meta_sim = sum(1 for r in results if r["anuncia_meta"] == "sim")
    n_meta_nao = sum(1 for r in results if r["anuncia_meta"] == "nao")
    n_meta_nv = sum(1 for r in results if r["anuncia_meta"] == "nao_verificado")
    n_goog_sim = sum(1 for r in results if r["anuncia_google"] == "sim")
    n_goog_nao = sum(1 for r in results if r["anuncia_google"] == "nao")
    n_goog_nv = sum(1 for r in results if r["anuncia_google"] == "nao_verificado")
    print(f"\n==========")
    print(f"META: sim={n_meta_sim} | nao={n_meta_nao} | nao_verificado={n_meta_nv}")
    print(f"GOOGLE: sim={n_goog_sim} | nao={n_goog_nao} | nao_verificado={n_goog_nv}")
    print(f"Salvo: {OUT}")

if __name__ == "__main__":
    main()

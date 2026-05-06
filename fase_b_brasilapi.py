#!/usr/bin/env python3
"""
Fase B: Enriquece CNPJs encontrados via BrasilAPI.
Puxa: razao social, socios (QSA), data abertura, capital social, porte, atividade.
Output: cnpj_enriquecidos.json
"""
import json, os, sys, io, time, re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
BASE = Path(__file__).parent
IN = BASE / "cnpj_encontrados.json"
OUT = BASE / "cnpj_enriquecidos.json"

with open(IN, "r", encoding="utf-8") as fh:
    leads = json.load(fh)

com_cnpj = [l for l in leads if l.get("cnpj")]
print(f"CNPJs pra consultar BrasilAPI: {len(com_cnpj)}")

def consultar_brasilapi(cnpj_obj):
    cnpj_limpo = re.sub(r"\D", "", cnpj_obj["cnpj"])
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            return {
                "id": cnpj_obj["id"],
                "nome": cnpj_obj["nome"],
                "cnpj": cnpj_obj["cnpj"],
                "brasilapi_ok": True,
                "razao_social": data.get("razao_social"),
                "nome_fantasia": data.get("nome_fantasia"),
                "data_inicio_atividade": data.get("data_inicio_atividade"),
                "capital_social": data.get("capital_social"),
                "porte": data.get("porte") or data.get("descricao_porte"),
                "cnae_principal": data.get("cnae_fiscal_descricao"),
                "situacao": data.get("descricao_situacao_cadastral"),
                "municipio": data.get("municipio"),
                "uf": data.get("uf"),
                "bairro": data.get("bairro"),
                "qsa": [
                    {
                        "nome": s.get("nome_socio"),
                        "qualificacao": s.get("qualificacao_socio"),
                        "data_entrada": s.get("data_entrada_sociedade"),
                    }
                    for s in (data.get("qsa") or [])
                ],
            }
        else:
            return {"id": cnpj_obj["id"], "nome": cnpj_obj["nome"], "cnpj": cnpj_obj["cnpj"],
                    "brasilapi_ok": False, "erro": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"id": cnpj_obj["id"], "nome": cnpj_obj["nome"], "cnpj": cnpj_obj["cnpj"],
                "brasilapi_ok": False, "erro": str(e)}

print(f"Consultando BrasilAPI (5 threads, respeitando rate limit)...")
results = []
start = time.time()

# Dedupe por CNPJ (alguns leads compartilham CNPJ)
vistos = {}
for c in com_cnpj:
    if c["cnpj"] not in vistos:
        vistos[c["cnpj"]] = c

unicos = list(vistos.values())
print(f"CNPJs unicos a consultar: {len(unicos)}")

# Rate limit: 3 req/s max
with ThreadPoolExecutor(max_workers=3) as ex:
    futures = {ex.submit(consultar_brasilapi, c): c for c in unicos}
    for fut in as_completed(futures):
        r = fut.result()
        results.append(r)
        if r.get("brasilapi_ok"):
            socios = ", ".join([s["nome"] for s in r.get("qsa") or []][:2]) or "—"
            print(f"  [OK] {r['nome'][:40]:40s} | {r.get('razao_social', '—')[:30]:30s} | socios: {socios}")
        else:
            print(f"  [ER] {r['nome'][:40]:40s} | {r.get('erro')}")
        time.sleep(0.3)

# Duplicar dados pra leads que compartilham CNPJ
por_cnpj = {r["cnpj"]: r for r in results}
todos_enriquecidos = []
for lead in com_cnpj:
    base = por_cnpj.get(lead["cnpj"], {})
    todos_enriquecidos.append({**lead, **base})

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(todos_enriquecidos, fh, ensure_ascii=False, indent=2)

elapsed = time.time() - start
ok = sum(1 for r in results if r.get("brasilapi_ok"))
print(f"\n==========")
print(f"Tempo: {elapsed:.1f}s")
print(f"BrasilAPI ok: {ok}/{len(results)} CNPJs unicos")
print(f"Leads enriquecidos: {len(todos_enriquecidos)}")
print(f"Salvo: {OUT}")

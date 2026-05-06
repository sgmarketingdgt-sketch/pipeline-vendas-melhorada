#!/usr/bin/env python3
"""
Gera lotes_v2 pra Fase C (rapport humano real).
Merge: base CSV + CNPJ da Fase A + dados BrasilAPI da Fase B + enriched v1 (como hint).
"""
import csv, json, os, sys, io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
BASE = Path(__file__).parent
CSV_IN = BASE / "leads_merged.csv"
CNPJ_JSON = BASE / "cnpj_enriquecidos.json"
ENRICHED_V1_DIR = BASE / "lotes"
OUT_DIR = BASE / "lotes_v2"
OUT_DIR.mkdir(exist_ok=True)

# Base
leads = []
with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
    for i, row in enumerate(csv.DictReader(fh), 1):
        row["id"] = i
        leads.append(row)
leads = leads[:50]

# CNPJ enriquecido (pode ter vazio)
cnpj_by_id = {}
if os.path.exists(CNPJ_JSON):
    with open(CNPJ_JSON, "r", encoding="utf-8") as fh:
        for c in json.load(fh):
            cnpj_by_id[c["id"]] = c

# Enriched v1 (pra reuso de Instagram handle/site_gap que o subagent v1 ja encontrou)
enriched_v1_by_id = {}
for i in range(1, 6):
    p = os.path.join(ENRICHED_V1_DIR, f"enriched_{i}.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            for item in json.load(fh):
                enriched_v1_by_id[item["id"]] = item

# Monta lead completo
enriched = []
for lead in leads:
    lid = lead["id"]
    cnpj_data = cnpj_by_id.get(lid, {})
    v1 = enriched_v1_by_id.get(lid, {})

    socios = []
    if cnpj_data.get("qsa"):
        socios = [s["nome"] for s in cnpj_data["qsa"]][:3]
    elif cnpj_data.get("brasilapi_ok") is False:
        socios = []

    enriched.append({
        "id": lid,
        "nome": lead["nome"],
        "telefone": lead.get("telefone", ""),
        "whatsapp": lead.get("whatsapp", ""),
        "nota_maps": lead.get("nota"),
        "avaliacoes_maps": lead.get("avaliacoes"),
        "recencia_review_dias": lead.get("recencia_dias"),
        "categoria_maps": lead.get("categoria"),
        "site": lead.get("site", ""),
        "endereco": lead.get("endereco", ""),
        "maps_url": lead.get("maps", ""),
        # Ja temos do BrasilAPI:
        "cnpj": cnpj_data.get("cnpj"),
        "razao_social": cnpj_data.get("razao_social"),
        "nome_fantasia": cnpj_data.get("nome_fantasia"),
        "data_abertura": cnpj_data.get("data_inicio_atividade"),
        "capital_social": cnpj_data.get("capital_social"),
        "porte_receita": cnpj_data.get("porte"),
        "cnae_principal": cnpj_data.get("cnae_principal"),
        "socios_cnpj": socios,
        # Hints da v1 (nao confiaveis, so dica):
        "v1_instagram_handle": v1.get("instagram_handle") if v1.get("instagram_handle") not in {"nao_encontrado", "@...", ""} else None,
        "v1_instagram_url": v1.get("instagram_url") if v1.get("instagram_url") and v1.get("instagram_url") != "nao_encontrado" else None,
        "v1_proposta_valor": v1.get("proposta_valor"),
        "v1_site_gap": v1.get("site_gap"),
    })

# Divide em 5 lotes de 10
for i in range(5):
    lote = enriched[i*10:(i+1)*10]
    with open(os.path.join(OUT_DIR, f"lote_v2_{i+1}.json"), "w", encoding="utf-8") as fh:
        json.dump(lote, fh, ensure_ascii=False, indent=2)
    com_cnpj = sum(1 for l in lote if l.get("cnpj"))
    com_dono = sum(1 for l in lote if l.get("socios_cnpj"))
    print(f"Lote v2 {i+1}: 10 leads | {com_cnpj} com CNPJ | {com_dono} com socios")

total_cnpj = sum(1 for l in enriched if l.get("cnpj"))
total_donos = sum(1 for l in enriched if l.get("socios_cnpj"))
print(f"\nTOTAIS: {total_cnpj}/50 com CNPJ | {total_donos}/50 com socios identificados")

#!/usr/bin/env python3
"""
merge_aviacao.py
================
Merge + dedup dos CSVs do extrator para prospecção de Escolas de Aviação no Brasil.
Mantém o mesmo contrato de saída que merge.py → leads_merged.csv

Diferenças em relação ao merge.py (hamburguerias):
  - Sem filtro SP-only (escolas são nacionais)
  - Sem filtro de DDD paulista
  - NICHE_TERMS e CAT_TERMS voltados para aviação
  - Aceita escolas sem celular se tiverem site (lead de alto ticket)
"""
import csv, glob, os, re, sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
SRC  = BASE / "prospects"
OUT_CSV = BASE / "leads_merged.csv"

# Só lê CSVs que vieram de queries de aviação (pelo segmento no CSV)
# — ou seja, CSVs onde a primeira linha de dados tem segmento="Escola de Aviação"
# Se quiser forçar: passe --all para usar todos os CSVs
import sys
force_all = "--all" in sys.argv

files = sorted(f for f in SRC.glob("*.csv") if "_agente" not in f.name)

# Filtra apenas arquivos de aviação (detecta pelo campo segmento no CSV)
aviacao_files = []
for f in files:
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            row = next(reader, None)
            if row and "aviação" in (row.get("segmento") or "").lower():
                aviacao_files.append(f)
            elif force_all:
                aviacao_files.append(f)
    except Exception:
        pass

if not aviacao_files:
    print("[aviso] Nenhum CSV com segmento='Escola de Aviação' encontrado em prospects/")
    print("        Rode o extrator com SEGMENTO='Escola de Aviação' no .env primeiro.")
    print("        Ou use --all para processar todos os CSVs.")
    sys.exit(0)

print(f"Lendo {len(aviacao_files)} CSVs de aviação:")
for f in aviacao_files:
    print(f"  {f.name}")

all_rows   = []
seen_phone = set()
seen_name  = set()
dup_count  = 0

for f in aviacao_files:
    origem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", f.stem)
    with open(f, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            phone    = (row.get("whatsapp") or "").strip()
            name_key = (row.get("nome")     or "").strip().lower()
            if phone    and phone    in seen_phone: dup_count += 1; continue
            if name_key and name_key in seen_name:  dup_count += 1; continue
            if phone:    seen_phone.add(phone)
            if name_key: seen_name.add(name_key)
            row["query_origem"] = origem
            all_rows.append(row)

print(f"\nTotal únicos: {len(all_rows)} (duplicados removidos: {dup_count})")

# ── Termos de nicho para aviação ──────────────────────────────────────────────
NICHE_TERMS = [
    "aviação", "aviacao", "piloto", "pilotos", "voo", "voos",
    "aeroclube", "aeroclub", "aeronáutica", "aeronautica",
    "flight", "sky", "air", "aero",
    "ppla", "ppl", "cpa", "atpl", "brevet",
    "instrução de voo", "instrucao de voo",
    "escola de voo",
]

CAT_TERMS = [
    "school", "flight", "aviation", "training",
    "establishment", "airport", "point_of_interest",
]

BLACKLIST_TERMS = [
    "táxi", "taxi", "transporte", "seguro", "segurança",
    "medicina", "clínica", "clinica",
    "supermercado", "mercado", "padaria",
]


def is_valid(row):
    nome = (row.get("nome")      or "").lower()
    cat  = (row.get("categoria") or "").lower()

    for term in BLACKLIST_TERMS:
        if term in nome:
            return False

    niche_ok = any(t in nome for t in NICHE_TERMS)
    cat_ok   = any(t in cat  for t in CAT_TERMS)
    return niche_ok or cat_ok


# Aceita leads com celular OU com site (aviação é alto ticket, site é sinal forte)
candidatos = [
    r for r in all_rows
    if (r.get("celular") or "").strip().lower() == "sim"
    or (r.get("site")    or "").strip()
]
filtrados = [r for r in candidatos if is_valid(r)]
print(f"Após filtro de nicho: {len(filtrados)}")

if not filtrados:
    print("\nNenhum lead passou o filtro. Revise os termos de nicho ou adicione mais queries.")
    sys.exit(0)


def rank_key(row):
    try:   score = float(row.get("score") or 0)
    except Exception: score = 0
    try:   nrl   = float(row.get("nrl")   or 10)
    except Exception: nrl   = 10
    try:   avals = int(row.get("avaliacoes") or 0)
    except Exception: avals = 0
    return (-score, nrl, -avals)


filtrados.sort(key=rank_key)
selecionados = filtrados[:50]

fieldnames = list(selecionados[0].keys())
with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(selecionados)

print(f"\nCSV merged salvo: {OUT_CSV}")
print(f"Selecionados (top {len(selecionados)} de {len(filtrados)}):")
for i, r in enumerate(selecionados[:60], 1):
    cidade = (r.get("endereco") or "")[-30:]
    score  = r.get("score", "")
    print(f"  {i:2d}. {r['nome'][:50]:50s} | score {score:>3} | {cidade}")

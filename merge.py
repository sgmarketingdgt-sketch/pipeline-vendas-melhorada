#!/usr/bin/env python3
"""Merge + dedup dos CSVs do extrator para prospecção de hamburguerias em SP."""
import csv, glob, os, re, sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
SRC = BASE / "prospects"
OUT_CSV = BASE / "leads_merged.csv"

files = sorted(f for f in SRC.glob("*.csv") if "_agente" not in f.name)
print(f"Lendo {len(files)} CSVs:")
for f in files:
    print(f"  {f.name}")

all_rows = []
seen_phone = set()
seen_name = set()
dup_count = 0

for f in files:
    origem = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", f.stem)
    with open(f, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            phone = (row.get("whatsapp") or "").strip()
            name_key = (row.get("nome") or "").strip().lower()
            if phone and phone in seen_phone:
                dup_count += 1
                continue
            if name_key and name_key in seen_name:
                dup_count += 1
                continue
            if phone:
                seen_phone.add(phone)
            if name_key:
                seen_name.add(name_key)
            row["query_origem"] = origem
            all_rows.append(row)

print(f"\nTotal únicos: {len(all_rows)} (duplicados removidos: {dup_count})")

eh_celular = [r for r in all_rows if (r.get("celular") or "").strip().lower() == "sim"]
com_site = [r for r in all_rows if (r.get("site") or "").strip()]
print(f"Celular (WhatsApp provável): {len(eh_celular)}")
print(f"Com site: {len(com_site)}")

BLACKLIST_TERMS = [
    "repartição pública", "repartição publica",
    "receita federal", "prefeitura",
    "tabelionato", "cartório", "cartorio",
    "supermercado", "mercado", "padaria",
    "pizzaria", "sushi", "japonesa", "italiana",
]

NICHE_TERMS = [
    "burger", "burguer", "hamburguer", "hamburgueria", "hamburgeria",
    "smash", "artesanal", "lanche", "lanches", "lanchonete",
    "gourmet", "dog", "sanduba", "sanduíche", "sanduiche",
]

SP_DDDS = {"11", "12", "13", "14", "15", "17", "18", "19"}


def is_valid(row):
    nome = (row.get("nome") or "").lower()
    cat = (row.get("categoria") or "").lower()
    endereco = (row.get("endereco") or "").upper()
    telefone = row.get("telefone") or ""
    for term in BLACKLIST_TERMS:
        if term in nome or term in cat:
            return False
    if " SP" not in endereco and "SÃO PAULO" not in endereco and "SAO PAULO" not in endereco:
        return False
    ddd_match = re.search(r"\((\d{2})\)", telefone)
    if ddd_match and ddd_match.group(1) not in SP_DDDS:
        return False
    # aceita se o nome bate com nicho OU se a categoria Maps é de alimentação
    niche_ok = any(t in nome for t in NICHE_TERMS)
    cat_ok = any(t in cat for t in ["burger", "hamburguer", "sandwich", "fast food", "meal takeaway", "restaurant"])
    return niche_ok or cat_ok


candidatos = [r for r in all_rows if (r.get("celular") or "").strip().lower() == "sim" or (r.get("site") or "").strip()]
filtrados = [r for r in candidatos if is_valid(r)]
print(f"Após filtro de nicho: {len(filtrados)}")


def rank_key(row):
    try:
        score = float(row.get("score") or 0)
    except Exception:
        score = 0
    try:
        nrl = float(row.get("nrl") or 10)
    except Exception:
        nrl = 10
    try:
        avals = int(row.get("avaliacoes") or 0)
    except Exception:
        avals = 0
    return (-score, nrl, -avals)


filtrados.sort(key=rank_key)
selecionados = filtrados[:50]

if selecionados:
    fieldnames = list(selecionados[0].keys())
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selecionados)
    print(f"\nCSV merged salvo: {OUT_CSV}")
    print(f"Selecionados (top {len(selecionados)} de {len(filtrados)}):")
    for i, r in enumerate(selecionados[:60], 1):
        score = r.get("score", "")
        nrl = r.get("nrl", "")
        wa = r.get("whatsapp", "") or r.get("celular", "")
        print(f"  {i:2d}. {r['nome'][:55]:55s} | score {score:>3} | NRL {nrl:>4} | {wa}")
else:
    print("\nNenhum lead passou o filtro. Rode mais queries no extrator.")

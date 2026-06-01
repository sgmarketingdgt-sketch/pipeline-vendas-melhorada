#!/usr/bin/env python3
"""Merge + dedup dos CSVs do extrator para prospecção local (qualquer nicho SP).
Filtra automaticamente os CSVs pelo SEGMENTO definido no .env."""
import csv, glob, os, re, sys, io
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
SRC = BASE / "prospects"
OUT_CSV = BASE / "leads_merged.csv"

SEGMENTO_ENV = os.getenv("SEGMENTO", "").strip().strip('"').strip("'").lower()

all_files = sorted(f for f in SRC.glob("*.csv") if "_agente" not in f.name)

# Filtra apenas CSVs do segmento atual (detecta pelo campo segmento na 1ª linha)
files = []
for f in all_files:
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            row = next(csv.DictReader(fh), None)
            seg = (row.get("segmento") or "").strip().strip('"').strip("'").lower()
            if not SEGMENTO_ENV or SEGMENTO_ENV in seg or seg in SEGMENTO_ENV:
                files.append(f)
    except Exception:
        pass

if not files:
    print(f"[aviso] Nenhum CSV com segmento='{SEGMENTO_ENV}' encontrado em prospects/")
    print("        Rode o extrator primeiro ou verifique o SEGMENTO no .env.")
    sys.exit(0)

print(f"Segmento: {SEGMENTO_ENV or '(todos)'} — {len(files)} CSVs encontrados:")
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
    # Falsos positivos para segurança do trabalho:
    "venda de epi", "equipamentos epi", "locação",
    "medicina do trabalho", "clínica", "clinica",
    "engenharia", "consultoria ambiental",
    "dedetização", "dedetizacao",
]

NICHE_TERMS = [
    # Segurança do trabalho — NRs e termos gerais
    "nr10", "nr35", "nr33", "nr12", "nr6", "nr20", "nr23", "nr18",
    "segurança do trabalho", "seguranca do trabalho",
    "treinamento nr", "curso nr", "capacitação nr", "capacitacao nr",
    "trabalho em altura", "espaço confinado", "espaco confinado",
    "elétrica segurança", "eletrica seguranca",
    "brigada de incêndio", "brigada de incendio",
    "cipa", "cipaatr", "nr-10", "nr-35", "nr-33",
    "higiene ocupacional", "ssma", "sesmt",
    "segurança ocupacional", "seguranca ocupacional",
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
    # Filtro geográfico SP (sempre aplicado, independente do segmento)
    if " SP" not in endereco and "SÃO PAULO" not in endereco and "SAO PAULO" not in endereco:
        return False
    ddd_match = re.search(r"\((\d{2})\)", telefone)
    if ddd_match and ddd_match.group(1) not in SP_DDDS:
        return False
    # Filtro de nicho: segmento do CSV bate com .env → aceita
    seg_row = (row.get("segmento") or "").strip().strip('"').strip("'").lower()
    if SEGMENTO_ENV and seg_row and (SEGMENTO_ENV in seg_row or seg_row in SEGMENTO_ENV):
        return True
    # Fallback: verifica NICHE_TERMS
    niche_ok = any(t in nome for t in NICHE_TERMS)
    cat_ok   = any(t in cat  for t in NICHE_TERMS)
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

if not selecionados:
    print("\n⚠️  Nenhum lead passou o filtro.")
    print("   Verifique o SEGMENTO no .env e rode mais queries no extrator.")
    # Apaga CSV antigo para evitar que fases seguintes processem dados de outra rodada
    if OUT_CSV.exists():
        OUT_CSV.unlink()
        print("   leads_merged.csv antigo removido para evitar contaminação.")
    import sys; sys.exit(1)

if selecionados:
    # União de todas as colunas presentes (CSVs de rodadas diferentes podem ter colunas distintas)
    all_keys = list(dict.fromkeys(k for row in selecionados for k in row.keys()))
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
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

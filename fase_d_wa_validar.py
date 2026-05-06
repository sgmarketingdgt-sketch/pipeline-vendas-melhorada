#!/usr/bin/env python3
"""
Fase D: valida se os 50 numeros dos leads tem WhatsApp via Evolution API (HTTP direto).
Output: wa_validado.json
"""
import csv, json, os, sys, io, re, time
import requests
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
CSV_IN = BASE / "leads_merged.csv"
OUT    = BASE / "wa_validado.json"

load_dotenv(BASE / ".env")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/").replace("/manager", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")

if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE:
    print("[ERRO] Variaveis EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE nao encontradas no .env")
    sys.exit(1)

print(f"Evolution API: {EVOLUTION_API_URL}")
print(f"Instancia: {EVOLUTION_INSTANCE}")

# Extrai numeros E.164 unicos dos 50 leads
numeros = []
seen = set()
with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
    for i, row in enumerate(csv.DictReader(fh), 1):
        if i > 50: break
        wa = re.sub(r"\D", "", row.get("whatsapp") or "")
        if not wa:
            wa = re.sub(r"\D", "", row.get("telefone") or "")
            if wa and not wa.startswith("55"):
                wa = "55" + wa
        if wa and wa not in seen:
            seen.add(wa)
            numeros.append({"id": i, "nome": row["nome"], "numero": wa})
        elif not wa:
            numeros.append({"id": i, "nome": row["nome"], "numero": None})

print(f"\nValidando {len([n for n in numeros if n['numero']])} numeros via Evolution API...")

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}

instance_slug = EVOLUTION_INSTANCE.replace(" ", "%20")

def check_whatsapp_batch(numbers: list) -> dict:
    """Checa lista de numeros. Retorna dict {numero: {exists, jid, name}}."""
    url = f"{EVOLUTION_API_URL}/chat/whatsappNumbers/{instance_slug}"
    payload = {"numbers": numbers}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return {item.get("number", item.get("jid","").split("@")[0]): item for item in data}
            elif isinstance(data, dict):
                return data
        else:
            print(f"  [AVISO] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  [ERRO] {e}")
    return {}

# Processa em batches de 10
BATCH = 10
resultado = []
nums_com_numero = [n for n in numeros if n["numero"]]
nums_sem_numero = [n for n in numeros if not n["numero"]]

resp_map = {}
for i in range(0, len(nums_com_numero), BATCH):
    batch = nums_com_numero[i:i+BATCH]
    batch_nums = [n["numero"] for n in batch]
    print(f"  Batch {i//BATCH + 1}: {batch_nums[:3]}...")
    resp = check_whatsapp_batch(batch_nums)
    resp_map.update(resp)
    time.sleep(1)  # respeita rate limit

# Cruza com leads
for n in numeros:
    if not n["numero"]:
        resultado.append({
            "id": n["id"],
            "nome": n["nome"],
            "numero": None,
            "wa_ativo": False,
            "wa_jid": None,
            "wa_name": None,
        })
        continue

    item = resp_map.get(n["numero"], {})
    # Evolution API retorna "exists" ou campo booleano
    exists = item.get("exists", False)
    if not isinstance(exists, bool):
        exists = bool(exists)
    jid = item.get("jid") or item.get("wuid") or None
    name = item.get("name") or item.get("pushName") or None

    resultado.append({
        "id": n["id"],
        "nome": n["nome"],
        "numero": n["numero"],
        "wa_ativo": exists,
        "wa_jid": jid,
        "wa_name": name,
    })

# Garante que todos os 50 leads estão no resultado (mesmo sem numero)
ids_presentes = {r["id"] for r in resultado}
with open(CSV_IN, "r", encoding="utf-8-sig") as fh:
    for i, row in enumerate(csv.DictReader(fh), 1):
        if i > 50: break
        if i not in ids_presentes:
            resultado.append({
                "id": i,
                "nome": row["nome"],
                "numero": None,
                "wa_ativo": False,
                "wa_jid": None,
                "wa_name": None,
            })

resultado.sort(key=lambda x: x["id"])

# Stats
ativos = sum(1 for r in resultado if r["wa_ativo"])
print(f"\n==========")
print(f"WhatsApp ATIVO:   {ativos}/{len(resultado)}")
print(f"WhatsApp INATIVO: {len(resultado) - ativos}")

print("\nAtivos:")
for r in resultado:
    if r["wa_ativo"]:
        name = f' | "{r["wa_name"]}"' if r["wa_name"] else ""
        print(f"  [OK] {r['nome'][:45]:45s} | {r['numero']}{name}")

print("\nInativos:")
for r in resultado:
    if not r["wa_ativo"]:
        num = r["numero"] or "sem numero"
        print(f"  [--] {r['nome'][:45]:45s} | {num}")

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(resultado, fh, ensure_ascii=False, indent=2)
print(f"\nSalvo: {OUT}")

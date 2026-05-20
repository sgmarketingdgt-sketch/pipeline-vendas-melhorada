#!/usr/bin/env python3
"""
extrator.py — wrapper Google Places Text Search v1 (Places API New).
Uso: python extrator.py "hamburguerias São Paulo"
Saída: prospects/YYYY-MM-DD_hamburguerias_sao_paulo.csv
"""
import csv, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
PROSPECTS_DIR = BASE / "prospects"
PROSPECTS_DIR.mkdir(exist_ok=True)

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.displayName,places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.formattedAddress,places.types,places.rating,"
    "places.userRatingCount,places.googleMapsUri,places.photos,places.reviews,"
    "places.socialMediaLinks,"   # Instagram, Facebook etc. do perfil do Maps
    "nextPageToken"
)


def slugify(text):
    for src, dst in [("àáâãä","a"),("èéêë","e"),("ìíîï","i"),("òóôõö","o"),("ùúûü","u"),("ç","c")]:
        for c in src:
            text = text.replace(c, dst)
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def is_celular(intl_phone):
    if not intl_phone:
        return False
    digits = re.sub(r"\D", "", intl_phone)
    return digits.startswith("55") and len(digits) >= 12 and digits[4] == "9"


def recencia_dias(reviews):
    if not reviews:
        return ""
    now = datetime.now(timezone.utc)
    mais_recente = None
    for r in reviews:
        pub = r.get("publishTime")
        if not pub:
            continue
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if mais_recente is None or dt > mais_recente:
                mais_recente = dt
        except Exception:
            continue
    return (now - mais_recente).days if mais_recente else ""


def nrl_recente(reviews):
    """Rating do review mais recente — proxy de reputação recente."""
    if not reviews:
        return ""
    with_time = [r for r in reviews if r.get("publishTime")]
    if not with_time:
        return ""
    latest = max(with_time, key=lambda r: r["publishTime"])
    return latest.get("rating", "")


def fetch_places(query, max_results=60):
    if not API_KEY:
        print("[erro] GOOGLE_PLACES_API_KEY não configurada no .env")
        sys.exit(1)

    all_places = []
    page_token = None

    while len(all_places) < max_results:
        body = {
            "textQuery": query,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "maxResultCount": 20,
        }
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(
            ENDPOINT,
            headers={
                "X-Goog-Api-Key": API_KEY,
                "X-Goog-FieldMask": FIELD_MASK,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[erro] HTTP {resp.status_code}: {resp.text[:300]}")
            break

        data = resp.json()
        places = data.get("places", [])
        all_places.extend(places)
        print(f"  página: {len(places)} resultados (total até agora: {len(all_places)})")

        page_token = data.get("nextPageToken")
        if not page_token or not places:
            break
        time.sleep(0.5)

    return all_places


def place_to_row(p):
    intl = p.get("internationalPhoneNumber", "")
    reviews = p.get("reviews", [])
    segmento = os.getenv("SEGMENTO", "Geral").strip().strip('"').strip("'")
    # Extrai Instagram (e Facebook) do campo socialMediaLinks do Maps
    social = p.get("socialMediaLinks") or []
    instagram_maps = next((s.get("uri", "") for s in social if "instagram.com" in s.get("uri", "")), "")
    facebook_maps  = next((s.get("uri", "") for s in social if "facebook.com"  in s.get("uri", "")), "")
    return {
        "nome": p.get("displayName", {}).get("text", ""),
        "telefone": p.get("nationalPhoneNumber", ""),
        "whatsapp": re.sub(r"\D", "", intl) if intl else "",
        "celular": "Sim" if is_celular(intl) else "Nao",
        "site": p.get("websiteUri", ""),
        "endereco": p.get("formattedAddress", ""),
        "categoria": (p.get("types") or [""])[0].replace("_", " "),
        "score": p.get("rating", ""),
        "avaliacoes": p.get("userRatingCount", ""),
        "maps": p.get("googleMapsUri", ""),
        "fotos": len(p.get("photos", [])),
        "nrl": nrl_recente(reviews),
        "recencia_dias": recencia_dias(reviews),
        "segmento": segmento,
        "instagram_maps": instagram_maps,
        "facebook_maps":  facebook_maps,
    }


def main():
    if len(sys.argv) < 2:
        print('Uso: python extrator.py "hamburguerias São Paulo"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Buscando: {query}")

    places = fetch_places(query)
    if not places:
        print("Nenhum resultado.")
        return

    rows = [place_to_row(p) for p in places]
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = PROSPECTS_DIR / f"{today}_{slugify(query)}.csv"

    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Salvos {len(rows)} resultados → {out_path}")


if __name__ == "__main__":
    main()

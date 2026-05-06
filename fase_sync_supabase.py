"""
fase_sync_supabase.py
=====================

Fase 08a do pipeline (rodar depois do consolidate_v2.py).

Sincroniza `leads_final.json` com o Supabase do usuário em modo
incremental. Garantias:

- Lead novo (não existe no Supabase) entra com `first_seen_at = now()`
  e `novo_nesta_rodada = true`.
- Lead existente recebe APENAS atualização de campos voláteis
  (sinais Maps, contagem Meta Ads, último visto). Status, notas,
  atividade, rapport e gancho NUNCA são sobrescritos.
- Cada execução registra histórico em `execucoes`.

Critérios de match (em ordem):
  1. CNPJ + agencia
  2. WhatsApp + agencia (apenas se ambos os lados não têm CNPJ)
  3. Nome normalizado + agencia (último recurso)

Uso:
    python fase_sync_supabase.py
    python fase_sync_supabase.py --dry-run     # simula sem escrever
    python fase_sync_supabase.py --input outro.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[erro] python-dotenv não instalado. Rode: pip install python-dotenv")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[erro] requests não instalado. Rode: pip install requests")
    sys.exit(1)


BASE = Path(__file__).parent
DEFAULT_INPUT = BASE / "leads_final.json"

# Campos atualizados em re-execuções (voláteis: refletem realidade externa)
CAMPOS_VOLATEIS = {
    "maps_nota",
    "maps_avaliacoes",
    "maps_fotos",
    "maps_recencia_dias",
    "maps_nrl",
    "anuncia_meta",
    "anuncia_google",
    "meta_ads_count",
    "whatsapp_ativo",
    "site",
    "telefone",
    "endereco_completo",
}

# Campos que NUNCA são tocados em re-execuções (trabalho do operador)
CAMPOS_PROTEGIDOS = {
    "status",
    "notes",
    "activity",
    "rapport_humano",
    "gancho_dor",
    "first_seen_at",
}


def normalizar_nome(nome: str) -> str:
    """Normaliza nome para match por similaridade."""
    if not nome:
        return ""
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Remove ruído comum em nomes de empresa
    for ruido in ("ltda", "me", "epp", "eireli", "cia", "s a", "sa"):
        s = re.sub(rf"\b{ruido}\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def carregar_env() -> dict:
    env_path = BASE / ".env"
    if not env_path.exists():
        print(f"[erro] .env não encontrado em {env_path}")
        sys.exit(1)
    load_dotenv(env_path)

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or ""
    ).strip()
    agencia = os.getenv("AGENCIA", "").strip()
    segmento = os.getenv("SEGMENTO", "").strip()

    if not url or not key:
        print("[erro] SUPABASE_URL e SUPABASE_ANON_KEY (ou SERVICE_ROLE) obrigatórios.")
        sys.exit(1)
    if not agencia:
        print("[erro] AGENCIA obrigatória no .env (ex: AGENCIA=\"Ethos Growth\").")
        sys.exit(1)

    return {
        "url": url,
        "key": key,
        "agencia": agencia,
        "segmento": segmento or "geral",
    }


def headers_supabase(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def carregar_local(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[erro] arquivo de entrada não encontrado: {path}")
        sys.exit(1)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    leads = data.get("leads") if isinstance(data, dict) else data
    if not isinstance(leads, list):
        print(f"[erro] formato inesperado em {path}")
        sys.exit(1)
    return leads


def buscar_remoto(cfg: dict) -> list[dict]:
    """Busca todos os leads existentes da agência."""
    print(f"[info] Buscando leads existentes da agência '{cfg['agencia']}'...")
    url = f"{cfg['url']}/rest/v1/leads"
    params = {
        "agencia": f"eq.{cfg['agencia']}",
        "select": "id,external_id,cnpj,whatsapp_numero,nome,segmento,status,novo_nesta_rodada",
    }
    resp = requests.get(url, headers=headers_supabase(cfg["key"]), params=params, timeout=30)
    if resp.status_code != 200:
        print(f"[erro] HTTP {resp.status_code} ao buscar: {resp.text[:200]}")
        sys.exit(1)
    leads = resp.json()
    print(f"[info] {len(leads)} leads existentes na nuvem")
    return leads


def indexar_remotos(remotos: list[dict]) -> tuple[dict, dict, dict]:
    by_cnpj = {}
    by_wa = {}
    by_nome = {}
    for r in remotos:
        cnpj = (r.get("cnpj") or "").strip()
        if cnpj:
            by_cnpj[cnpj] = r
            continue  # CNPJ é mais forte; não indexa em WA/nome
        wa = (r.get("whatsapp_numero") or "").strip()
        if wa:
            by_wa[wa] = r
        nome_norm = normalizar_nome(r.get("nome") or "")
        if nome_norm:
            by_nome[nome_norm] = r
    return by_cnpj, by_wa, by_nome


def encontrar_match(lead: dict, by_cnpj: dict, by_wa: dict, by_nome: dict) -> dict | None:
    cnpj = (lead.get("cnpj") or "").strip()
    if cnpj and cnpj in by_cnpj:
        return by_cnpj[cnpj]
    wa = (lead.get("whatsapp_numero") or "").strip()
    if wa and not cnpj and wa in by_wa:
        return by_wa[wa]
    nome_norm = normalizar_nome(lead.get("nome") or "")
    if nome_norm and nome_norm in by_nome:
        return by_nome[nome_norm]
    return None


def montar_payload_insert(lead: dict, agencia: str, segmento: str, cidade: str | None = None) -> dict:
    """Mapeia o JSON local para o schema da tabela leads."""
    return {
        "external_id": str(lead.get("id")) if lead.get("id") is not None else None,
        "agencia": agencia,
        "segmento": segmento,
        "cidade_busca": cidade,
        "nome": lead.get("nome") or "",
        "razao_social": lead.get("razao_social"),
        "nome_fantasia": lead.get("nome_fantasia"),
        "cnpj": lead.get("cnpj") or None,
        "endereco_completo": lead.get("endereco_completo"),
        "cidade": lead.get("cidade"),
        "bairro": lead.get("bairro"),
        "telefone": lead.get("telefone"),
        "whatsapp_numero": lead.get("whatsapp_numero") or None,
        "whatsapp_ativo": bool(lead.get("whatsapp_ativo")),
        "site": lead.get("site"),
        "maps_url": lead.get("maps_url"),
        "socios_cnpj": lead.get("socios_cnpj") or [],
        "dono": lead.get("dono"),
        "dono_fonte": lead.get("dono_fonte"),
        "maps_nota": lead.get("maps_nota"),
        "maps_recencia_dias": lead.get("maps_recencia_dias"),
        "maps_nrl": lead.get("maps_nrl"),
        "nicho_cliente": lead.get("nicho_cliente"),
        "tempo_mercado": lead.get("tempo_mercado"),
        "equipe_visivel": lead.get("equipe_visivel"),
        "instagram": lead.get("instagram") or {},
        "anuncia_meta": lead.get("anuncia_meta"),
        "anuncia_google": lead.get("anuncia_google"),
        "meta_ads_count": int(lead.get("meta_ads_count") or 0),
        "rapport_humano": lead.get("rapport_humano") or [],
        "gancho_dor": lead.get("gancho_dor") or [],
        "priority_score": float(lead.get("priority_score") or 0),
        "status": "novo",
        "notes": [],
        "activity": [],
        "novo_nesta_rodada": True,
        "first_seen_at": datetime.utcnow().isoformat() + "Z",
        "last_seen_at": datetime.utcnow().isoformat() + "Z",
    }


def montar_payload_update(lead: dict) -> dict:
    """Atualização diferencial: somente campos voláteis + last_seen_at."""
    payload = {"last_seen_at": datetime.utcnow().isoformat() + "Z"}
    for campo in CAMPOS_VOLATEIS:
        if campo in lead and lead[campo] is not None:
            payload[campo] = lead[campo]
    # Casts críticos
    if "meta_ads_count" in payload:
        payload["meta_ads_count"] = int(payload["meta_ads_count"] or 0)
    if "whatsapp_ativo" in payload:
        payload["whatsapp_ativo"] = bool(payload["whatsapp_ativo"])
    return payload


def bulk_insert(cfg: dict, novos: list[dict]) -> int:
    """Insere em lotes de 100. Retorna quantos foram aceitos."""
    if not novos:
        return 0
    print(f"[info] Inserindo {len(novos)} leads novos...")
    aceitos = 0
    LOTE = 100
    for i in range(0, len(novos), LOTE):
        chunk = novos[i:i + LOTE]
        url = f"{cfg['url']}/rest/v1/leads"
        resp = requests.post(url, headers=headers_supabase(cfg["key"]), json=chunk, timeout=60)
        if resp.status_code in (200, 201):
            aceitos += len(chunk)
            print(f"  [ok] lote {i // LOTE + 1}: {len(chunk)} aceitos")
        else:
            print(f"  [erro] lote {i // LOTE + 1}: HTTP {resp.status_code} — {resp.text[:300]}")
    return aceitos


def patch_lead(cfg: dict, lead_id: str, payload: dict) -> bool:
    url = f"{cfg['url']}/rest/v1/leads"
    params = {"id": f"eq.{lead_id}"}
    resp = requests.patch(
        url,
        headers=headers_supabase(cfg["key"]),
        params=params,
        json=payload,
        timeout=30,
    )
    return resp.status_code in (200, 204)


def registrar_execucao(cfg: dict, extraidos: int, novos: int, existentes: int, duracao: float) -> None:
    payload = {
        "agencia": cfg["agencia"],
        "segmento": cfg["segmento"],
        "leads_extraidos": extraidos,
        "leads_novos": novos,
        "leads_existentes": existentes,
        "duracao_segundos": int(duracao),
        "data_execucao": datetime.utcnow().isoformat() + "Z",
    }
    url = f"{cfg['url']}/rest/v1/execucoes"
    resp = requests.post(url, headers=headers_supabase(cfg["key"]), json=payload, timeout=30)
    if resp.status_code in (200, 201):
        print("[ok] Execução registrada no histórico")
    else:
        print(f"[aviso] Falha ao registrar execução: HTTP {resp.status_code} — {resp.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync incremental do Supabase")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Caminho do leads_final.json")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem escrever no Supabase")
    args = parser.parse_args()

    inicio = time.time()
    cfg = carregar_env()

    print()
    print("=" * 70)
    print("  Fase 08a — Sync incremental Supabase")
    print("=" * 70)
    print(f"  Agência:  {cfg['agencia']}")
    print(f"  Segmento: {cfg['segmento']}")
    print(f"  Entrada:  {args.input.name}")
    print(f"  Dry-run:  {'sim' if args.dry_run else 'não'}")
    print("=" * 70)
    print()

    leads_locais = carregar_local(args.input)
    print(f"[info] {len(leads_locais)} leads locais carregados")

    remotos = buscar_remoto(cfg)
    by_cnpj, by_wa, by_nome = indexar_remotos(remotos)

    cidade_default = None
    for lead in leads_locais:
        if lead.get("cidade"):
            cidade_default = lead["cidade"]
            break

    novos: list[dict] = []
    para_atualizar: list[tuple[str, dict]] = []

    for lead in leads_locais:
        match = encontrar_match(lead, by_cnpj, by_wa, by_nome)
        if match:
            payload = montar_payload_update(lead)
            para_atualizar.append((match["id"], payload))
            lead["novo_nesta_rodada"] = False
            lead["supabase_id"] = match["id"]
        else:
            payload = montar_payload_insert(lead, cfg["agencia"], cfg["segmento"], cidade_default)
            novos.append(payload)
            lead["novo_nesta_rodada"] = True

    print()
    print(f"[diff] {len(novos)} novos, {len(para_atualizar)} existentes preservados")

    if args.dry_run:
        print("[dry-run] não escreveu nada no Supabase")
    else:
        if novos:
            bulk_insert(cfg, novos)
        if para_atualizar:
            print(f"[info] Atualizando campos voláteis de {len(para_atualizar)} leads...")
            ok = 0
            for lead_id, payload in para_atualizar:
                if patch_lead(cfg, lead_id, payload):
                    ok += 1
            print(f"  [ok] {ok}/{len(para_atualizar)} atualizados")

        registrar_execucao(
            cfg,
            extraidos=len(leads_locais),
            novos=len(novos),
            existentes=len(para_atualizar),
            duracao=time.time() - inicio,
        )

    out_path = args.input
    payload_out = {
        "leads": leads_locais,
        "sync": {
            "agencia": cfg["agencia"],
            "segmento": cfg["segmento"],
            "novos": len(novos),
            "existentes_preservados": len(para_atualizar),
            "executado_em": datetime.utcnow().isoformat() + "Z",
            "dry_run": args.dry_run,
        },
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload_out, fh, ensure_ascii=False, indent=2)
    print(f"[ok] {out_path.name} atualizado com flags novo_nesta_rodada")

    print()
    print(f"[fim] {time.time() - inicio:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

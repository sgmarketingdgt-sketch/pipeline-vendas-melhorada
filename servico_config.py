"""
servico_config.py
=================
Carrega e processa configurações de serviços da pasta servicos/.
Suporta múltiplos serviços por lead (multi-service mode).
"""
from __future__ import annotations
import json
import re
from pathlib import Path

BASE = Path(__file__).parent
SERVICOS_DIR = BASE / "servicos"


def get_todos_servicos() -> dict[str, dict]:
    """Carrega todos os JSONs em servicos/ e retorna dict {id: config}."""
    configs = {}
    if not SERVICOS_DIR.exists():
        return configs
    for path in sorted(SERVICOS_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            sid = cfg.get("id") or path.stem
            configs[sid] = cfg
        except Exception as e:
            print(f"[aviso] servico_config: erro ao carregar {path.name}: {e}")
    return configs


def get_servico(servico_id: str | None = None) -> dict:
    """Carrega um serviço específico pelo ID (ou o definido no .env)."""
    if not servico_id:
        try:
            from dotenv import dotenv_values
            env = dotenv_values(BASE / ".env")
        except ImportError:
            env = {}
        servico_id = env.get("SERVICO", "").strip()
    if not servico_id:
        return {}
    path = SERVICOS_DIR / f"{servico_id}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ─── Scoring e classificação ──────────────────────────────────────────────────

def _site_sem_proprio(site: str) -> bool:
    s = (site or "").lower()
    return not s or any(p in s for p in [
        "ifood", "instagram", "facebook", "goomer",
        "saipos", "menudino", "anota.ai", "ola.click",
    ])


def calcular_priority_score_servico(lead: dict, servico: dict) -> float:
    if not servico:
        return 0.0

    score = 0.0
    regras = servico.get("priority_score", {}).get("regras", [])
    pesos  = servico.get("priority_score", {}).get("pesos", {})

    wa_ativo    = bool(lead.get("whatsapp_ativo"))
    tem_dono    = bool(lead.get("dono"))
    sem_site    = _site_sem_proprio(lead.get("site") or "")
    tem_ig      = bool((lead.get("instagram") or {}).get("url") or lead.get("instagram_handle"))
    anuncia_nao = lead.get("anuncia_meta") == "nao" or lead.get("anuncia_meta") is None

    if wa_ativo:
        score += pesos.get("wa_ativo_bonus", 15)
    if tem_dono:
        score += pesos.get("dono_identificado_bonus", 10)
    if sem_site:
        score += pesos.get("maps_sem_site_bonus", 0)

    for regra in regras:
        campo = regra.get("campo", "")
        bonus = regra.get("bonus", 0)

        # Campos booleanos especiais
        if campo == "site_ausente":
            if sem_site: score += bonus
            continue
        if campo == "anuncia_meta_nao":
            if anuncia_nao: score += bonus
            continue
        if campo == "tem_instagram":
            if tem_ig: score += bonus
            continue

        # Campos numéricos
        valor_lead = lead.get(campo)
        if valor_lead is None:
            continue
        try:
            valor_lead = float(valor_lead)
            valor_ref  = float(regra.get("valor", 0))
        except (TypeError, ValueError):
            continue

        op = regra.get("operador", "")
        if   op == "<"  and valor_lead <  valor_ref: score += bonus
        elif op == "<=" and valor_lead <= valor_ref: score += bonus
        elif op == ">"  and valor_lead >  valor_ref: score += bonus
        elif op == ">=" and valor_lead >= valor_ref: score += bonus
        elif op == "="  and valor_lead == valor_ref: score += bonus

    return round(score, 1)


def classificar_lead(lead: dict, servico: dict) -> str:
    """Retorna 'alta', 'media' ou 'baixa' baseado nos sinais do ICP."""
    if not servico:
        return "media"

    sinais   = servico.get("icp", {}).get("sinais_qualificacao", {})
    descartar = sinais.get("descartar", [])

    wa_ativo    = bool(lead.get("whatsapp_ativo"))
    tem_ig      = bool((lead.get("instagram") or {}).get("url") or lead.get("instagram_handle"))
    sem_site    = _site_sem_proprio(lead.get("site") or "")
    anuncia_nao = lead.get("anuncia_meta") == "nao" or lead.get("anuncia_meta") is None

    # Descarte
    if "wa_ativo = false" in descartar and not wa_ativo:
        return "baixa"
    if "sem instagram e sem site" in descartar and not tem_ig and not (lead.get("site") or ""):
        return "baixa"

    nota    = float(lead.get("maps_nota")      or 5)
    avals   = int(lead.get("maps_avaliacoes")  or 0)
    recencia = int(lead.get("maps_recencia_dias") or 0)
    sid = servico.get("id", "")

    if sid == "gmb":
        if nota < 4.2 or avals < 100 or recencia > 60 or sem_site:
            return "alta"
        if nota < 4.5 or avals < 300 or recencia > 30:
            return "media"
        return "baixa"

    if sid == "trafego_pago":
        if anuncia_nao and wa_ativo and tem_ig:
            return "alta"
        if anuncia_nao and wa_ativo:
            return "media"
        if not anuncia_nao and wa_ativo:
            return "media"  # upsell/troca de agência
        return "baixa"

    # Genérico
    return "media" if wa_ativo else "baixa"


def gerar_rapport(lead: dict, servico: dict) -> list[str]:
    templates = servico.get("rapport_humano", [])
    result = []
    for tpl in templates:
        s = tpl
        s = s.replace("{maps_avaliacoes}", str(lead.get("maps_avaliacoes") or "poucas"))
        s = s.replace("{maps_nota}", str(lead.get("maps_nota") or ""))
        s = s.replace("{nome}", lead.get("nome") or "")
        s = s.replace("{segmento}", lead.get("nicho_cliente") or "restaurante")
        result.append(s)
    return result


def gerar_gancho_dor(servico: dict, lead: dict | None = None) -> list[str]:
    """Retorna ganchos de dor, substituindo placeholders se lead for fornecido."""
    templates = servico.get("gancho_dor", [])
    if not lead:
        return templates
    dono = lead.get("dono") or ""
    dono_primeiro = dono.split()[0].title() if dono else "tudo bem"
    result = []
    for tpl in templates:
        s = tpl
        s = s.replace("{dono_primeiro_nome}", dono_primeiro)
        s = s.replace("{nome}",              lead.get("nome") or "")
        s = s.replace("{segmento}",          lead.get("nicho_cliente") or "escola")
        s = s.replace("{maps_avaliacoes}",   str(lead.get("maps_avaliacoes") or ""))
        s = s.replace("{maps_nota}",         str(lead.get("maps_nota") or ""))
        s = s.replace("{cidade}",            lead.get("cidade") or "")
        result.append(s)
    return result


def gerar_mensagem_wa(lead: dict, servico: dict) -> str | None:
    tpl = servico.get("mensagem_wa_template", "")
    if not tpl:
        return None
    dono = lead.get("dono") or ""
    dono_primeiro = dono.split()[0].title() if dono else "tudo bem"
    msg = tpl
    msg = msg.replace("{dono_primeiro_nome}", dono_primeiro)
    msg = msg.replace("{nome}", lead.get("nome") or "")
    msg = msg.replace("{segmento}", lead.get("nicho_cliente") or "restaurante")
    msg = msg.replace("{maps_avaliacoes}", str(lead.get("maps_avaliacoes") or ""))
    msg = msg.replace("{maps_nota}", str(lead.get("maps_nota") or ""))
    return msg


def processar_todos_servicos(lead: dict) -> dict:
    """
    Processa todos os serviços disponíveis para um lead.
    Filtra por nicho_alvo: serviços com nicho_alvo definido só são aplicados
    a leads cujo campo 'segmento' bate com o nicho_alvo do serviço.

    Retorna dict:
    {
      "gmb":                  { "classificacao": "alta", "score": 55, ... },
      "trafego_pago_aviacao": { "classificacao": "media", "score": 40, ... },
      ...
    }
    """
    todos = get_todos_servicos()
    resultado = {}
    nicho_lead = (lead.get("segmento") or "").lower()

    for sid, cfg in todos.items():
        nicho_alvo = (cfg.get("nicho_alvo") or "").lower()

        # Se o serviço tem nicho_alvo definido, só processa leads do nicho certo
        if nicho_alvo and nicho_lead:
            if nicho_alvo not in nicho_lead and nicho_lead not in nicho_alvo:
                continue

        score         = calcular_priority_score_servico(lead, cfg)
        classificacao = classificar_lead(lead, cfg)
        rapport       = gerar_rapport(lead, cfg)
        gancho        = gerar_gancho_dor(cfg, lead)
        mensagem      = gerar_mensagem_wa(lead, cfg)
        resultado[sid] = {
            "nome_servico":  cfg.get("nome", sid),
            "classificacao": classificacao,
            "score":         score,
            "rapport":       rapport,
            "gancho":        gancho,
            "mensagem_wa":   mensagem,
        }
    return resultado

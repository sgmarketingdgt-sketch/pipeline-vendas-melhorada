#!/usr/bin/env python3
"""
consolidate_v2.py
=================

Consolida os dados das fases anteriores (CSV base + CNPJ + BrasilAPI +
enriched v2 + WA + anuncia Meta/Google) em um único `leads_final.json`.

Fontes:
    --source=local      (default) merge dos JSONs locais das fases
    --source=supabase   pull dos leads já sincronizados no Supabase
    --source=hybrid     local + complementa com Supabase para preservar
                         status, notas e atividade entre execuções

Uso típico:
    python consolidate_v2.py
    python consolidate_v2.py --source=supabase
    python consolidate_v2.py --source=hybrid
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
OUT  = BASE / "leads_final.json"

# ── Offset de ID por segmento (evita colisão ao misturar nichos) ─────────────
# Cada nicho ocupa uma faixa de 100 IDs. Adicione novos nichos aqui.
SEGMENTO_ID_OFFSET: dict[str, int] = {
    "hamburgueria":      0,    # IDs  1 – 99
    "escola de aviação": 100,  # IDs 101 – 199
    "escola de aviacao": 100,
}

def _id_offset(segmento: str) -> int:
    s = (segmento or "").lower()
    for key, off in SEGMENTO_ID_OFFSET.items():
        if key in s:
            return off
    return 0


# ── Ângulo de abordagem ──────────────────────────────────────────────────────

# Resultado esperado por serviço — aparece no campo resultado_alvo de cada lead
RESULTADO_ALVO_POR_SERVICO: dict[str, str] = {
    "trafego_pago":         "Aumentar pedidos via Meta Ads",
    "gmb":                  "Dominar busca local no Google Maps",
    "trafego_pago_aviacao": "Captar matrículas via Google Ads",
}


def _extrair_angulo(gancho_text: str) -> tuple[str, str]:
    """Extrai a tag [TIPO] do início do gancho.

    Retorna (angulo, conteudo_sem_tag):
      angulo  — 'DOR' | 'DESEJO' | 'OPORTUNIDADE' | 'DADO DE MERCADO' | 'Abordagem'
      conteudo — texto do gancho sem o prefixo [TAG], pronto para uso no bot
    """
    if not gancho_text:
        return ("Abordagem", "")
    m = re.match(r"^\[([^\]]+)\]\s*", gancho_text)
    if m:
        return (m.group(1), gancho_text[m.end():].strip())
    return ("Abordagem", gancho_text.strip())


def _selecionar_gancho(gancho_list: list, lead: dict) -> str:
    """Escolhe o gancho mais adequado ao perfil do lead.

    Empresa que já anuncia → ângulo DESEJO (upsell).
    Empresa sem anúncio   → ângulo DOR ou DADO DE MERCADO.
    Fallback              → primeiro da lista.
    """
    if not gancho_list:
        return ""
    anuncia = (lead.get("anuncia_meta") or "").lower()
    for item in gancho_list:
        tag_m = re.match(r"^\[([^\]]+)\]", item or "")
        tag = (tag_m.group(1).upper() if tag_m else "")
        if anuncia == "sim" and "DESEJO" in tag:
            return item
        if anuncia != "sim" and any(k in tag for k in ("DOR", "DADO", "OPORTUNIDADE")):
            return item
    return gancho_list[0]


# ---------------------------------------------------------------------
# Modo LOCAL — comportamento histórico do CMD-3
# ---------------------------------------------------------------------

def _normalizar_tel(tel: str) -> str:
    """Remove tudo que não é dígito e retorna os últimos 11 dígitos (DDD + número)."""
    digits = re.sub(r"\D", "", tel or "")
    return digits[-11:] if len(digits) >= 11 else digits

def _chave_lead(lead: dict) -> str:
    """Chave de identificação única de um lead para merge incremental.
    Prioridade: telefone normalizado → nome+cidade (lowercase, sem espaços extras)."""
    tel = _normalizar_tel(lead.get("telefone") or lead.get("whatsapp_numero") or "")
    if len(tel) >= 10:
        return f"tel:{tel}"
    nome  = re.sub(r"\s+", " ", (lead.get("nome") or "")).strip().lower()
    cidade = (lead.get("cidade") or "").strip().lower()
    return f"nome:{nome}|{cidade}"


def consolidar_local() -> tuple[list, dict]:
    # Carrega todos os serviços disponíveis
    try:
        from servico_config import (
            get_servico, processar_todos_servicos,
            calcular_priority_score_servico, gerar_rapport,
            gerar_gancho_dor, classificar_lead, gerar_mensagem_wa,
        )
        servico_principal = get_servico()  # serviço definido no .env (fallback para rapport/gancho genérico)
        multi_servico = True
    except ImportError:
        servico_principal = {}
        multi_servico = False
        def processar_todos_servicos(lead): return {}
        def calcular_priority_score_servico(lead, s): return 0.0
        def gerar_rapport(lead, s): return []
        def gerar_gancho_dor(s): return []
        def classificar_lead(lead, s): return "media"
        def gerar_mensagem_wa(lead, s): return None

    leads_by_id = {}
    # ── Detecta segmento desta rodada (CSV ou .env) ──────────────────────────
    from dotenv import dotenv_values
    _env = dotenv_values(BASE / ".env") if (BASE / ".env").exists() else {}
    _segmento_env = (_env.get("SEGMENTO") or "Geral").strip().strip('"').strip("'")
    _id_off = _id_offset(_segmento_env)

    csv_path = BASE / "leads_merged.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig") as fh:
            for i, row in enumerate(csv.DictReader(fh), 1):
                if i > 50:
                    break
                leads_by_id[i] = row

    cnpj_by_id = {}
    cnpj_path = BASE / "cnpj_enriquecidos.json"
    if cnpj_path.exists():
        with cnpj_path.open("r", encoding="utf-8") as fh:
            for c in json.load(fh):
                cnpj_by_id[c["id"]] = c

    # lotes_v2 contém enriquecimento AI gerado especificamente para hamburguerias.
    # Carregar para outros segmentos causaria contaminação (nicho, instagram errados).
    v2_by_id = {}
    _segmento_lower = _segmento_env.lower()
    if "hamburgueria" in _segmento_lower or _segmento_lower in ("", "geral"):
        for i in range(1, 6):
            p = BASE / "lotes_v2" / f"enriched_v2_{i}.json"
            if p.exists():
                with p.open("r", encoding="utf-8") as fh:
                    for item in json.load(fh):
                        v2_by_id[item["id"]] = item

    wa_by_id = {}
    wa_path = BASE / "wa_validado.json"
    if wa_path.exists():
        with wa_path.open("r", encoding="utf-8") as fh:
            for w in json.load(fh):
                wa_by_id[w["id"]] = w

    anuncia_by_id = {}
    anuncia_path = BASE / "anuncia_validado.json"
    if anuncia_path.exists():
        with anuncia_path.open("r", encoding="utf-8") as fh:
            for a in json.load(fh):
                anuncia_by_id[a["id"]] = a

    email_by_id = {}
    email_path = BASE / "email_validado.json"
    if email_path.exists():
        with email_path.open("r", encoding="utf-8") as fh:
            for e in json.load(fh):
                if e.get("email"):
                    email_by_id[e["id"]] = e

    v1_by_id = {}
    for i in range(1, 6):
        p = BASE / "lotes" / f"enriched_{i}.json"
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                for item in json.load(fh):
                    v1_by_id[item["id"]] = item

    for lid, a in anuncia_by_id.items():
        v = v2_by_id.setdefault(lid, {})
        v["anuncia_meta"] = a.get("anuncia_meta", v.get("anuncia_meta"))
        v["anuncia_google"] = a.get("anuncia_google", v.get("anuncia_google"))
        v["meta_ads_count"] = a.get("meta_ads_count", 0)

    final = []
    total_ids = max(leads_by_id.keys()) if leads_by_id else 0
    for lid in range(1, total_ids + 1):
        base = leads_by_id.get(lid, {})
        cnpj = cnpj_by_id.get(lid, {})
        v2 = v2_by_id.get(lid, {})
        wa = wa_by_id.get(lid, {})
        v1 = v1_by_id.get(lid, {})

        nome = base.get("nome", "")
        endereco = base.get("endereco", "")

        # Extrai cidade e bairro de endereço brasileiro (qualquer estado)
        # Formato típico: "Rua X, 123 - Bairro, Cidade - UF, CEP, Brazil"
        # Pega o par "Cidade - UF" imediatamente antes do CEP
        cidade_match = re.search(r',\s*([^,\-]+?)\s*-\s*([A-Z]{2}),\s*\d{5}', endereco)
        if cidade_match:
            cidade = cidade_match.group(1).strip()
        else:
            # Fallback: qualquer "Cidade - UF" no endereço
            cidade_match2 = re.search(r'([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\.]+?)\s*-\s*([A-Z]{2})\b', endereco)
            cidade = cidade_match2.group(1).strip() if cidade_match2 else ""

        # Extrai bairro: texto entre vírgula e o par "Cidade - UF"
        bairro_match = re.search(r'-\s*([^,\-]+?)\s*,\s*[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]+?\s*-\s*[A-Z]{2},', endereco)
        bairro = bairro_match.group(1).strip() if bairro_match else v2.get("bairro_atuacao", "")

        try:
            gmn_score = float(base.get("score") or 0)
        except (TypeError, ValueError):
            gmn_score = 0
        try:
            q_score = float(v2.get("score_qualidade_pesquisa") or 5)
        except (TypeError, ValueError):
            q_score = 5
        wa_bonus = 10 if wa.get("wa_ativo") else 0
        dono_id = (v2.get("dono_identificado") or "").lower()
        dono_bonus = 15 if v2.get("dono_identificado") and "nao_identificado" not in dono_id else 0
        ig_url = (v2.get("instagram") or {}).get("url") or ""
        ig_bonus = 5 if "http" in ig_url else 0
        priority_score_base = round(gmn_score * 0.3 + q_score * 5 + wa_bonus + dono_bonus + ig_bonus, 1)

        # Segmento deste lead (do CSV ou do .env)
        segmento_lead = (base.get("segmento") or _segmento_env).strip().strip('"').strip("'")

        # Score específico do serviço (sobrepõe o base se configurado)
        lead_parcial = {
            "whatsapp_ativo": wa.get("wa_ativo", False),
            "dono": None,  # preenchido abaixo
            "site": base.get("site"),
            "maps_nota": base.get("nota"),
            "maps_avaliacoes": base.get("avaliacoes"),
            "maps_recencia_dias": base.get("recencia_dias"),
            "segmento": segmento_lead,
        }
        servico_score = calcular_priority_score_servico(lead_parcial, servico_principal)
        priority_score = round(priority_score_base + servico_score, 1) if servico_principal else priority_score_base

        dono_raw = v2.get("dono_identificado") or ""
        dono_limpo = None
        if dono_raw and "nao_identificado" not in dono_raw.lower() and "nao_encontrado" not in dono_raw.lower():
            dono_limpo = re.split(r"[\(,]", dono_raw)[0].strip()

        # Fallback: usa primeiro sócio do CNPJ quando dono_identificado não foi preenchido
        if not dono_limpo:
            socios_cnpj_list = [s for s in (cnpj.get("qsa") or []) if s.get("nome")]
            if socios_cnpj_list:
                nome_socio = socios_cnpj_list[0]["nome"].title()
                # Filtra sócios que são PJ (razão social no lugar de pessoa física)
                palavras = nome_socio.split()
                is_pj = any(p.lower() in ("ltda","s/a","sa","eireli","epp","me","holding","participacoes") for p in palavras)
                if not is_pj:
                    dono_limpo = nome_socio
                    dono_raw = nome_socio

        wa_numero = wa.get("numero") or re.sub(r"\D", "", base.get("whatsapp") or "")

        # Atualiza lead_parcial com dono e dados completos
        lead_parcial["dono"] = dono_limpo
        lead_parcial["nome"] = nome
        lead_parcial["nicho_cliente"] = v2.get("nicho_cliente_principal")
        lead_parcial["instagram"] = v2.get("instagram") or {}
        lead_parcial["anuncia_meta"] = v2.get("anuncia_meta")

        # Processa TODOS os serviços para este lead
        servicos_lead = processar_todos_servicos(lead_parcial) if multi_servico else {}

        # Rapport/gancho/msg do serviço principal (para compatibilidade)
        servico_principal_data = servicos_lead.get(servico_principal.get("id", ""), {})
        rapport = servico_principal_data.get("rapport") or gerar_rapport(lead_parcial, servico_principal) or v2.get("rapport_humano") or []
        gancho  = servico_principal_data.get("gancho")  or gerar_gancho_dor(servico_principal) or v2.get("gancho_dor") or []
        classificacao_icp = servico_principal_data.get("classificacao") or "media"
        mensagem_wa = servico_principal_data.get("mensagem_wa")

        # ── Ângulo principal de abordagem ────────────────────────────────────
        _gancho_para_angulo = servico_principal_data.get("gancho") or gancho
        _gancho_sel = _selecionar_gancho(_gancho_para_angulo, lead_parcial)
        _angulo, _conteudo_angulo = _extrair_angulo(_gancho_sel)
        _servico_id = servico_principal.get("id", "") if servico_principal else ""
        _resultado_alvo = RESULTADO_ALVO_POR_SERVICO.get(
            _servico_id, "Crescimento via marketing digital"
        )

        final.append({
            "id": lid + _id_off,
            "segmento": segmento_lead,
            "nome": nome,
            "razao_social": cnpj.get("razao_social"),
            "nome_fantasia": cnpj.get("nome_fantasia"),
            "cnpj": cnpj.get("cnpj"),
            "cnpj_fonte": "scraping_rodape" if cnpj.get("cnpj") else None,
            "endereco_completo": endereco,
            "cidade": cidade,
            "bairro": bairro,
            "telefone": base.get("telefone"),
            "whatsapp_numero": wa_numero,
            "whatsapp_ativo": wa.get("wa_ativo", False),
            "whatsapp_wa_me": f"https://wa.me/{wa_numero}" if wa_numero else None,
            "whatsapp_perfil_nome": wa.get("wa_name"),
            "site": (base.get("site") or "").strip() or None,
            "maps_url": base.get("maps"),
            "data_abertura": cnpj.get("data_inicio_atividade"),
            "tempo_mercado_anos": None,
            "capital_social": cnpj.get("capital_social"),
            "porte_receita": cnpj.get("porte"),
            "cnae_principal": cnpj.get("cnae_principal"),
            "situacao_receita": cnpj.get("situacao"),
            "socios_cnpj": [s for s in (cnpj.get("qsa") or []) if s.get("nome")],
            "dono": dono_limpo,
            "dono_raw": dono_raw if dono_raw else None,
            "dono_fonte": v2.get("dono_fonte"),
            "maps_nota": base.get("nota"),
            "maps_avaliacoes": base.get("avaliacoes"),
            "maps_fotos": base.get("fotos"),
            "maps_recencia_dias": base.get("recencia_dias"),
            "maps_nrl": base.get("nrl"),
            "tom_respostas_maps": v2.get("tom_respostas_maps"),
            # nicho_cliente: usa v2 (AI) se disponível, senão deriva do segmento
            "nicho_cliente": v2.get("nicho_cliente_principal") or segmento_lead,
            "tempo_mercado": v2.get("tempo_mercado"),
            "equipe_visivel": v2.get("equipe_visivel"),
            # instagram: apenas usa v2 se o segmento bate (evita handle de hamburgueria em escola de aviação)
            "instagram": v2.get("instagram") or {},
            "anuncia_meta": v2.get("anuncia_meta"),
            "anuncia_google": v2.get("anuncia_google"),
            "meta_ads_count": v2.get("meta_ads_count", 0),
            "email": email_by_id.get(lid + _id_off, {}).get("email"),
            "email_fonte": email_by_id.get(lid + _id_off, {}).get("email_fonte"),
            "whois_nome": email_by_id.get(lid + _id_off, {}).get("whois_nome"),
            "proposta_valor": v1.get("proposta_valor"),
            "site_gap": v1.get("site_gap"),
            "rapport_humano": rapport,
            "gancho_dor": gancho,
            "score_qualidade_pesquisa": v2.get("score_qualidade_pesquisa"),
            "priority_score": priority_score,
            "classificacao_icp": classificacao_icp,
            "mensagem_wa": mensagem_wa,
            "angulo": _angulo,
            "conteudo_angulo": _conteudo_angulo,
            "resultado_alvo": _resultado_alvo,
            "servicos": servicos_lead,
            "query_origem": base.get("query_origem"),
            "novo_nesta_rodada": True,
            "data_entrada": datetime.now().strftime("%Y-%m-%d"),
        })

    hoje = datetime.now()
    for lead in final:
        data = lead.get("data_abertura")
        if data:
            try:
                dt = datetime.fromisoformat(data)
                lead["tempo_mercado_anos"] = round((hoje - dt).days / 365.25, 1)
            except ValueError:
                pass

    # ── Merge incremental com leads_final.json existente ────────────────────
    if OUT.exists():
        try:
            with OUT.open("r", encoding="utf-8") as fh:
                existing = json.load(fh).get("leads", [])

            # Separa por segmento
            mesmo_seg  = [l for l in existing if (l.get("segmento") or "").lower() == segmento_lead.lower()]
            outros_seg = [l for l in existing if (l.get("segmento") or "").lower() != segmento_lead.lower()]

            # ── Preserva status/notas/follow-up dos leads do MESMO segmento ──
            # Monta índice por chave de identificação dos leads EXISTENTES
            existing_by_key: dict[str, dict] = {}
            for el in mesmo_seg:
                k = _chave_lead(el)
                existing_by_key[k] = el

            # Monta índice por chave dos leads NOVOS (recém-consolidados)
            new_keys: set[str] = set()
            for nl in final:
                k = _chave_lead(nl)
                new_keys.add(k)
                if k in existing_by_key:
                    el = existing_by_key[k]
                    # Preserva dados de pipeline (não sobrescreve com None)
                    nl["status"]         = el.get("status", "novo")
                    nl["notes"]          = el.get("notes") or []
                    nl["activity"]       = el.get("activity") or []
                    nl["followup_start"] = el.get("followup_start")
                    nl["followup_sent"]  = el.get("followup_sent") or {}
                    nl["loss_reason"]    = el.get("loss_reason")
                    nl["supabase_id"]    = el.get("supabase_id")
                    nl["first_seen_at"]  = el.get("first_seen_at")
                    # Preserva campos de Instagram preenchidos (manual ou automaticamente)
                    for ig_field in (
                        "instagram_local_url",
                        "instagram_dono_url", "instagram_dono_nome", "instagram_dono_bio",
                        "instagram_decisor_url", "instagram_decisor_nome", "instagram_decisor_bio",
                    ):
                        if el.get(ig_field):
                            nl.setdefault(ig_field, el[ig_field])
                    nl["novo_nesta_rodada"] = False  # já existia
                    nl["data_entrada"] = el.get("data_entrada", datetime.now().strftime("%Y-%m-%d"))
                    # historico_resumido é gravado pelo N8N — nunca sobrescrever
                    if el.get("historico_resumido"):
                        nl["historico_resumido"] = el["historico_resumido"]
                else:
                    nl["novo_nesta_rodada"] = True   # realmente novo
                    nl["data_entrada"] = datetime.now().strftime("%Y-%m-%d")

            # Leads que existiam mas NÃO apareceram na nova extração → mantém com flag
            leads_sumidos = [
                el for el in mesmo_seg
                if _chave_lead(el) not in new_keys
            ]
            for el in leads_sumidos:
                el["nao_visto_nesta_rodada"] = True
                el["novo_nesta_rodada"] = False
            if leads_sumidos:
                print(f"  ↩  {len(leads_sumidos)} leads anteriores não encontrados nesta rodada (mantidos)")
                final.extend(leads_sumidos)

            novos_count    = sum(1 for nl in final if nl.get("novo_nesta_rodada"))
            repetidos_count = sum(1 for nl in final if not nl.get("novo_nesta_rodada") and not nl.get("nao_visto_nesta_rodada"))
            print(f"  ✦  {novos_count} leads novos | {repetidos_count} atualizados | {len(leads_sumidos)} mantidos sem reextração")

            # ── Preserva outros segmentos com merge de email ──────────────────
            for l in outros_seg:
                if not l.get("email") and l["id"] in email_by_id:
                    em = email_by_id[l["id"]]
                    l["email"]       = em.get("email")
                    l["email_fonte"] = em.get("email_fonte")
                    l["whois_nome"]  = em.get("whois_nome")
            if outros_seg:
                print(f"  Preservando {len(outros_seg)} leads de outros nichos do leads_final.json")
                final.extend(outros_seg)

        except Exception as e:
            print(f"  [aviso] Não foi possível ler leads_final.json existente: {e}")

    final.sort(key=lambda x: -x["priority_score"])

    stats = {
        "total": len(final),
        "com_cnpj": sum(1 for l in final if l["cnpj"]),
        "com_dono": sum(1 for l in final if l["dono"]),
        "com_socios_cnpj": sum(1 for l in final if l["socios_cnpj"]),
        "wa_ativo": sum(1 for l in final if l["whatsapp_ativo"]),
        "com_instagram": sum(1 for l in final if ((l["instagram"] or {}).get("url") or "").startswith("http")),
        "anuncia_meta_sim": sum(1 for l in final if l["anuncia_meta"] == "sim"),
        "anuncia_google_sim": sum(1 for l in final if l["anuncia_google"] == "sim"),
        "com_rapport_3plus": sum(1 for l in final if len(l["rapport_humano"]) >= 3),
        "com_gancho_dor": sum(1 for l in final if len(l["gancho_dor"]) >= 2),
    }
    return final, stats


# ---------------------------------------------------------------------
# Modo SUPABASE — pull do estado atual da nuvem
# ---------------------------------------------------------------------

def consolidar_supabase() -> tuple[list, dict]:
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
    if not url or not key or not agencia:
        print("[erro] SUPABASE_URL, chave e AGENCIA são obrigatórios no .env")
        sys.exit(1)

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    params = {
        "agencia": f"eq.{agencia}",
        "select": "*",
        "order": "priority_score.desc",
    }
    resp = requests.get(f"{url}/rest/v1/leads", headers=headers, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"[erro] HTTP {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)

    leads = resp.json()
    final = []
    for r in leads:
        external_id = r.get("external_id")
        try:
            lid = int(external_id) if external_id else None
        except ValueError:
            lid = None
        wa = r.get("whatsapp_numero") or ""
        final.append({
            "id": lid or r["id"],
            "supabase_id": r["id"],
            "nome": r.get("nome"),
            "razao_social": r.get("razao_social"),
            "nome_fantasia": r.get("nome_fantasia"),
            "cnpj": r.get("cnpj"),
            "endereco_completo": r.get("endereco_completo"),
            "cidade": r.get("cidade"),
            "bairro": r.get("bairro"),
            "telefone": r.get("telefone"),
            "whatsapp_numero": wa,
            "whatsapp_ativo": r.get("whatsapp_ativo", False),
            "whatsapp_wa_me": f"https://wa.me/{wa}" if wa else None,
            "site": r.get("site"),
            "maps_url": r.get("maps_url"),
            "socios_cnpj": r.get("socios_cnpj") or [],
            "dono": r.get("dono"),
            "dono_fonte": r.get("dono_fonte"),
            "maps_nota": r.get("maps_nota"),
            "maps_recencia_dias": r.get("maps_recencia_dias"),
            "maps_nrl": r.get("maps_nrl"),
            "nicho_cliente": r.get("nicho_cliente"),
            "tempo_mercado": r.get("tempo_mercado"),
            "equipe_visivel": r.get("equipe_visivel"),
            "instagram": r.get("instagram") or {},
            "anuncia_meta": r.get("anuncia_meta"),
            "anuncia_google": r.get("anuncia_google"),
            "meta_ads_count": r.get("meta_ads_count", 0),
            "email": email_by_id.get(r["id"], {}).get("email") or r.get("email"),
            "email_fonte": email_by_id.get(r["id"], {}).get("email_fonte") or r.get("email_fonte"),
            "whois_nome": email_by_id.get(r["id"], {}).get("whois_nome") or r.get("whois_nome"),
            "rapport_humano": r.get("rapport_humano") or [],
            "gancho_dor": r.get("gancho_dor") or [],
            "priority_score": float(r.get("priority_score") or 0),
            "status": r.get("status", "novo"),
            "notes": r.get("notes") or [],
            "activity": r.get("activity") or [],
            "novo_nesta_rodada": bool(r.get("novo_nesta_rodada")),
            "first_seen_at": r.get("first_seen_at"),
            "last_seen_at": r.get("last_seen_at"),
        })
    final.sort(key=lambda x: -x.get("priority_score", 0))

    stats = {
        "total": len(final),
        "fonte": "supabase",
        "agencia": agencia,
        "com_cnpj": sum(1 for l in final if l.get("cnpj")),
        "com_dono": sum(1 for l in final if l.get("dono")),
        "wa_ativo": sum(1 for l in final if l.get("whatsapp_ativo")),
        "anuncia_meta_sim": sum(1 for l in final if l.get("anuncia_meta") == "sim"),
        "novos_nesta_rodada": sum(1 for l in final if l.get("novo_nesta_rodada")),
        "ja_abordados": sum(1 for l in final if l.get("status") and l["status"] != "novo"),
    }
    return final, stats


# ---------------------------------------------------------------------
# Modo HYBRID — local + sobrepõe estado de trabalho do Supabase
# ---------------------------------------------------------------------

def consolidar_hybrid() -> tuple[list, dict]:
    """Local como base, complementa com status/notes/activity do Supabase."""
    locais, stats_local = consolidar_local()
    try:
        remotos, _ = consolidar_supabase()
    except SystemExit:
        print("[aviso] Supabase indisponível, retornando apenas dados locais.")
        return locais, stats_local

    by_cnpj = {r.get("cnpj"): r for r in remotos if r.get("cnpj")}
    by_wa = {r.get("whatsapp_numero"): r for r in remotos if r.get("whatsapp_numero")}

    enriquecidos = 0
    for lead in locais:
        match = None
        if lead.get("cnpj") and lead["cnpj"] in by_cnpj:
            match = by_cnpj[lead["cnpj"]]
        elif lead.get("whatsapp_numero") and lead["whatsapp_numero"] in by_wa:
            match = by_wa[lead["whatsapp_numero"]]
        if match:
            lead["status"] = match.get("status", "novo")
            lead["notes"] = match.get("notes") or []
            lead["activity"] = match.get("activity") or []
            lead["supabase_id"] = match.get("supabase_id")
            lead["novo_nesta_rodada"] = bool(match.get("novo_nesta_rodada"))
            enriquecidos += 1

    stats_local["fonte"] = "hybrid"
    stats_local["enriquecidos_pelo_supabase"] = enriquecidos
    return locais, stats_local


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Consolida leads em leads_final.json")
    parser.add_argument(
        "--source",
        choices=["local", "supabase", "hybrid"],
        default="local",
        help="Fonte dos dados (default: local)",
    )
    parser.add_argument("--out", type=Path, default=OUT, help="Caminho de saída")
    args = parser.parse_args()

    if args.source == "local":
        final, stats = consolidar_local()
    elif args.source == "supabase":
        final, stats = consolidar_supabase()
    else:
        final, stats = consolidar_hybrid()

    print("STATS FINAIS:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    payload = {
        "leads": final,
        "stats": stats,
        "gerado_em": datetime.now().isoformat(),
        "fonte": args.source,
    }
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"\nSalvo: {args.out}")
    print(f"Tamanho: {args.out.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

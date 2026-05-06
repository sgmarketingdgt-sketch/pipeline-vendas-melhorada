#!/usr/bin/env python3
"""
build_html_v2.py
================

Gera o `index.html` final substituindo placeholders no `template_crm.html`:

    __LEADS_DATA__       -> JSON com leads_final.json embutido (sempre)
    __SUPABASE_URL__     -> SUPABASE_URL (do .env, vazio se ausente)
    __SUPABASE_ANON_KEY__-> SUPABASE_ANON_KEY (do .env, vazio se ausente)
    __AGENCIA__          -> AGENCIA (do .env, vazio se ausente)
    __SEGMENTO__         -> SEGMENTO (do .env, "geral" se ausente)

Quando todos os placeholders Supabase estão vazios, o CRM gerado opera
100% local via localStorage (modo standalone). Quando estão preenchidos,
o CRM sincroniza estado com a nuvem e habilita filtros incrementais
(Apenas não contactados, Novos nesta rodada, histórico de execuções).
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
TEMPLATE = BASE / "template_crm.html"
LEADS_JSON = BASE / "leads_final.json"
OUT = BASE / "index.html"


def carregar_env() -> dict:
    """Carrega .env se existir; retorna dict vazio se ausente."""
    env_path = BASE / ".env"
    if not env_path.exists():
        return {}
    try:
        from dotenv import dotenv_values
        return {k: (v or "") for k, v in dotenv_values(env_path).items()}
    except ImportError:
        # fallback: parse manual rápido
        out = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
        return out


def main() -> int:
    if not TEMPLATE.exists():
        print(f"[erro] template não encontrado: {TEMPLATE}")
        return 1
    if not LEADS_JSON.exists():
        print(f"[erro] leads_final.json não encontrado: {LEADS_JSON}")
        return 1

    tpl = TEMPLATE.read_text(encoding="utf-8")
    with LEADS_JSON.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    env = carregar_env()
    supabase_url = env.get("SUPABASE_URL", "").strip()
    supabase_key = env.get("SUPABASE_ANON_KEY", "").strip()
    agencia = env.get("AGENCIA", "").strip()
    segmento = env.get("SEGMENTO", "geral").strip() or "geral"
    cidade = env.get("CIDADE", "").strip()
    agencia_inicial = agencia[0].upper() if agencia else "A"

    cloud_on = bool(supabase_url and supabase_key and agencia)

    leads_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = tpl
    html = html.replace("__LEADS_DATA__", leads_json)
    html = html.replace("__SUPABASE_URL__", supabase_url)
    html = html.replace("__SUPABASE_ANON_KEY__", supabase_key)
    html = html.replace("__AGENCIA__", agencia.replace("'", "\\'"))
    html = html.replace("__SEGMENTO__", segmento.replace("'", "\\'"))
    html = html.replace("__CIDADE__", cidade.replace("'", "\\'"))
    html = html.replace("__AGENCIA_INICIAL__", agencia_inicial)

    OUT.write_text(html, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    leads_qtd = len(data.get("leads", []))

    print(f"HTML gerado: {OUT}")
    print(f"Tamanho: {kb:.1f} KB")
    print(f"Leads embebidos: {leads_qtd}")
    print(f"Cloud mode: {'ativo (Supabase)' if cloud_on else 'desativado (localStorage)'}")
    if cloud_on:
        print(f"  Agência: {agencia}")
        print(f"  Segmento: {segmento}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
setup_supabase.py
=================

Aplica o schema do Invictus Prospect Template no projeto Supabase
do usuário. Roda uma única vez por projeto.

Uso:
    python setup_supabase.py

Requer no `.env`:
    SUPABASE_URL=https://xxxxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=eyJ...        (apenas para validação; nunca commitar)
    SUPABASE_DB_URL=postgresql://...        (opcional, modo automático)

Modos de execução:

    1. Automático (preferido): se SUPABASE_DB_URL estiver presente,
       conecta via psycopg2 e aplica o schema.sql diretamente.

    2. Manual (fallback): mostra o caminho do schema.sql e instruções
       para colar no SQL Editor do Supabase.

Em ambos os modos, valida ao final se as tabelas foram criadas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("[erro] python-dotenv não instalado. Rode: pip install python-dotenv")
    sys.exit(1)

import urllib.request
import urllib.error
import json


SCHEMA_PATH = Path(__file__).parent / "supabase" / "schema.sql"
TABELAS_ESPERADAS = ["leads", "execucoes"]


def carregar_env() -> dict:
    """Carrega variáveis do .env e valida obrigatórias."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print(f"[erro] .env não encontrado em {env_path}")
        print("       Copie .env.example para .env e preencha as chaves.")
        sys.exit(1)

    load_dotenv(env_path)

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()

    if not url:
        print("[erro] SUPABASE_URL ausente no .env")
        sys.exit(1)
    if not service_key:
        print("[erro] SUPABASE_SERVICE_ROLE_KEY ausente no .env")
        print("       Pegue em: Project Settings > API > service_role (secret)")
        sys.exit(1)

    return {"url": url, "service_key": service_key, "db_url": db_url}


def carregar_schema() -> str:
    if not SCHEMA_PATH.exists():
        print(f"[erro] Schema não encontrado em {SCHEMA_PATH}")
        sys.exit(1)
    return SCHEMA_PATH.read_text(encoding="utf-8")


def aplicar_schema_automatico(db_url: str, schema_sql: str) -> bool:
    """Tenta aplicar via psycopg2. Retorna True se ok, False se falhou."""
    try:
        import psycopg2
    except ImportError:
        print("[aviso] psycopg2 não instalado. Caindo para modo manual.")
        print("        Para usar o modo automático: pip install psycopg2-binary")
        return False

    print("[info] Aplicando schema via conexão direta...")
    try:
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
        print("[ok] Schema aplicado com sucesso.")
        return True
    except Exception as exc:
        print(f"[erro] Falha ao aplicar schema: {exc}")
        return False


def instrucoes_modo_manual(schema_sql: str, supabase_url: str) -> None:
    """Imprime instruções para o usuário aplicar o schema manualmente."""
    project_ref = supabase_url.replace("https://", "").split(".")[0]
    sql_editor = f"https://supabase.com/dashboard/project/{project_ref}/sql/new"

    print()
    print("=" * 70)
    print("  Modo manual — aplicar o schema pelo SQL Editor")
    print("=" * 70)
    print()
    print("1. Abra o SQL Editor do seu projeto:")
    print(f"   {sql_editor}")
    print()
    print("2. Copie e cole o conteúdo de:")
    print(f"   {SCHEMA_PATH}")
    print()
    print("3. Clique em 'Run'.")
    print()
    print("4. Rode novamente este script para validar:")
    print("   python setup_supabase.py")
    print()
    print("=" * 70)


def validar_tabelas(url: str, service_key: str) -> bool:
    """Verifica via PostgREST se as tabelas existem e respondem."""
    print("[info] Validando tabelas no Supabase...")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    todas_ok = True
    for tabela in TABELAS_ESPERADAS:
        endpoint = f"{url}/rest/v1/{tabela}?limit=0"
        req = urllib.request.Request(endpoint, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    print(f"  [ok] tabela '{tabela}' acessível")
                else:
                    print(f"  [aviso] tabela '{tabela}' status {resp.status}")
                    todas_ok = False
        except urllib.error.HTTPError as exc:
            print(f"  [erro] tabela '{tabela}' inacessível: HTTP {exc.code}")
            todas_ok = False
        except Exception as exc:
            print(f"  [erro] tabela '{tabela}' inacessível: {exc}")
            todas_ok = False
    return todas_ok


def main() -> int:
    print()
    print("=" * 70)
    print("  Invictus Prospect Template — Setup Supabase")
    print("=" * 70)
    print()

    cfg = carregar_env()
    schema_sql = carregar_schema()

    print(f"[info] Projeto: {cfg['url']}")
    print(f"[info] Schema: {SCHEMA_PATH.name} ({len(schema_sql)} bytes)")
    print()

    aplicado = False
    if cfg["db_url"]:
        aplicado = aplicar_schema_automatico(cfg["db_url"], schema_sql)
    else:
        print("[info] SUPABASE_DB_URL não configurado — modo manual.")
        print("       (Para automático, adicione SUPABASE_DB_URL no .env;")
        print("        pegue em Project Settings > Database > Connection string > URI)")

    if not aplicado:
        instrucoes_modo_manual(schema_sql, cfg["url"])

    print()
    if validar_tabelas(cfg["url"], cfg["service_key"]):
        print()
        print("[sucesso] Supabase configurado. Tudo pronto para o pipeline.")
        return 0

    print()
    print("[pendente] Aplique o schema no SQL Editor (instruções acima)")
    print("           e rode este script de novo para validar.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# =====================================================================
# Invictus Prospect Template — setup automatizado (macOS / Linux)
# =====================================================================
# Cria venv, instala dependências, baixa Chromium, prepara .env.
# Rode uma vez por máquina:
#
#     chmod +x setup.sh && ./setup.sh
#
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "===================================================================="
echo "  Invictus Prospect Template — Setup"
echo "===================================================================="
echo

# ---------------------------------------------------------------------
# Python 3.10+ check
# ---------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "[erro] Python 3 não encontrado."
  echo "       Instale em: https://www.python.org/downloads/"
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo "[erro] Python 3.10+ obrigatório. Você tem $PY_VERSION."
  exit 1
fi
echo "[ok] Python $PY_VERSION detectado"

# ---------------------------------------------------------------------
# Virtualenv
# ---------------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "[info] Criando ambiente virtual em .venv/"
  python3 -m venv .venv
else
  echo "[info] Reaproveitando .venv existente"
fi

# Ativa venv para o resto do script
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[info] Atualizando pip..."
python -m pip install --upgrade pip --quiet

# ---------------------------------------------------------------------
# Dependências Python
# ---------------------------------------------------------------------
echo "[info] Instalando dependências de requirements.txt..."
python -m pip install -r requirements.txt --quiet

# ---------------------------------------------------------------------
# Playwright (Chromium para a Fase E)
# ---------------------------------------------------------------------
echo "[info] Instalando Chromium (Playwright)..."
python -m playwright install chromium

# ---------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[ok] .env criado a partir do .env.example"
  echo "     Edite-o agora antes de rodar o pipeline:"
  echo "       \$EDITOR .env"
else
  echo "[info] .env já existe — não sobrescrevi"
fi

# ---------------------------------------------------------------------
# Próximos passos
# ---------------------------------------------------------------------
echo
echo "===================================================================="
echo "  Setup concluído. Próximos passos:"
echo "===================================================================="
echo
echo "  1. Edite o .env com suas chaves (Google Places obrigatório,"
echo "     Supabase opcional mas recomendado para sync multi-device)."
echo
echo "  2. Se for usar Supabase, crie o projeto e aplique o schema:"
echo "       python setup_supabase.py"
echo
echo "  3. Inicie o pipeline com o Claude Code:"
echo "       claude < PROMPT.md"
echo
echo "  Para ativar o ambiente em sessões futuras:"
echo "       source .venv/bin/activate"
echo

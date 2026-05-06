# =====================================================================
# Invictus Prospect Template — setup automatizado (Windows)
# =====================================================================
# Cria venv, instala dependências, baixa Chromium, prepara .env.
# Rode uma vez por máquina:
#
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# =====================================================================

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "===================================================================="
Write-Host "  Invictus Prospect Template — Setup"
Write-Host "===================================================================="
Write-Host ""

# ---------------------------------------------------------------------
# Python 3.10+ check (prefere `py` launcher do Windows)
# ---------------------------------------------------------------------
$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    Write-Host "[erro] Python 3 não encontrado."
    Write-Host "       Instale em: https://www.python.org/downloads/"
    exit 1
}

$pyVersion = & $pythonCmd -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'
$pyMajor = [int](& $pythonCmd -c 'import sys; print(sys.version_info[0])')
$pyMinor = [int](& $pythonCmd -c 'import sys; print(sys.version_info[1])')

if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
    Write-Host "[erro] Python 3.10+ obrigatório. Você tem $pyVersion."
    exit 1
}
Write-Host "[ok] Python $pyVersion detectado"

# ---------------------------------------------------------------------
# Virtualenv
# ---------------------------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "[info] Criando ambiente virtual em .venv/"
    & $pythonCmd -m venv .venv
} else {
    Write-Host "[info] Reaproveitando .venv existente"
}

# Ativa venv para o resto do script
$venvActivate = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "[erro] Falha ao criar venv (Activate.ps1 não existe)."
    exit 1
}
. $venvActivate

Write-Host "[info] Atualizando pip..."
python -m pip install --upgrade pip --quiet

# ---------------------------------------------------------------------
# Dependências Python
# ---------------------------------------------------------------------
Write-Host "[info] Instalando dependências de requirements.txt..."
python -m pip install -r requirements.txt --quiet

# ---------------------------------------------------------------------
# Playwright (Chromium para a Fase E)
# ---------------------------------------------------------------------
Write-Host "[info] Instalando Chromium (Playwright)..."
python -m playwright install chromium

# ---------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[ok] .env criado a partir do .env.example"
    Write-Host "     Edite-o agora antes de rodar o pipeline:"
    Write-Host "       notepad .env"
} else {
    Write-Host "[info] .env já existe — não sobrescrevi"
}

# ---------------------------------------------------------------------
# Próximos passos
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "===================================================================="
Write-Host "  Setup concluído. Próximos passos:"
Write-Host "===================================================================="
Write-Host ""
Write-Host "  1. Edite o .env com suas chaves (Google Places obrigatório,"
Write-Host "     Supabase opcional mas recomendado para sync multi-device)."
Write-Host ""
Write-Host "  2. Se for usar Supabase, crie o projeto e aplique o schema:"
Write-Host "       python setup_supabase.py"
Write-Host ""
Write-Host "  3. Inicie o pipeline com o Claude Code:"
Write-Host "       claude < PROMPT.md"
Write-Host ""
Write-Host "  Para ativar o ambiente em sessões futuras:"
Write-Host "       .\.venv\Scripts\Activate.ps1"
Write-Host ""

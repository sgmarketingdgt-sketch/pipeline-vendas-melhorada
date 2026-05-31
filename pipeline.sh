#!/bin/bash
# ============================================================
# pipeline.sh — Yonzza Digital
# Uso: ./pipeline.sh
# Roda todas as fases de enriquecimento + deploy automaticamente
# ============================================================

set -e  # para se qualquer fase falhar

VERDE="\033[0;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[0;31m"
RESET="\033[0m"

echo ""
echo "=================================================="
echo "  PIPELINE DE PROSPECÇÃO — Yonzza Digital"
echo "=================================================="

# Lê o .env para mostrar o contexto atual
SEGMENTO=$(grep "^SEGMENTO=" .env | cut -d'"' -f2)
CIDADE=$(grep "^CIDADE=" .env | cut -d'"' -f2)
echo ""
echo -e "  Segmento: ${AMARELO}${SEGMENTO}${RESET}"
echo -e "  Cidade:   ${AMARELO}${CIDADE}${RESET}"
echo ""
echo "  Confirma? (Enter para continuar / Ctrl+C para cancelar)"
read -r

echo ""
echo -e "${VERDE}[Fase 02] Dedup e filtro...${RESET}"
python3 merge.py

echo ""
echo -e "${VERDE}[Fase 03] Buscando CNPJs...${RESET}"
python3 fase_a_cnpj.py

echo ""
echo -e "${VERDE}[Fase 04] Enriquecendo via BrasilAPI...${RESET}"
python3 fase_b_brasilapi.py

echo ""
echo -e "${VERDE}[Fase 05] Validando WhatsApp...${RESET}"
python3 fase_d_wa_validar.py

echo ""
echo -e "${VERDE}[Fase 06] Verificando anúncios Meta e Google...${RESET}"
python3 fase_e_anuncia_real.py

echo ""
echo -e "${VERDE}[Fase 07] Buscando e-mails...${RESET}"
python3 fase_email.py

echo ""
echo -e "${VERDE}[Fase 08] Buscando Instagram e decisores...${RESET}"
python3 fase_instagram.py

echo ""
echo -e "${VERDE}[Fase 09] Consolidando leads...${RESET}"
python3 consolidate_v2.py

echo ""
echo -e "${VERDE}[Fase 09a] Sincronizando Supabase...${RESET}"
python3 fase_sync_supabase.py

echo ""
echo -e "${VERDE}[Fase 10] Gerando CRM...${RESET}"
python3 build_html_v2.py

echo ""
echo -e "${VERDE}[Fase 10] Publicando na Vercel...${RESET}"
DEPLOY_OUT=$(npx vercel --prod --yes --force 2>&1)
echo "$DEPLOY_OUT"
# Extrai URL do deployment (*.vercel.app que não seja o alias)
DEPLOY_URL=$(echo "$DEPLOY_OUT" | grep -o 'https://invictus-prospect-yonzza-[a-z0-9]*\.vercel\.app' | head -1)
if [ -n "$DEPLOY_URL" ]; then
  npx vercel alias set "${DEPLOY_URL#https://}" invictus-prospect-yonzza.vercel.app 2>/dev/null || true
fi

echo ""
echo "=================================================="
echo -e "${VERDE}  CONCLUÍDO!${RESET}"
echo -e "  CRM no ar: ${AMARELO}https://invictus-prospect-yonzza.vercel.app${RESET}"
echo "=================================================="
echo ""

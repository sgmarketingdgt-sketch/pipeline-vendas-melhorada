-- Migration: adiciona campo last_inbound_ts para detecção de burst (bot)
-- Gerado em: 2026-05-20
-- Lógica: se duas mensagens do mesmo número chegarem no mesmo minuto,
-- classifica como bot (burst detection no Fluxo-02).

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS last_inbound_ts bigint DEFAULT NULL;

-- Índice para lookup rápido por número (já deve existir, mas garante)
CREATE INDEX IF NOT EXISTS idx_leads_whatsapp_numero
  ON leads (whatsapp_numero);

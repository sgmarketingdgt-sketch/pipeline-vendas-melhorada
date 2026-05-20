-- Migration: adiciona colunas de trabalho do operador e campos de enriquecimento
-- Gerado em: 2026-05-19
-- Aplique no SQL Editor do Supabase se o projeto já existe com o schema antigo.
-- Idempotente: usa ADD COLUMN IF NOT EXISTS.

-- ---------------------------------------------------------------------
-- Sinais Maps extras (voláteis — atualizados a cada rodada do pipeline)
-- ---------------------------------------------------------------------
ALTER TABLE leads ADD COLUMN IF NOT EXISTS maps_avaliacoes   text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS maps_fotos        text;

-- ---------------------------------------------------------------------
-- Ângulo de abordagem (gerado pelo pipeline, volátil)
-- ---------------------------------------------------------------------
ALTER TABLE leads ADD COLUMN IF NOT EXISTS angulo            text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS conteudo_angulo   text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS resultado_alvo    text;

-- ---------------------------------------------------------------------
-- Score conversacional (gravado exclusivamente pelo N8N)
-- ---------------------------------------------------------------------
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS score_conversacional jsonb
  DEFAULT '{"dor":0,"momento":0,"maturidade":0,"comportamento":0,"anti_curioso":0,"total":0,"temperatura":"frio","sinais":[],"ultima_atualizacao":null}'::jsonb;

-- Índice GIN para consultas por temperatura
CREATE INDEX IF NOT EXISTS idx_leads_score_conversacional
  ON leads USING GIN (score_conversacional);

-- ---------------------------------------------------------------------
-- Campos de trabalho do operador (nunca sobrescritos pelo pipeline Python)
-- ---------------------------------------------------------------------
ALTER TABLE leads ADD COLUMN IF NOT EXISTS overrides          jsonb    DEFAULT '{}'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_bot             text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS historico_resumido text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS followup_start     bigint;   -- timestamp JS (ms)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS followup_sent      jsonb    DEFAULT '{}'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS loss_reason        text;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS needs_loss_reason  boolean  DEFAULT false;

-- ---------------------------------------------------------------------
-- Índice único para upsert por external_id (usado pelo CRM como fallback)
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS leads_external_id_agencia_uniq
  ON leads (external_id, agencia)
  WHERE external_id IS NOT NULL AND external_id <> '';

-- ---------------------------------------------------------------------
-- Preenche colunas jsonb nulas em linhas existentes
-- ---------------------------------------------------------------------
UPDATE leads SET overrides      = '{}'::jsonb WHERE overrides      IS NULL;
UPDATE leads SET followup_sent  = '{}'::jsonb WHERE followup_sent  IS NULL;
UPDATE leads SET score_conversacional =
  '{"dor":0,"momento":0,"maturidade":0,"comportamento":0,"anti_curioso":0,"total":0,"temperatura":"frio","sinais":[],"ultima_atualizacao":null}'::jsonb
  WHERE score_conversacional IS NULL;

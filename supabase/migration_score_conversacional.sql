-- Migration: adiciona campo score_conversacional à tabela leads
-- Gerado em: 2026-05-18
-- Campo gravado pelo agente N8N após interações com o lead.
-- O pipeline Python nunca sobrescreve este campo.

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS score_conversacional jsonb
  DEFAULT '{"dor":0,"momento":0,"maturidade":0,"comportamento":0,"anti_curioso":0,"total":0,"temperatura":"frio","sinais":[],"ultima_atualizacao":null}';

-- Índice GIN para consultas por temperatura ou pilar (ex: WHERE score_conversacional->>'temperatura' = 'prioridade')
CREATE INDEX IF NOT EXISTS idx_leads_score_conversacional
  ON leads USING GIN (score_conversacional);

-- Preenche leads existentes que ainda não têm o campo
UPDATE leads
SET score_conversacional = '{"dor":0,"momento":0,"maturidade":0,"comportamento":0,"anti_curioso":0,"total":0,"temperatura":"frio","sinais":[],"ultima_atualizacao":null}'::jsonb
WHERE score_conversacional IS NULL;

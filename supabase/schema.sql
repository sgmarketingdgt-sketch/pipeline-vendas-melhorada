-- =====================================================================
-- Invictus Prospect Template — Schema Supabase
-- =====================================================================
-- Aplicado pela primeira execução de `python setup_supabase.py`.
-- Idempotente: pode ser rodado várias vezes sem quebrar.
--
-- Modelo: cada usuário cria o próprio projeto Supabase. Sem multi-tenancy
-- formal, sem auth obrigatória. O campo `agencia` serve como filtro
-- lógico caso o mesmo projeto seja usado para várias marcas.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Extensões necessárias
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------
-- Tabela: leads
-- ---------------------------------------------------------------------
-- Guarda cada lead enriquecido pelo pipeline. Upsert acontece via
-- (cnpj, agencia) quando há CNPJ, ou (whatsapp_numero, agencia) como
-- fallback. Os campos voláteis (maps_nota, anuncia_meta etc) podem ser
-- atualizados em re-execuções; os campos de trabalho do operador
-- (status, notes, activity, rapport) NUNCA são sobrescritos.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id           text,
  agencia               text NOT NULL,
  segmento              text,
  cidade_busca          text,

  -- Identificação
  nome                  text NOT NULL,
  razao_social          text,
  nome_fantasia         text,
  cnpj                  text,

  -- Localização e contato
  endereco_completo     text,
  cidade                text,
  bairro                text,
  telefone              text,
  whatsapp_numero       text,
  whatsapp_ativo        boolean DEFAULT false,
  site                  text,
  maps_url              text,

  -- Dados oficiais
  socios_cnpj           jsonb DEFAULT '[]'::jsonb,
  dono                  text,
  dono_fonte            text,

  -- Sinais Maps
  maps_nota             text,
  maps_recencia_dias    text,
  maps_nrl              text,

  -- Contexto de negócio
  nicho_cliente         text,
  tempo_mercado         text,
  equipe_visivel        text,
  instagram             jsonb DEFAULT '{}'::jsonb,

  -- Sinais de mídia
  anuncia_meta          text,
  anuncia_google        text,
  meta_ads_count        integer DEFAULT 0,

  -- Sinais Maps extras
  maps_avaliacoes       text,
  maps_fotos            text,

  -- Inteligência de abordagem
  rapport_humano        jsonb DEFAULT '[]'::jsonb,
  gancho_dor            jsonb DEFAULT '[]'::jsonb,
  mensagem_wa           text,
  angulo                text,
  conteudo_angulo       text,
  resultado_alvo        text,
  priority_score        numeric DEFAULT 0,

  -- Score conversacional (gravado pelo N8N — nunca sobrescrito pelo Python)
  score_conversacional  jsonb DEFAULT '{"dor":0,"momento":0,"maturidade":0,"comportamento":0,"anti_curioso":0,"total":0,"temperatura":"frio","sinais":[],"ultima_atualizacao":null}'::jsonb,

  -- Estado de trabalho do operador (nunca sobrescrito pelo pipeline Python)
  status                text DEFAULT 'novo',
  notes                 jsonb DEFAULT '[]'::jsonb,
  activity              jsonb DEFAULT '[]'::jsonb,
  overrides             jsonb DEFAULT '{}'::jsonb,
  is_bot                text,
  historico_resumido    text,
  followup_start        bigint,
  followup_sent         jsonb DEFAULT '{}'::jsonb,
  loss_reason           text,
  needs_loss_reason     boolean DEFAULT false,

  -- Controle de execução incremental
  novo_nesta_rodada     boolean DEFAULT true,
  first_seen_at         timestamptz DEFAULT now(),
  last_seen_at          timestamptz DEFAULT now(),

  -- Auditoria
  created_at            timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Índices únicos para upsert determinístico
-- ---------------------------------------------------------------------
-- CNPJ é o identificador mais forte. Quando presente, deduplica por ele.
CREATE UNIQUE INDEX IF NOT EXISTS leads_cnpj_agencia_uniq
  ON leads (cnpj, agencia)
  WHERE cnpj IS NOT NULL AND cnpj <> '';

-- Fallback: quando não há CNPJ, deduplica por WhatsApp.
CREATE UNIQUE INDEX IF NOT EXISTS leads_whatsapp_agencia_uniq
  ON leads (whatsapp_numero, agencia)
  WHERE whatsapp_numero IS NOT NULL AND whatsapp_numero <> ''
    AND (cnpj IS NULL OR cnpj = '');

-- Índice para upsert via external_id (usado pelo cloudUpsertLead do CRM como fallback).
CREATE UNIQUE INDEX IF NOT EXISTS leads_external_id_agencia_uniq
  ON leads (external_id, agencia)
  WHERE external_id IS NOT NULL AND external_id <> '';

-- ---------------------------------------------------------------------
-- Índices de leitura (kanban e filtros)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS leads_agencia_status
  ON leads (agencia, status);

CREATE INDEX IF NOT EXISTS leads_agencia_segmento
  ON leads (agencia, segmento);

CREATE INDEX IF NOT EXISTS leads_novo_nesta_rodada
  ON leads (agencia, novo_nesta_rodada)
  WHERE novo_nesta_rodada = true;

CREATE INDEX IF NOT EXISTS leads_priority_score
  ON leads (agencia, priority_score DESC);

-- ---------------------------------------------------------------------
-- Tabela: execucoes
-- ---------------------------------------------------------------------
-- Histórico de cada rodada do pipeline. Mostrado na aba "Execuções"
-- do CRM e usado para mostrar o que foi novo em cada rodada.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS execucoes (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agencia               text NOT NULL,
  data_execucao         timestamptz DEFAULT now(),
  segmento              text,
  cidade                text,
  leads_extraidos       integer DEFAULT 0,
  leads_novos           integer DEFAULT 0,
  leads_existentes      integer DEFAULT 0,
  duracao_segundos      integer DEFAULT 0,
  observacoes           text
);

CREATE INDEX IF NOT EXISTS execucoes_agencia_data
  ON execucoes (agencia, data_execucao DESC);

-- ---------------------------------------------------------------------
-- Trigger: atualizar updated_at automaticamente
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS leads_set_updated_at ON leads;
CREATE TRIGGER leads_set_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW
  EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- Row Level Security (RLS)
-- ---------------------------------------------------------------------
-- Cada usuário cria o próprio projeto Supabase, então o modelo de
-- segurança aceitável é: anon key habilitada, RLS ativada, policy
-- aberta dentro do projeto. Quem quiser fechar mais (multi-marca no
-- mesmo projeto, JWT customizado), tem o exemplo comentado abaixo.
-- ---------------------------------------------------------------------
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE execucoes ENABLE ROW LEVEL SECURITY;

-- Policy de acesso: a anon_key é embutida no HTML do CRM (necessário para funcionar
-- sem backend). A "segurança" vem da obscuridade da URL do CRM (Vercel) e do fato
-- de ser um projeto pessoal/privado. Se o projeto for compartilhado, substitua
-- por autenticação via Supabase Auth + policy por agencia (exemplo comentado abaixo).
DROP POLICY IF EXISTS leads_anon_all ON leads;
CREATE POLICY leads_anon_all ON leads
  FOR ALL
  TO anon, authenticated
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS execucoes_anon_all ON execucoes;
CREATE POLICY execucoes_anon_all ON execucoes
  FOR ALL
  TO anon, authenticated
  USING (true)
  WITH CHECK (true);

-- Exemplo de policy mais estrita (descomentar e adaptar se necessário):
-- CREATE POLICY leads_by_agencia ON leads
--   FOR ALL
--   TO authenticated
--   USING (agencia = (auth.jwt() ->> 'agencia'))
--   WITH CHECK (agencia = (auth.jwt() ->> 'agencia'));

-- ---------------------------------------------------------------------
-- View opcional: contagem por status (útil para dashboards futuros)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW leads_stats AS
SELECT
  agencia,
  segmento,
  status,
  COUNT(*)::integer AS total,
  COUNT(*) FILTER (WHERE novo_nesta_rodada)::integer AS novos
FROM leads
GROUP BY agencia, segmento, status;

-- =====================================================================
-- Fim do schema
-- =====================================================================

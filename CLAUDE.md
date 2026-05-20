# CLAUDE.md — Invictus Prospect · Agência Yonzza Digital

Este arquivo é a memória permanente do projeto. Leia antes de qualquer ação.

---

## 1. O que é este projeto

Pipeline de prospecção B2B que extrai leads do Google Maps, enriquece com CNPJ/WA/Meta/e-mail/Instagram, gera um CRM estático e faz deploy na Vercel. O CRM sincroniza estado (status, notas, atividade) via Supabase, permitindo uso em múltiplos dispositivos. Um agente N8N faz qualificação automática por WhatsApp e escreve no mesmo Supabase.

**URL de produção:** https://invictus-prospect-yonzza.vercel.app  
**Domínio customizado:** https://agenciayonzza.com  
**Deploy:**
```bash
npx vercel --prod --yes --force
npx vercel alias set [url-gerada].vercel.app invictus-prospect-yonzza.vercel.app
```
> Nota: o caminho `/tmp/vercel-local/...` não existe mais — usar `npx vercel` diretamente.

---

## 2. Nichos ativos

| Nicho | Segmento no .env | IDs | Serviço |
|---|---|---|---|
| Hamburguerias (SP) | `Hamburgueria` | 1–99 | `trafego_pago`, `gmb` |
| Escolas de Aviação (Brasil) | `Escola de Aviação` | 101–199 | `trafego_pago_aviacao` |

Próximo nicho novo começa no offset **200** (IDs 201–299).

---

## 3. Estrutura de arquivos

```
.env                        → configuração ativa (SEGMENTO, CIDADE, SERVICO)
extrator.py                 → fase 1: extrai leads do Google Maps (Places API New)
merge.py                    → fase 2: deduplica hamburguerias (SP, top 50, filtra DDD 11)
merge_aviacao.py            → fase 2: deduplica aviação (Brasil, top 50, sem filtro DDD)
fase_a_cnpj.py              → fase 3: busca CNPJ no site de cada lead
fase_b_brasilapi.py         → fase 4: enriquece CNPJ via BrasilAPI (razão social, sócios)
fase_d_wa_validar.py        → fase 5: valida WhatsApp via Evolution API
fase_e_anuncia_real.py      → fase 6: verifica anúncios Meta + Google Ads via Playwright
fase_email.py               → fase 7: busca e-mails (RDAP + scraping + CNPJ)
fase_instagram.py           → fase 8a: busca Instagram local + dono/decisor via Google
consolidate_v2.py           → fase 8b: monta leads_final.json (multi-nicho, incremental)
build_html_v2.py            → fase 9: gera index.html com leads embutidos
template_crm.html           → fonte do CRM (NUNCA editar index.html direto)
servicos/                   → JSONs de configuração por nicho/serviço
servico_config.py           → lógica de scoring, rapport, ganchos, mensagens
leads_final.json            → saída consolidada (todos os nichos)
fase_sync_supabase.py       → sync manual completo para o Supabase
```

---

## 4. Arquivos de cache (NÃO apagar — levam horas para recriar)

```
wa_validado.json            → validações WhatsApp já feitas
anuncia_validado.json       → verificações Meta/Google Ads já feitas
email_validado.json         → e-mails encontrados (RDAP + scraping)
instagram_validado.json     → Instagram local + dono + decisor já buscados
cnpj_encontrados.json       → CNPJs extraídos dos sites
cnpj_enriquecidos.json      → dados BrasilAPI
leads_merged.csv            → CSV da rodada atual (input do consolidate)
```

---

## 5. Merge incremental — comportamento ao rodar de novo

O `consolidate_v2.py` **nunca apaga** leads que já têm trabalho feito. A cada rodada:

- **Lead que já existia** → dados enriquecidos atualizados, status/notas/follow-up preservados
- **Lead novo** → entra com badge "Novo"
- **Lead que sumiu da extração** → mantido no CRM com badge "NÃO VISTO" e opacidade reduzida
- **Outros nichos** → sempre preservados intactos

---

## 6. Como adicionar um novo nicho

**Passo A — Registrar offset de ID** em `consolidate_v2.py`:
```python
SEGMENTO_ID_OFFSET: dict[str, int] = {
    "hamburgueria":        0,    # IDs   1–99
    "escola de aviação":   100,  # IDs 101–199
    "escola de aviacao":   100,
    "novo nicho aqui":     200,  # IDs 201–299  ← adicionar
}
```

**Passo B — Criar `servicos/novo_nicho.json`** com estrutura mínima:
```json
{
  "id": "id_sem_espacos",
  "nome": "Tráfego Pago",
  "nicho_alvo": "nome do nicho (mesmo do SEGMENTO, lowercase)",
  "ticket_inicial": 0,
  "mensagem_wa_template": "Olá, {dono_primeiro_nome}! ...",
  "rapport_humano": [
    "texto de conexão 1",
    "texto de conexão 2 com {nome} e {maps_avaliacoes}",
    "texto de conexão 3"
  ],
  "gancho_dor": [
    "[DADO DE MERCADO] Olá, {dono_primeiro_nome}! ... {nome} ... CTA?",
    "[DOR] Olá, {dono_primeiro_nome}! ... {nome} ... CTA?",
    "[DESEJO] Olá, {dono_primeiro_nome}! ... {nome} ... CTA?"
  ]
}
```

**Passo C — Atualizar `.env`:**
```
SEGMENTO="Nome do Nicho"
CIDADE="Cidade ou Brasil"
SERVICO=id_sem_espacos
```

O usuário fornece: nome do nicho, cidade/região e contexto de mercado (Claude gera as mensagens).

---

## 7. Placeholders disponíveis nos templates

| Placeholder | Valor |
|---|---|
| `{dono_primeiro_nome}` | Primeiro nome do dono |
| `{nome}` | Nome do estabelecimento |
| `{segmento}` | Nicho/segmento do lead |
| `{maps_avaliacoes}` | Número de avaliações no Maps |
| `{maps_nota}` | Nota no Maps |
| `{cidade}` | Cidade do lead |

---

## 8. Pipeline completo por segmento

### Para nichos com merge genérico (hamburguerias):
```bash
python3 extrator.py "hamburguerias São Paulo"
python3 merge.py
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py
python3 consolidate_v2.py
python3 build_html_v2.py
npx vercel --prod --yes --force
npx vercel alias set [url].vercel.app invictus-prospect-yonzza.vercel.app
```

### Para aviação (merge nacional sem filtro DDD):
```bash
python3 extrator.py "escolas de aviação Brasil"
python3 merge_aviacao.py    # ← usa este em vez do merge.py
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py
python3 consolidate_v2.py
python3 build_html_v2.py
npx vercel --prod --yes --force
npx vercel alias set [url].vercel.app invictus-prospect-yonzza.vercel.app
```

---

## 9. extrator.py — detalhes importantes

Usa a **Places API New** (`places.googleapis.com/v1/places:searchText`).

Campos extraídos incluem `places.socialMediaLinks` — permite capturar Instagram e Facebook diretamente do perfil do Google Maps. Exemplo no `place_to_row()`:
```python
social = p.get("socialMediaLinks") or []
instagram_maps = next((s.get("uri","") for s in social if "instagram.com" in s.get("uri","")), "")
facebook_maps  = next((s.get("uri","") for s in social if "facebook.com"  in s.get("uri","")), "")
```
Variável de ambiente necessária: `GOOGLE_PLACES_API_KEY` no `.env`.

---

## 10. fase_e_anuncia_real.py — comportamento do cache

Cache em `anuncia_validado.json`. Lógica de re-processamento:
```python
# Leads com google_metodo = "fallback_*" são reprocessados (resultado incerto)
ja_ok = (cached
         and cached.get("anuncia_google") in ("sim", "nao")
         and not cached.get("google_metodo", "").startswith("fallback"))
```
A detecção do Google Ads Transparency Center usa `networkidle` + texto ("123 anunciantes") antes de seletores CSS, pois o site é uma SPA React/Angular.

---

## 11. Régua de follow-up (CRM)

4 sub-colunas dentro de "Abordado": **D0 → D+2 → D+5 → D+7**

| Sub-coluna | Etapa | Objetivo |
|---|---|---|
| D0 | 1 | Abordagem inicial |
| D+2 | 2 | Novo ângulo (DOR) |
| D+5 | 3 | Verificação direta (sim/não) |
| D+7 | 4 | Saída honrosa |

- **Todas as datas calculadas a partir de D0 (`followup_start`)** — nunca da etapa anterior
  - D+2 = `followup_start + 2 dias`, D+5 = `followup_start + 5 dias`, D+7 = `followup_start + 7 dias`
- Arrastar entre sub-colunas persiste via `overrides.abordado_subcol` no localStorage + Supabase
- Ao arrastar, as etapas anteriores são marcadas automaticamente como enviadas em `followup_sent`
- O filtro **"Follow-up hoje"** cruza `followup_start` + sub-coluna atual + data real
- `CONCLUDED_STATUSES = ['ganhou', 'perdeu', 'agendado', 'sem_resposta', 'qualificado']` — leads nesses status não aparecem no filtro nem na régua
- `followup_start`, `followup_sent`, `loss_reason`, `needs_loss_reason` são salvos no Supabase e restaurados no `bootCloud`

---

## 12. Integração N8N × CRM — coexistência manual/automático

O N8N escreve diretamente no Supabase (campos `status`, `historico_resumido`, `is_bot`). O CRM detecta leads do N8N e exibe indicadores visuais.

### Campos-chave no estado do lead (localStorage + Supabase)

| Campo | Origem | Supabase | Descrição |
|---|---|---|---|
| `status` | CRM / N8N | ✅ sync | Status kanban atual |
| `notes` | CRM | ✅ sync | Notas do operador |
| `activity` | CRM | ✅ sync | Histórico de atividade |
| `overrides` | CRM | ✅ sync | Edições manuais + sub-coluna + controle manual |
| `followup_start` | CRM | ✅ sync | Timestamp (ms) do início da régua |
| `followup_sent` | CRM | ✅ sync | `{1: ts, 2: ts, 3: ts, 4: ts}` — etapas enviadas |
| `loss_reason` | CRM | ✅ sync | Motivo do lead perdido |
| `needs_loss_reason` | CRM | ✅ sync | Flag: motivo pendente de definição |
| `historico_resumido` | N8N | ✅ lê, nunca escreve | Resumo das interações do agente |
| `is_bot` | N8N / CRM | ✅ sync | Flag de automação |
| `score_conversacional` | N8N | ✅ lê, nunca escreve | Score de qualificação conversacional |

### Status do N8N e mapeamento para colunas kanban

| Status N8N | Coluna exibida |
|---|---|
| `qualificando` | Respondeu |
| `aguardando_decisor` | Respondeu |
| `aguardando_contato` | Respondeu |
| `desqualificado` | **Perdeu** (normalizado automaticamente) |

### Controle manual vs N8N

- Badge **🤖 Automático** → lead sendo gerido pelo N8N
- Badge **✋ Controle manual** → operador assumiu o lead
- Arrastar lead do N8N entre sub-colunas ativa `manual_control` automaticamente
- Botões "Devolver ao N8N" / "Tomar controle" na aba Follow-up do dossier
- Filtro **"👤 Minhas abordagens"** mostra apenas leads manuais (sem N8N ou com `manual_control`)

### Merge no bootCloud (local vence sobre cloud)
```javascript
state.leads[lid].overrides = { ...(c.overrides || {}), ...(state.leads[lid].overrides || {}) };
```
Garante que ações recentes do operador não sejam sobrescritas pelo Supabase.

---

## 13. Status `desqualificado` — normalização automática

Quando o N8N marca um lead como `desqualificado`:
1. Na carga do CRM, é convertido para `perdeu`
2. `needs_loss_reason = true` é setado
3. Popup automático abre com o histórico da conversa para o operador escolher o motivo real
4. Se fechar sem escolher → badge amarelo **"⚠️ Definir motivo da perda"** clicável no card
5. O campo "Motivo da perda" no dossier (header) é sempre editável via dropdown

### Motivos de perda disponíveis
- Desqualificado pelo agente
- Sem resposta após régua completa
- Não tem interesse no momento
- Já tem fornecedor/agência
- Preço / orçamento
- Não é o decisor
- Empresa inativa ou encerrada
- Outro (campo livre)

---

## 14. Campos de Instagram (pipeline + CRM)

### Campos adicionados pelo pipeline (`fase_instagram.py`)
| Campo | Fonte | Descrição |
|---|---|---|
| `instagram_local_url` | site scraping / Maps | URL do perfil da empresa |
| `instagram_dono_url` | Google + Instagram | URL do dono/CEO |
| `instagram_dono_nome` | meta og:title | Nome exibido no Instagram |
| `instagram_dono_bio` | meta og:description | Bio do perfil |
| `instagram_decisor_url` | Google + Instagram | URL do decisor/marketing |
| `instagram_decisor_nome` | meta og:title | Nome do decisor |
| `instagram_decisor_bio` | meta og:description | Bio do decisor |

### Edição manual no CRM
Na aba **Visão Geral** do dossier, botão **"Editar dados"** permite corrigir/complementar todos os campos acima, além de telefone, e-mail, site e nome do dono. Salvos como `overrides` em localStorage + Supabase.

---

## 15. CRM — onde cada coisa está

- **Kanban**: 7 colunas (Novo → Abordado → Respondeu → Agendado → Sem resposta → Ganhou → Perdeu)
- **Abordado**: 4 sub-colunas de follow-up (D0, D+2, D+5, D+7) — arrastar persiste
- **Filtros**: Instagram, WhatsApp, Dono, CNPJ, Anuncia Meta, E-mail, Follow-up hoje, Priority 70+, GMB Alta, Tráfego Alta, Nicho, Cidade, 👤 Minhas abordagens
- **Dossier**: 5 abas — Visão Geral, Rapport Humano, Ganchos de Dor, Follow-up, Atividade
- **Follow-up**: painel de controle N8N/manual, botões devolver/tomar controle, mensagens de cada etapa
- **Export CSV**: inclui e-mail, status, notas, motivo de perda, score conversacional, temperatura, sub-coluna e etapas enviadas
- **Gráficos**: funil de conversão (inclui status `qualificado`), motivos de perda, score de prioridade

---

## 16. Supabase

- Sincroniza todos os campos de trabalho do operador entre dispositivos
- Tabela: `leads` com campo `agencia = "Yonzza Digital"`
- Sync automático ao mudar status, adicionar nota, arrastar card ou salvar edição
- `cloudUpsertLead(leadId, { skipStatus: true })` — não sobrescreve status (usado quando N8N pode estar gerenciando o lead)
- `fase_sync_supabase.py` para sync manual completo do pipeline
- Schema completo em `supabase/schema.sql` — aplicar via `python setup_supabase.py`
- Projetos existentes: aplicar `supabase/migration_campos_crm.sql` no SQL Editor

### Campos sincronizados por `cloudUpsertLead`
`notes`, `activity`, `overrides`, `followup_start`, `followup_sent`, `loss_reason`, `needs_loss_reason`, `is_bot`, `novo_nesta_rodada`, e opcionalmente `status`.

### Campos lidos mas nunca escritos pelo CRM
`historico_resumido`, `score_conversacional` — escritos exclusivamente pelo N8N.

### Campos protegidos por `fase_sync_supabase.py` (Python nunca sobrescreve)
`status`, `notes`, `activity`, `overrides`, `followup_start`, `followup_sent`, `loss_reason`, `needs_loss_reason`, `is_bot`, `historico_resumido`, `score_conversacional`.

---

## 17. Regras importantes

1. **Nunca editar `index.html` diretamente** — editar sempre `template_crm.html` e rodar `build_html_v2.py`
2. **Nunca apagar os arquivos de cache** (wa_validado, email_validado, etc.)
3. **Sempre fixar o alias** após deploy: `npx vercel alias set [url].vercel.app invictus-prospect-yonzza.vercel.app`
4. **Offset de ID por nicho** — cada nicho ocupa 100 IDs. Nunca reutilizar faixas existentes
5. **merge_aviacao.py** é específico para nichos nacionais (sem filtro de DDD/estado)
6. **`cloudUpsertLead` com `skipStatus: true`** sempre que a ação é do operador sobre lead N8N (evita race condition)
7. **Local vence sobre cloud** no merge do bootCloud — ações recentes do operador têm prioridade
8. **`fmtDate(iso)`** formata data ISO completa (dd/mm/aaaa) — usar para `data_abertura` e datas de texto. **`fmtDateShort(ts)`** formata timestamp JS como DD/MM — usar no follow-up
9. **Schema novo projeto**: `python setup_supabase.py`. **Projeto existente**: aplicar `supabase/migration_campos_crm.sql` no SQL Editor do Supabase
10. **`CONCLUDED_STATUSES`** = `['ganhou', 'perdeu', 'agendado', 'sem_resposta', 'qualificado']` — leads nesses status não participam de régua nem do filtro "Follow-up hoje"

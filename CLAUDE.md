# CLAUDE.md — Invictus Prospect · Agência Yonzza Digital

Este arquivo é a memória permanente do projeto. Leia antes de qualquer ação.

---

## 1. O que é este projeto

Pipeline de prospecção B2B que extrai leads do Google Maps, enriquece com CNPJ/WA/Meta/e-mail, gera um CRM estático e faz deploy na Vercel.

**URL de produção:** https://invictus-prospect-yonzza.vercel.app  
**Domínio customizado:** https://agenciayonzza.com  
**Deploy:** `/tmp/vercel-local/node_modules/.bin/vercel --prod --yes --force`

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
extrator.py                 → fase 1: extrai leads do Google Maps
merge.py                    → fase 2: deduplica hamburguerias (SP, top 50)
merge_aviacao.py            → fase 2: deduplica aviação (Brasil, top 50)
fase_a_cnpj.py              → fase 3: busca CNPJ no site de cada lead
fase_b_brasilapi.py         → fase 4: enriquece CNPJ via BrasilAPI
fase_d_wa_validar.py        → fase 5: valida WhatsApp via Evolution API
fase_e_anuncia_real.py      → fase 6: verifica anúncios Meta via Playwright
fase_email.py               → fase 7: busca e-mails (RDAP + scraping + CNPJ)
fase_instagram.py           → fase 8a: busca Instagram local + dono/decisor via Google
consolidate_v2.py           → fase 8b: monta leads_final.json (multi-nicho)
build_html_v2.py            → fase 9: gera index.html com leads embutidos
template_crm.html           → fonte do CRM (nunca editar index.html direto)
servicos/                   → JSONs de configuração por nicho/serviço
servico_config.py           → lógica de scoring, rapport, ganchos, mensagens
leads_final.json            → saída consolidada (todos os nichos)
```

---

## 4. Arquivos de cache (não apagar)

```
wa_validado.json            → validações WhatsApp já feitas
anuncia_validado.json       → verificações Meta Ads já feitas
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

### O que o Claude faz (não precisa de ação do usuário):

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

### O que o usuário fornece:
- Nome do nicho
- Cidade ou região
- Contexto de mercado (Claude gera as mensagens)

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
python3 extrator.py
python3 merge.py
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py   # ← busca Instagram local + dono/decisor
python3 consolidate_v2.py
python3 build_html_v2.py
/tmp/vercel-local/node_modules/.bin/vercel --prod --yes --force
```

### Para aviação (merge nacional sem filtro DDD):
```bash
python3 extrator.py
python3 merge_aviacao.py    # ← usa este em vez do merge.py
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py   # ← busca Instagram local + dono/decisor
python3 consolidate_v2.py
python3 build_html_v2.py
/tmp/vercel-local/node_modules/.bin/vercel --prod --yes --force
```

**Depois do deploy, fixar o alias:**
```bash
/tmp/vercel-local/node_modules/.bin/vercel alias set [url-deploy].vercel.app invictus-prospect-yonzza.vercel.app
```

---

## 9. Régua de follow-up (implementada no CRM)

4 etapas automáticas ao mover lead para "Abordado":

| Etapa | Quando | Objetivo |
|---|---|---|
| 1 | Dia 0 | Abordagem inicial |
| 2 | D+2 | Novo ângulo (DOR) |
| 3 | D+5 | Verificação direta (sim/não) |
| 4 | D+7 | Saída honrosa |

Status especial **"Sem resposta"** separado de "Perdido".  
Ao mover para "Perdido" → popup de motivo (obrigatório).

---

## 10. Campos de Instagram (pipeline + CRM)

### Campos adicionados pelo pipeline (`fase_instagram.py`)
| Campo | Fonte | Descrição |
|---|---|---|
| `instagram_local_url` | site scraping / existing | URL do perfil da empresa |
| `instagram_dono_url` | Google + Instagram | URL do dono/CEO |
| `instagram_dono_nome` | meta og:title | Nome exibido no Instagram |
| `instagram_dono_bio` | meta og:description | Bio do perfil |
| `instagram_decisor_url` | Google + Instagram | URL do decisor/marketing |
| `instagram_decisor_nome` | meta og:title | Nome do decisor |
| `instagram_decisor_bio` | meta og:description | Bio do decisor |

### Edição manual no CRM
Na aba **Visão Geral** do dossier, botão **"Editar dados"** permite corrigir/complementar:
- Telefone, e-mail, site, nome do dono
- Instagram do local, dono (URL + nome + bio) e decisor (URL + nome + bio)

Os dados editados ficam salvos como **overrides** em localStorage e sincronizam com Supabase.  
O `consolidate_v2.py` preserva os campos de Instagram no merge incremental.

---

## 11. CRM — onde cada coisa está

- **Kanban**: 6 colunas (Novo → Abordado → Respondeu → Agendado → Sem resposta → Ganhou → Perdido)
- **Filtros**: Instagram, WhatsApp, Dono, CNPJ, Anuncia Meta, E-mail, Follow-up hoje, Priority 70+, GMB Alta, Tráfego Alta, Nicho, Cidade
- **Dossier**: 5 abas — Visão Geral, Rapport Humano, Ganchos de Dor, Follow-up, Atividade
- **Export CSV**: inclui e-mail, status, notas

---

## 11. Supabase

- Sincroniza status/notas/atividade entre dispositivos
- Tabela: `leads` com campo `agencia = "Yonzza Digital"`
- Sync automático ao mudar status ou adicionar nota
- `fase_sync_supabase.py` para sync manual completo

---

## 12. Regras importantes

1. **Nunca editar `index.html` diretamente** — editar sempre `template_crm.html` e rodar `build_html_v2.py`
2. **Nunca apagar os arquivos de cache** (wa_validado, email_validado, etc.) — levam horas para recriar
3. **Sempre fixar o alias** após deploy para garantir que `invictus-prospect-yonzza.vercel.app` aponta para a versão mais recente
4. **Offset de ID por nicho** — cada nicho ocupa 100 IDs. Nunca reutilizar faixas existentes
5. **merge_aviacao.py** é específico para nichos nacionais (sem filtro de DDD/estado)

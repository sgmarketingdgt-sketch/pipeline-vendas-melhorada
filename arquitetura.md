# Arquitetura — Invictus Prospect Template

## Visão geral

Pipeline de nove fases que transforma a entrada "segmento + cidade" em um CRM kanban navegável com 50 leads enriquecidos.

```
             INPUT: "certificado digital Belo Horizonte"
                            │
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 01                         │
 │  extrator.py → Google Places API                      │
 │  Roda N queries combinando segmento com sinônimos e   │
 │  cidades vizinhas. Captura: nome, endereço, telefone, │
 │  site, URL no Maps, rating, reviews, fotos, horário.  │
 │  SAÍDA: prospects/[DATA]_[QUERY].csv por query        │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 02                         │
 │  merge.py                                             │
 │  Lê todos os CSVs. Dedup por E.164 e nome. Filtro     │
 │  regional (DDD + endereço). Blacklist de termos fora  │
 │  do nicho. Ranqueia por score + recência.             │
 │  SAÍDA: leads_merged.csv (top 50)                     │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 03                         │
 │  fase_a_cnpj.py                                       │
 │  GET em cada site nas páginas /contato, /sobre,       │
 │  /politica-privacidade, rodapé da home. Regex         │
 │  captura CNPJ. Validação mínima (sem dígitos          │
 │  repetidos, sem sequência zero).                      │
 │  SAÍDA: cnpj_encontrados.json                         │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 04                         │
 │  fase_b_brasilapi.py                                  │
 │  Para cada CNPJ, consulta brasilapi.com.br. Extrai:   │
 │  razão social, data abertura, capital social, porte,  │
 │  CNAE, situação cadastral, QSA (quadro de sócios).    │
 │  SAÍDA: cnpj_enriquecidos.json                        │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 05                         │
 │  gerar_lotes_v2.py + cinco subagentes em paralelo     │
 │  Divide 50 leads em cinco lotes de dez.               │
 │  Cada subagente (general-purpose) lê o seu lote +     │
 │  dados das fases anteriores. Pesquisa:                │
 │  - Instagram (handle, bio, posts recentes)            │
 │  - Dono (se não veio do CNPJ: LinkedIn, Maps, site)   │
 │  - Contexto: tempo de mercado, nicho de cliente,      │
 │    bairro, equipe visível, tom de respostas no Maps   │
 │  - Separa rapport humano (conexão) de gancho de dor   │
 │    (observação comercial)                             │
 │  SAÍDA: lotes_v2/enriched_v2_[1-5].json               │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                   FASE 06 (opcional)                  │
 │  fase_d_wa_validar.py                                 │
 │  SSH para servidor com Evolution API self-hosted.     │
 │  Batch: verifica os 50 números E.164 de uma vez.      │
 │  API retorna {exists: true|false} por número.         │
 │  SAÍDA: wa_validado.json                              │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 07                         │
 │  fase_e_anuncia_real.py                               │
 │  Chromium headless via Playwright consulta a Meta     │
 │  Ad Library pública. Para cada lead, filtra por nome  │
 │  e conta quantos anúncios ativos estão rodando.       │
 │  Anti-detect: user-agent Chrome, webdriver undefined. │
 │  SAÍDA: anuncia_validado.json                         │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 08                         │
 │  consolidate_v2.py                                    │
 │  Merge FINAL: CSV + CNPJ + BrasilAPI + IA + WA +      │
 │  Meta. Normaliza campos. Calcula priority score       │
 │  ponderado (score GMN + qualidade pesquisa + bonus    │
 │  por WA ativo + bonus por dono + bonus por IG).       │
 │  Ordena por prioridade descendente.                   │
 │  SAÍDA: leads_final.json                              │
 └──────────────────────────┬──────────────────────────┘
                            ▼
 ┌──────────────────────────┴──────────────────────────┐
 │                       FASE 09                         │
 │  build_html_v2.py                                     │
 │  Lê template_crm.html + leads_final.json.             │
 │  Substitui placeholder __LEADS_DATA__ pelo JSON.      │
 │  SAÍDA: index.html (autocontido)                      │
 │                                                        │
 │  vercel --prod                                        │
 │  Deploy em CDN global. SAÍDA: https://[slug].vercel.app│
 └───────────────────────────────────────────────────────┘
```

## Stack por fase

| Fase | Tecnologia | Custo | Rate limit |
|------|------------|-------|------------|
| 01 — extrator | Python + requests + Google Places Text Search v1 | US$ 200/mês gratuitos | 600 req/min |
| 02 — merge | Python puro (csv, json) | Zero | N/A |
| 03 — scrape CNPJ | Python + requests + regex | Zero | Oito threads em paralelo |
| 04 — BrasilAPI | Python + requests + brasilapi.com.br | Zero | Três req/seg |
| 05 — rapport via IA | Claude Code (cinco subagentes paralelos) | Plano Claude Code atual | N/A |
| 06 — validar WhatsApp | Evolution API self-hosted + SSH | VPS (R$ 20 a R$ 30/mês) | N/A |
| 07 — Meta Ad Library | Playwright + Chromium headless | Zero | Delay de três a cinco segundos |
| 08 — consolidate | Python puro | Zero | N/A |
| 09 — build HTML | Python puro (substituição de template) | Zero | N/A |
| Deploy | Vercel no plano gratuito | Zero | Ilimitado para estático |

## Dados consumidos e produzidos por fase

```
FASE 01 consome: query (string), chave da Google Places API
FASE 01 produz:  N CSVs com 20 a 50 linhas cada

FASE 02 consome: todos os CSVs da Fase 01
FASE 02 produz:  um CSV consolidado com 50 linhas

FASE 03 consome: CSV da Fase 02 (campo `site`)
FASE 03 produz:  JSON com {id, nome, site, cnpj, pagina_origem}

FASE 04 consome: JSON da Fase 03 (campo `cnpj`)
FASE 04 produz:  JSON com dados completos da BrasilAPI

FASE 05 consome: JSONs das Fases 03 e 04 + CSV da Fase 02
FASE 05 produz:  cinco JSONs com rapport_humano, gancho_dor, Instagram
                 detalhado, anuncia_meta, etc

FASE 06 consome: CSV da Fase 02 (campo `whatsapp` E.164)
FASE 06 produz:  JSON com {id, numero, wa_ativo: bool, wa_name}

FASE 07 consome: CSV da Fase 02 (campo `nome`)
FASE 07 produz:  JSON com {id, anuncia_meta: sim|nao, meta_ads_count}

FASE 08 consome: TUDO acima
FASE 08 produz:  um JSON com 50 leads totalmente consolidados

FASE 09 consome: JSON da Fase 08 + template HTML
FASE 09 produz:  um index.html autocontido

Deploy  consome: index.html
Deploy  produz:  URL pública na Vercel
```

## Anatomia do HTML final

```
index.html (~220 KB)
│
├── <head>
│   ├── Tailwind CDN
│   ├── Sortable.js CDN
│   ├── Google Fonts (Plus Jakarta Sans + Inter + JetBrains Mono)
│   └── CSS custom (~6 KB: scrollbar, animações, chips, cards, dossiê)
│
├── <body>
│   ├── Topbar fixo (logo, breadcrumb, stats, search, ações)
│   ├── Filter bar sticky (chips, dropdown de cidade, contador)
│   ├── Kanban horizontal scroll (seis colunas de 320 px cada)
│   ├── Dossier slide-in à direita (50 vw, quatro abas)
│   ├── Command palette modal (Cmd K ou Ctrl K)
│   ├── Confirm modal (reset)
│   └── Toast
│
├── <script>const LEADS = {...180 KB de dados...};</script>
├── <script src="sortable.min.js"></script>
└── <script>(function() { ...app JS 20 KB... })();</script>
```

## Estado persistido no localStorage

Chave: `ethos_crm_bh_2026_04_22` (renomeie conforme sua execução).

```json
{
  "leads": {
    "1": { "status": "novo", "notes": [], "activity": [] },
    "2": {
      "status": "abordado",
      "notes": [{"t": 1730000000000, "text": "..."}],
      "activity": [{"t": 1730000000000, "type": "status", "msg": "..."}]
    }
  },
  "theme": "dark"
}
```

## Fluxo de interação do usuário

```
1. Usuário abre o CRM pela primeira vez
   → loadState() retorna initialState() (todos em "Novo")
   → renderHeaderStats() + renderKanban()

2. Usuário arrasta um card de "Novo" para "Abordado"
   → Sortable.js dispara onEnd
   → state.leads[id].status = "abordado"
   → activity.unshift({type: "status", msg: "movido..."})
   → saveState()
   → toast()

3. Usuário clica no card
   → openDossier(leadId) com animação slide-in
   → renderiza as quatro abas
   → aba padrão: Visão Geral

4. Usuário clica no botão WhatsApp
   → abre wa.me/NUMERO em nova aba (sem mensagem pré-preenchida)
   → activity.unshift({type: "wa", msg: "WhatsApp aberto"})
   → saveState()

5. Usuário digita nota na aba Atividade
   → notes.unshift({t: now, text})
   → saveState()
   → renderDossierBody()

6. Usuário aperta Cmd K (ou Ctrl K)
   → openPalette()
   → input ganha foco
   → lista mostra três ações rápidas + até 20 leads filtrados

7. Usuário digita "marcelo" na palette
   → filtra leads em tempo real (match em nome, dono, bairro, nicho)
   → setas navegam
   → Enter abre o lead selecionado

8. Usuário clica em Export CSV
   → gera blob com 14 colunas (id, nome, dono, cnpj, cidade, telefone,
     wa, wa_ativo, ig, site, status, notas, score)
   → download forçado
```

## Metas de qualidade por fase

| Fase | Métrica | Meta |
|------|---------|------|
| 01 | Empresas brutas | 80 a 120 |
| 02 | Leads filtrados (regional + nicho) | 50 ou mais |
| 03 | Taxa de CNPJ encontrado | 40 a 60 por cento |
| 04 | Taxa BrasilAPI com sucesso | 80 a 95 por cento |
| 05 | Leads com três ou mais pontos de rapport | 90 por cento ou mais |
| 05 | Leads com dono identificado | 50 por cento ou mais |
| 06 | Taxa de WhatsApp real | 70 por cento ou mais |
| 07 | Taxa de confirmação do Playwright | 90 por cento ou mais |
| 08 | Tamanho do `leads_final.json` | 100 a 300 KB |
| 09 | Tamanho do `index.html` | 150 a 300 KB |
| 09 | Tempo de carregamento | Abaixo de dois segundos |
| Deploy | Tempo total | Abaixo de 30 segundos |

## Extensões possíveis

- Google Search SERP via Playwright com proxies rotativos (para checar anúncios Google).
- Bulk actions no CRM (seleção múltipla + mover em lote).
- Tab "Relatório" com funil de conversão entre colunas.
- Sincronização entre dispositivos via Supabase no free tier (opt-in).
- Replicar em outras cidades ou nichos (trocar apenas o `PROMPT.md` e rerodar).
- Importação manual de leads fora do Google Maps.
- Relatórios agregados: taxa de conversão por status, tempo médio no pipeline, top leads mais movimentados.

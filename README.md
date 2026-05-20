# Invictus Prospect Template

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Powered by Claude Code](https://img.shields.io/badge/powered%20by-Claude%20Code-D97757)](https://claude.ai/code)
[![Supabase](https://img.shields.io/badge/sync-Supabase-3ECF8E)](https://supabase.com)
[![Playwright](https://img.shields.io/badge/playwright-Chromium-2EAD33)](https://playwright.dev/python/)

Pipeline de prospecção B2B executado pelo Claude Code. Você descreve um
segmento e uma cidade — o pipeline roda dez fases encadeadas (Google Places,
dedup, CNPJ, BrasilAPI, WhatsApp, Meta Ads, e-mail, Instagram,
consolidação e deploy) e entrega um CRM kanban estático com sync opcional
via Supabase.

> **Demo pública**: https://invictus-prospect-template.vercel.app

## Por que este projeto existe

Prospecção B2B boa exige juntar dados de várias fontes, validar sinais
(WhatsApp ativo? anuncia? quem é o dono? qual o Instagram do decisor?) e
ainda manter um pipeline humano de follow-up. Fazer isso na mão consome
horas. Plataformas que prometem automatizar tudo cobram caro e travam você
no formato delas.

Este template é o caminho do meio: você roda no Claude Code, em qualquer
nicho, com seus próprios dados, e fica dono de tudo. Sem mensalidade, sem
trava, sem multi-tenancy. Open source MIT.

## Quickstart

```bash
git clone https://github.com/sgmarketingdgt-sketch/pipeline-vendas-melhorada
cd pipeline-vendas-melhorada
./setup.sh          # Windows: powershell -ExecutionPolicy Bypass -File .\setup.ps1
# Edite o .env com sua chave Google Places (e opcional Supabase)
claude < PROMPT.md
```

O `setup.sh` cria a venv, instala dependências, baixa o Chromium do
Playwright e prepara o `.env`. Em seguida, edite o `PROMPT.md` substituindo
`[AGENCIA]`, `[SEGMENTO]`, `[CIDADE]` e `[ABRANGENCIA]` pelo seu recorte e
cole o arquivo no Claude Code.

## Como funciona

```
   Google Places API (Places API New)
          ↓
  merge.py / merge_aviacao.py    (dedup + filtro regional ou nacional)
          ↓
    fase_a_cnpj.py               (CNPJ via scraping de rodapé)
          ↓
   fase_b_brasilapi.py           (razão social, sócios, porte)
          ↓
  fase_d_wa_validar.py           (Evolution API — opcional)
          ↓
  fase_e_anuncia_real.py         (Playwright: Meta Ad Library + Google Ads)
          ↓
      fase_email.py              (RDAP/WHOIS + scraping + CNPJ)
          ↓
   fase_instagram.py             (Instagram empresa + dono + decisor)
          ↓
   consolidate_v2.py             → leads_final.json
          ↓
  fase_sync_supabase.py          (incremental — opcional)
          ↓
    build_html_v2.py             → index.html (CRM kanban)
          ↓
      npx vercel --prod          → URL privada do CRM
```

Cada fase é um script Python independente. Você pode rodá-las isoladas para
debugar, ou deixar o Claude Code orquestrar tudo via `PROMPT.md`.

Para nichos nacionais (sem filtro de estado), use `merge_aviacao.py` no
lugar de `merge.py` na Fase 02.

## CRM incluso

O `build_html_v2.py` gera um `index.html` único e autocontido com todos os
leads embutidos. Recursos:

- **Kanban** com 7 colunas: Novo, Abordado, Respondeu, Qualificado, Agendado, Sem Resposta, Ganhou, Perdeu
- **Abordado** dividido em 4 sub-colunas de follow-up: D0, D+2, D+5, D+7 (datas sempre calculadas a partir do D0)
- **Dossiê** com 5 abas: Visão Geral, Rapport Humano, Ganchos de Dor, Follow-up, Atividade
- **Score de Perfil** (calculado pelo pipeline) + **Score Conversacional** (gravado pelo N8N após interações)
- **Régua de follow-up** automática com filtro "Follow-up hoje" cruzando data real
- **Integração N8N**: badges automático/manual, painel de controle por lead, normalização de status
- **Filtros** combináveis: Instagram, WhatsApp, Dono, CNPJ, Anuncia Meta, E-mail, Follow-up hoje, Priority 70+, GMB Alta, Tráfego Alta, Nicho, Cidade, Minhas abordagens
- **Export CSV** com status, notas, motivo de perda, score, temperatura, sub-coluna e etapas de follow-up enviadas
- **Funil de conversão**, gráfico de motivos de perda e distribuição de score
- Drag-and-drop entre colunas e sub-colunas com persistência automática
- Command palette `Cmd+K` / `Ctrl+K` para busca instantânea
- Edição manual de qualquer campo do lead (telefone, e-mail, Instagram, dono) com badge de dado editado
- Tema dark/light alternável, mobile responsivo

## Modo incremental (Supabase)

Na primeira execução, todos os leads entram com `status = "novo"`. Da
segunda em diante, o pipeline:

- Identifica leads já existentes via CNPJ → WhatsApp → nome normalizado
- Atualiza apenas campos voláteis (nota Maps, contagem Meta Ads, ângulo de abordagem)
- **Preserva** todo o trabalho do operador: status, notas, atividade, follow-up, overrides, motivo de perda
- Marca leads novos com badge "Novo" e leads que sumiram da extração com badge "NÃO VISTO"
- Registra cada rodada em `execucoes` (consultável no header do CRM)

Sem Supabase configurado, o CRM opera 100% local via localStorage. Com
Supabase, ganha sync entre dispositivos — rode o pipeline no laptop,
acompanhe pelo celular.

Cada usuário cria o próprio projeto Supabase grátis. Sem multi-tenancy e
sem servidor compartilhado. Veja o passo a passo em
[`supabase/README.md`](supabase/README.md).

Para projetos novos: `python3 setup_supabase.py`.
Para projetos existentes: aplique `supabase/migration_campos_crm.sql` no
SQL Editor do Supabase.

## Stack

- **Python 3.10+** — pipeline (requests, python-dotenv, Playwright, BeautifulSoup4)
- **Claude Code** — orquestrador do pipeline via `PROMPT.md`
- **HTML estático autocontido** — CRM sem build step, sem framework
- **Tailwind via CDN**, **Sortable.js via CDN**, **supabase-js via CDN**
- **Plus Jakarta Sans + Inter** via Google Fonts
- **Supabase** — sync entre dispositivos e modo incremental (opcional)
- **Evolution API** — validação real de WhatsApp (opcional)
- **N8N** — agente de qualificação automática por WhatsApp (opcional)
- **Vercel** — hospedagem do CRM gerado (opcional)

## Customização

O `PROMPT.md` tem quatro variáveis principais:

```
[AGENCIA]      — sua marca, aparece no header e no CSV exportado
[SEGMENTO]     — academias, clínicas, escolas, advocacia, restaurantes...
[CIDADE]       — qualquer cidade brasileira, ou "Brasil" para nichos nacionais
[ABRANGENCIA]  — local (usa merge.py) ou nacional (usa merge_aviacao.py)
```

Funciona para qualquer nicho presente no Google Maps. Segmentos testados ou
viáveis: hamburguerias, escolas de aviação, certificadoras digitais,
oftalmologistas, clínicas odontológicas e veterinárias, autoescolas,
estúdios de pilates, buffets, advogados, contadores, oficinas, salões de
beleza.

Para adicionar um novo nicho sem perder os leads dos nichos existentes,
veja a seção "Como adicionar um novo nicho" no `CLAUDE.md`.

Para mudar a paleta visual, edite `template_crm.html` (configuração
Tailwind no topo) e rode `build_html_v2.py` para gerar o `index.html`.
**Nunca edite o `index.html` diretamente.**

## Limitações conhecidas

- **Google Ads Transparency Center**: a verificação pública é opcional para
  anunciantes não políticos no Brasil, então `anuncia_google` será `nao`
  na maioria dos casos. Não é falso negativo: a fonte é incompleta por
  design.
- **Validação WhatsApp**: depende de instância Evolution API auto-hospedada.
  Sem ela, o campo fica em branco e o CRM exibe "não verificado".
- **Playwright**: requer Chromium instalado localmente (aprox. 200 MB). O
  `setup.sh` faz isso automaticamente.
- **Custo Google Places**: cada query consome quota da API. Comece com
  cidades menores e nichos específicos para calibrar o gasto antes de
  escalar.

## Roadmap

- v1.1 — busca SERP via Playwright como complemento ao Google Places
- v1.2 — modo "campanha" com cohorts de leads e métricas de conversão por rodada
- v1.3 — exportação direta para CRMs externos (Pipedrive, HubSpot, Notion)

Sugestões? Abra uma issue.

## Contribuir

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para o guia completo. Em resumo:

- Issue antes de PR grande, PR direto para fix óbvio.
- PT-BR com acentuação, sem emoji, sem travessão.
- Lint passa (`flake8`).
- Não commite dados de cliente nem `.env`.

## Licença

[MIT](LICENSE). Use, adapte, cobre pela execução para seus clientes se
quiser. Pede-se apenas manter o crédito em algum lugar do entregável.

---

Licença MIT.

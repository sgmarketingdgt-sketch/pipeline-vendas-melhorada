# PROMPT raiz — Pipeline de prospecção B2B com Claude Code

Este é o prompt parametrizável do Invictus Prospect Template. Substitua as variáveis do bloco abaixo pelo seu recorte e cole o arquivo inteiro no Claude Code. Ele executa as dez fases em ordem e entrega um CRM kanban no final.

## Variáveis a substituir

- `[AGENCIA]` — nome da sua operação (ex: "Ethos Growth", ou só o seu nome).
- `[SEGMENTO]` — qualquer nicho local (ex: "certificado digital", "academias", "clínicas odontológicas", "escolas de curso livre", "restaurantes vegetarianos", "escritórios de advocacia").
- `[CIDADE]` — qualquer cidade brasileira (ex: "Belo Horizonte", "Curitiba", "Recife", "São José dos Campos", "Porto Alegre"). Para nichos nacionais, use "Brasil".
- `[ABRANGENCIA]` — `local` para nichos de uma cidade (usa `merge.py` com filtro de DDD) ou `nacional` para nichos sem filtro regional (usa `merge_aviacao.py`).

Opcionais:

- `[REGIAO_EVITAR]` — cidade/região que não deve ser prospectada (normalmente a matriz de um cliente seu, para evitar conflito). Se não há, deixe "nenhuma".
- `[URL_VERCEL]` — slug da URL final no Vercel (ex: "leads-odonto-curitiba"). Se não tiver preferência, o Claude Code gera um nome.

---

## Prompt a colar no Claude Code

Você é um engenheiro de dados sênior. Vou pedir para você executar um pipeline de prospecção B2B em dez fases, escrito em Python.

Contexto do pedido:

- Agência: `[AGENCIA]`
- Segmento alvo: `[SEGMENTO]`
- Cidade/região alvo: `[CIDADE]`
- Abrangência: `[ABRANGENCIA]`
- Região a evitar: `[REGIAO_EVITAR]`
- Meta: 50 leads qualificados e organizados em um CRM kanban gerado estaticamente.

Execute as dez fases na ordem a seguir. Entre cada uma, apresente um resumo curto do que saiu (quantos leads, taxa de acerto, erros encontrados). Se algo falhar, investigue antes de prosseguir.

### Fase 01 — Extração via Google Places

Use `extrator.py` (wrapper sobre Google Places Text Search v1 — Places API New).

Rode entre oito e doze queries para ampliar a base. Combine o segmento com sinônimos e, se abrangência for local, com cidades vizinhas:

```bash
python3 extrator.py "[SEGMENTO] [CIDADE]"
python3 extrator.py "[SEGMENTO_SINONIMO_1] [CIDADE]"
python3 extrator.py "[SEGMENTO_SINONIMO_2] [CIDADE]"
python3 extrator.py "[SEGMENTO] [CIDADE_VIZINHA_1]"   # apenas se abrangência local
python3 extrator.py "[SEGMENTO] [CIDADE_VIZINHA_2]"   # apenas se abrangência local
```

Objetivo: entre 80 e 120 empresas brutas. Os CSVs ficam salvos em `prospects/`.

### Fase 02 — Dedup e filtro regional

Se abrangência for **local**, rode `merge.py`. Se for **nacional**, rode `merge_aviacao.py`.

Ambos fazem:
- Leitura de todos os CSVs da pasta `prospects/`.
- Dedup por telefone no formato E.164 e por nome.
- Ranqueamento por score do Google Maps e por recência de reviews.
- Saída: top 50 em `leads_merged.csv`.

O `merge.py` aplica adicionalmente:
- Filtro por DDD e endereço para manter apenas leads do estado alvo.
- Blacklist de termos fora do nicho (receita federal, prefeitura, repartição pública, etc).

Ajuste em `merge.py` quando necessário:
- `NICHE_TERMS` com termos que aparecem no nome das empresas do segmento.
- `BLACKLIST_TERMS` com termos a evitar.
- `MG_DDDS` com os DDDs do estado alvo.

### Fase 03 — Extração de CNPJ

Rode `fase_a_cnpj.py`. Para cada lead com site, faz GET em:

`/`, `/contato`, `/sobre`, `/sobre-nos`, `/quem-somos`, `/politica-privacidade`, `/politica-de-privacidade`, `/termos`, `/termos-de-uso`, `/empresa`.

Regex: `\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}`. Valida CNPJ minimamente (não aceita sequência de zeros nem dígitos repetidos).

Saída: `cnpj_encontrados.json`. Taxa de acerto típica: 40 a 60 por cento.

### Fase 04 — Enriquecimento via BrasilAPI

Rode `fase_b_brasilapi.py`. Para cada CNPJ, consulta `https://brasilapi.com.br/api/cnpj/v1/{CNPJ}`.

Extrai: razão social, nome fantasia, data de início de atividade, capital social, porte, CNAE principal, situação cadastral e QSA (quadro de sócios e administradores).

Saída: `cnpj_enriquecidos.json`. Rate limit confortável com três threads em paralelo: 16 a 19 CNPJs por minuto.

### Fase 05 — Validação real de WhatsApp (opcional)

Se houver uma Evolution API self-hosted configurada no `.env` (`EVOLUTION_API_URL` e `EVOLUTION_API_KEY`), rode `fase_d_wa_validar.py`. Ele consulta todos os números de uma vez no endpoint `/chat/whatsappNumbers/[INSTANCIA]` e retorna, para cada número, `exists: true|false` e nome do perfil quando disponível.

Saída: `wa_validado.json`. Se não houver Evolution API, pule esta fase — o CRM exibirá "não verificado" no campo e os leads ainda aparecem normalmente.

### Fase 06 — Checagem de anúncios Meta e Google via Playwright

Rode `fase_e_anuncia_real.py`. Abre um Chromium headless via Playwright e, para cada lead:

- Consulta a Meta Ad Library pública (`facebook.com/ads/library/`) com filtros `active_status=active&country=BR&q=[NOME]` e captura a contagem real de anúncios ativos.
- Verifica presença no Google Ads Transparency Center (`adstransparency.google.com`) usando `networkidle` + detecção de texto antes de seletores CSS (o site é SPA React).

Saída: `anuncia_validado.json`. Leads com resultado incerto (`google_metodo` começando com `fallback_`) são reprocessados automaticamente na próxima execução.

### Fase 07 — Busca de e-mails

Rode `fase_email.py`. Para cada lead, busca e-mail em três fontes em ordem de confiança:

1. **RDAP/WHOIS** — consulta o domínio do site via `rdap.registro.br` (retorna responsável técnico/administrativo).
2. **Scraping do site** — varre o site e subpáginas de contato buscando padrões de e-mail.
3. **Dados do CNPJ** — extrai e-mail registrado na Receita Federal via BrasilAPI.

Saída: `email_validado.json`. O campo `email_fonte` indica a origem (`registrobr_rdap`, `site_scraping` ou `cnpj_receita`). Taxa de acerto típica: 30 a 50 por cento.

### Fase 08 — Busca de Instagram e decisores

Rode `fase_instagram.py`. Para cada lead, busca em duas etapas:

1. **Instagram da empresa** — via scraping do site próprio e via `socialMediaLinks` do Google Maps (capturado na Fase 01). Salva URL do perfil.
2. **Instagram do dono e do decisor de marketing** — busca no Google combinando nome da empresa + sócios do CNPJ + termos como "CEO", "sócio", "fundador", "marketing". Extrai nome, URL e bio via meta tags `og:title` / `og:description`.

Saída: `instagram_validado.json`. Campos gravados: `instagram_local_url`, `instagram_dono_url`, `instagram_dono_nome`, `instagram_dono_bio`, `instagram_decisor_url`, `instagram_decisor_nome`, `instagram_decisor_bio`.

### Fase 09 — Consolidação

Rode `consolidate_v2.py`. Faz o merge final de todas as fases anteriores em `leads_final.json`:

- Une extração, CNPJ, WhatsApp, anúncios, e-mail e Instagram por ID de lead.
- Deriva dono a partir do QSA do CNPJ (filtra PJ, holdings e sócios com participação abaixo de 5%).
- Calcula `priority_score` ponderado: nota Maps, avaliações, WhatsApp ativo, dono identificado, Instagram localizado, anuncia Meta/Google.
- Gera rapport humano e ganchos de dor a partir da configuração do serviço (`servicos/[SERVICO].json`).
- Comportamento incremental: leads com trabalho feito no CRM (status, notas, follow-up) são preservados. Leads novos entram com badge "Novo". Leads que sumiram da extração ficam com badge "NÃO VISTO".
- Outros nichos no `leads_final.json` são sempre preservados intactos.

### Fase 09a — Sync incremental no Supabase (opcional)

Se o `.env` tiver `SUPABASE_URL`, `SUPABASE_ANON_KEY` e `AGENCIA` preenchidos, rode `fase_sync_supabase.py`:

- Identifica leads já existentes no Supabase (match por CNPJ → WhatsApp → nome normalizado).
- Insere apenas leads realmente novos, com `first_seen_at = now()`.
- Atualiza somente campos voláteis dos existentes (sinais Maps, contagem Meta Ads, mensagem WA, ângulo). Nunca sobrescreve status, notas, atividade, follow-up ou dados do operador.
- Registra a rodada em `execucoes` (visível no header do CRM).

Se o projeto Supabase ainda não foi configurado, execute primeiro `python3 setup_supabase.py` (aplica o `supabase/schema.sql`). Sem Supabase configurado, pule esta fase: o CRM opera 100% via localStorage automaticamente.

### Fase 10 — Build HTML e deploy

Rode `build_html_v2.py`. Substitui os placeholders no `template_crm.html` (dados dos leads, URL Supabase, agência) e gera `index.html`.

Deploy na Vercel:

```bash
npx vercel --prod --yes --force
npx vercel alias set [url-gerada].vercel.app [URL_VERCEL].vercel.app
```

Na primeira execução o Vercel cria o projeto. Nas seguintes, é só redeploy. O alias garante que a URL não muda entre deploys.

---

## O que o CRM entrega

- **Kanban** com 7 colunas: Novo → Abordado → Respondeu → Qualificado → Agendado → Sem Resposta → Ganhou → Perdeu.
- **Abordado** dividido em 4 sub-colunas de follow-up: D0 · D+2 · D+5 · D+7 (todas calculadas a partir do D0, nunca da etapa anterior).
- **Dossiê** com 5 abas: Visão Geral, Rapport Humano, Ganchos de Dor, Follow-up, Atividade.
- **Filtros** combináveis: Instagram, WhatsApp real, Com dono, CNPJ, Anuncia Meta, E-mail, Follow-up hoje, Priority 70+, GMB Alta, Tráfego Alta, Nicho, Cidade, Minhas abordagens.
- **Score de Perfil** (priority_score) + **Score Conversacional** (gravado pelo N8N após interações).
- **Export CSV** com status, notas, motivo de perda, score, temperatura, sub-coluna e etapas enviadas.
- **Funil de conversão**, gráfico de motivos de perda e distribuição de score.
- Drag-and-drop entre colunas e sub-colunas (Sortable.js via CDN).
- Estado persistido em localStorage + Supabase (sync entre dispositivos quando configurado).
- Integração com agente N8N: badges automático/manual, painel de controle por lead, normalização de status.

---

## Requisitos técnicos

- Python 3.10 ou superior com `requests`, `playwright`, `python-dotenv`.
- Chave da Google Places API com Places API (New) ativada (US$ 200 de crédito gratuito por mês cobrem o uso típico).
- Playwright instalado: `pip install playwright` e `python -m playwright install chromium`.
- Node.js + `npx` para o deploy na Vercel.
- Claude Code autenticado no seu plano.
- Opcional: Evolution API self-hosted para validação real de WhatsApp.
- Opcional: projeto Supabase para sync entre dispositivos.

---

## Metas de qualidade por execução

- 50 leads consolidados, todos da região alvo.
- 40% ou mais com CNPJ identificado.
- 25% ou mais com dono identificado via QSA ou Instagram.
- 50% ou mais com Instagram da empresa localizado.
- 30% ou mais com e-mail encontrado.
- 70% ou mais com WhatsApp validado (se rodou a Fase 05).

Se bater esse alvo, a entrega está no padrão. Abaixo disso, vale reextrair com queries adicionais na Fase 01.

---

## Observações finais

- **Nunca edite `index.html` diretamente** — edite sempre `template_crm.html` e rode `build_html_v2.py`.
- Rapport humano e gancho comercial são campos separados e não se misturam. Rapport é conexão (bairro, tempo de mercado, cultura). Gancho é observação dura (site sem SSL, reviews sem resposta, Instagram parado).
- Se a Fase 06 falhar por bloqueio da Meta, repita com delays maiores. Se persistir, o lead fica marcado como "não verificado" — não bloqueia o restante.
- Para nichos nacionais (sem filtro de DDD/estado), sempre use `merge_aviacao.py` na Fase 02 em vez de `merge.py`.
- Cada nicho ocupa uma faixa de 100 IDs no `consolidate_v2.py`. Nunca reutilize faixas existentes ao adicionar um novo nicho.

---

Licença MIT.

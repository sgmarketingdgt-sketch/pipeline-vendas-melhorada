# PROMPT raiz — Pipeline de prospecção B2B com Claude Code

Este é o prompt parametrizável do Invictus Prospect Template. Substitua as três variáveis do bloco abaixo pelo seu recorte e cole o arquivo inteiro no Claude Code. Ele executa as nove fases em ordem e entrega um CRM kanban no final.

## Três variáveis a substituir

- `[AGENCIA]` — nome da sua operação (ex: "Ethos Growth", ou só o seu nome).
- `[SEGMENTO]` — qualquer nicho local (ex: "certificado digital", "academias", "clínicas odontológicas", "escolas de curso livre", "restaurantes vegetarianos", "escritórios de advocacia").
- `[CIDADE]` — qualquer cidade brasileira (ex: "Belo Horizonte", "Curitiba", "Recife", "São José dos Campos", "Porto Alegre").

Opcionais:

- `[REGIAO_EVITAR]` — cidade/região que não deve ser prospectada (normalmente a matriz de um cliente seu, para evitar conflito). Se não há, deixe "nenhuma".
- `[URL_VERCEL]` — slug da URL final no Vercel (ex: "leads-odonto-curitiba"). Se não tiver preferência, o Claude Code gera um nome.

---

## Prompt a colar no Claude Code

Você é um engenheiro de dados sênior. Vou pedir para você executar um pipeline de prospecção B2B em nove fases, escrito em Python e com suporte do Claude Code (subagentes `general-purpose` em paralelo para a parte de IA).

Contexto do pedido:

- Agência: `[AGENCIA]`
- Segmento alvo: `[SEGMENTO]`
- Cidade alvo: `[CIDADE]`
- Região a evitar: `[REGIAO_EVITAR]`
- Meta: 50 leads qualificados e organizados em um CRM kanban gerado estaticamente.

Execute as nove fases na ordem a seguir. Entre cada uma, apresente um resumo curto do que saiu. Se algo falhar, investigue antes de prosseguir.

### Fase 01 — Extração via Google Places

Use o extrator Python disponível no template (`extrator.py` — um wrapper sobre Google Places Text Search v1).

Rode entre oito e doze queries para ampliar a base. Combine o segmento com sinônimos e cidades vizinhas, por exemplo:

```bash
python extrator.py "[SEGMENTO] [CIDADE]"
python extrator.py "[SEGMENTO_SINONIMO_1] [CIDADE]"
python extrator.py "[SEGMENTO_SINONIMO_2] [CIDADE]"
python extrator.py "[SEGMENTO] [CIDADE_VIZINHA_1]"
python extrator.py "[SEGMENTO] [CIDADE_VIZINHA_2]"
```

Objetivo: entre 80 e 120 empresas brutas. Os CSVs ficam salvos em `prospects/`.

### Fase 02 — Dedup e filtro regional

Rode `merge.py`. Ele faz:

- Leitura de todos os CSVs da pasta `prospects/`.
- Dedup por telefone no formato E.164 e por nome.
- Filtro por DDD e endereço para manter apenas leads do estado alvo.
- Blacklist de termos fora do nicho (receita federal, prefeitura, repartição pública, etc).
- Ranqueamento por score do Google Maps e por recência de reviews.
- Saída: top 50 em `leads_merged.csv`.

Ajuste em `merge.py`:

- `NICHE_TERMS` com termos que aparecem no nome de empresas do segmento.
- `BLACKLIST_TERMS` com termos a evitar.
- `MG_DDDS` com os DDDs do estado alvo. Renomeie para `ESTADO_DDDS` se quiser.

### Fase 03 — Extração de CNPJ

Rode `fase_a_cnpj.py`. Para cada lead com site, ele faz GET em:

- `/`, `/contato`, `/sobre`, `/sobre-nos`, `/quem-somos`, `/politica-privacidade`, `/politica-de-privacidade`, `/termos`, `/termos-de-uso`, `/empresa`.

Regex: `\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}`. Valida CNPJ minimamente (não pode ser sequência de zeros nem dígitos repetidos).

Saída: `cnpj_encontrados.json`. Taxa de acerto típica: 40 a 60 por cento.

### Fase 04 — Enriquecimento via BrasilAPI

Rode `fase_b_brasilapi.py`. Para cada CNPJ, consulta `https://brasilapi.com.br/api/cnpj/v1/{CNPJ}`.

Extrai: razão social, nome fantasia, data de início de atividade, capital social, porte, CNAE principal, situação cadastral, e QSA (quadro de sócios). Saída: `cnpj_enriquecidos.json`.

Rate limit confortável com três threads em paralelo. 16 a 19 CNPJs por minuto.

### Fase 05 — Pesquisa de contexto via IA

Rode `gerar_lotes_v2.py` para dividir os 50 leads em cinco lotes de dez.

Em seguida, no Claude Code, dispare cinco subagentes `general-purpose` em paralelo, um para cada lote. O prompt de cada subagente pesquisa:

1. Instagram: handle, bio, três a cinco posts recentes com data, tema e tipo (humano, comercial ou institucional), frequência de postagens.
2. Dono: se o `socios_cnpj` já veio preenchido, usa o primeiro. Caso contrário, busca em bio do Instagram, respostas a reviews no Google Maps, página "sobre" do site, LinkedIn.
3. Contexto humano: tempo de mercado calculado pela data de abertura, nicho de cliente principal inferido (MEI, contador, advogado etc), bairro de atuação, equipe visível, tom das respostas em reviews no Maps.
4. Anúncios: `anuncia_google` (heurística via Google Search) e `anuncia_meta` (checagem via Meta Ad Library, marcado como "nao_verificado" se o scraping cair em proteção anti-bot — a validação objetiva acontece na Fase 07).
5. Separação estrita entre `rapport_humano[]` (três a quatro fatos de conexão humana) e `gancho_dor[]` (duas a três observações comerciais duras). Sem misturar os dois. Sem escrever mensagens.

Cada subagente salva o enriquecimento do seu lote em `lotes_v2/enriched_v2_X.json`.

### Fase 06 — Validação real de WhatsApp (opcional)

Se houver uma Evolution API self-hosted rodando, execute `fase_d_wa_validar.py`. Ele faz uma chamada SSH ao servidor e consulta todos os números de uma vez no endpoint `/chat/whatsappNumbers/[INSTANCIA]`. Retorna, para cada número, `exists: true|false` e nome do perfil, quando disponível.

Saída: `wa_validado.json`. Se não houver Evolution API, pule esta fase. O CRM exibirá "não verificado" no campo.

### Fase 07 — Checagem de anúncios no Meta via Playwright

Rode `fase_e_anuncia_real.py`. Ele abre um Chromium headless via Playwright e, para cada lead, consulta a Meta Ad Library pública em `https://www.facebook.com/ads/library/` com filtros `active_status=active&country=BR&q=[NOME]`.

Captura a contagem real de anúncios ativos de cada empresa no momento da execução. Saída: `anuncia_validado.json`. Taxa de confirmação típica sem bloqueio: 100 por cento.

### Fase 08 — Consolidação

Rode `consolidate_v2.py`. Ele faz o merge final de todas as fases anteriores em `leads_final.json`. Normaliza campos, calcula um `priority_score` ponderado (score do Google Maps, qualidade da pesquisa humana, WhatsApp ativo, dono identificado, Instagram localizado) e ordena os leads por prioridade decrescente.

### Fase 08a — Sync incremental no Supabase (opcional)

Se o `.env` tiver `SUPABASE_URL`, `SUPABASE_ANON_KEY` e `AGENCIA` preenchidos, rode `fase_sync_supabase.py`. Ele garante o comportamento incremental:

- Identifica leads já existentes no Supabase (match por CNPJ, depois telefone, depois nome normalizado).
- Insere apenas os leads realmente novos.
- Atualiza somente campos voláteis dos existentes (sinais Maps, contagem Meta Ads, último visto). Nunca sobrescreve status, notas, atividade ou rapport.
- Registra a rodada em `execucoes` (consultável no header do CRM).
- Atualiza o `leads_final.json` local com a flag `novo_nesta_rodada`, usada pelo CRM para o badge "Novo" e pelo filtro "Novos nesta rodada".

Se o usuário ainda não criou o projeto Supabase, execute primeiro `setup_supabase.py` (que aplica o `supabase/schema.sql`). Sem Supabase configurado, pule esta fase: o CRM cai para localStorage automaticamente.

### Fase 09 — Build HTML e deploy

Rode `build_html_v2.py`. Ele substitui o placeholder `__LEADS_DATA__` no `template_crm.html` pelo JSON embutido e gera `index.html`.

Em seguida, deploy na Vercel:

```bash
cd pasta-do-projeto
vercel --prod --yes --name [URL_VERCEL]
```

Na primeira execução, o Vercel pergunta o escopo e cria o projeto. Nas próximas, é só redeploy.

---

## O que o HTML final entrega

- Kanban de seis colunas: Novo, Abordado, Respondeu, Agendado, Ganhou, Perdeu.
- Drag-and-drop entre colunas (Sortable.js via CDN).
- Dossiê slide-in à direita com quatro abas: Visão Geral, Rapport Humano, Ganchos de Dor, Atividade.
- Command palette (Cmd K ou Ctrl K) com busca global e ações rápidas.
- Filtros combináveis em chips: Com Instagram, WhatsApp real, Com dono, CNPJ oficial, Anuncia Meta, Priority 70+, Cidade.
- Export CSV com status atual e notas.
- Timeline automática (clicar em WhatsApp registra interação) e notas manuais.
- Estado persistido em `localStorage` com chave configurável.
- Tema dark por padrão com toggle para light.
- Responsivo no mobile (kanban vira lista vertical agrupada por status).

---

## Requisitos técnicos

- Python 3.10 ou superior com `requests`.
- Chave da Google Places API com Places API (New) ativada (US$ 200 de crédito gratuito por mês cobrem o uso típico).
- Playwright instalado (`pip install playwright` e `python -m playwright install chromium`).
- Conta Vercel (ou qualquer host estático equivalente).
- Claude Code no seu plano atual.
- Opcional: Evolution API self-hosted para validação real de WhatsApp.

---

## Metas de qualidade por execução

- 50 leads consolidados, todos da cidade alvo.
- 40 por cento ou mais com CNPJ.
- 25 por cento ou mais com dono identificado via CNPJ oficial ou LinkedIn.
- 60 por cento ou mais com Instagram localizado.
- 70 por cento ou mais com WhatsApp validado (se rodou a Fase 06).
- Todos com três ou mais pontos de rapport humano.
- Todos com duas ou mais observações de gancho comercial.

Se bater esse alvo, a entrega está no padrão. Abaixo disso, vale reextrair com queries adicionais.

---

## Observações finais

- NUNCA pré-escreva mensagem de WhatsApp no CRM. O vendedor personaliza cada abordagem lendo o dossiê.
- Rapport humano é diferente de gancho comercial. Rapport é ponto de conexão (bairro, tempo de mercado, cultura da empresa, nicho atendido). Gancho é observação dura (site em HTTP sem SSL, review sem resposta há 18 meses, Instagram parado).
- Se a Fase 07 falhar por bloqueio da Meta, repita uma vez com delays maiores. Se persistir, marque como "não verificado".
- Se os seus leads saírem com DDD de outro estado, verifique se o filtro regional da Fase 02 está configurado para o estado certo.

---

Método aberto por Maurício Ribeiro, sócio da Ethos Growth. Licença MIT.

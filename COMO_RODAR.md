# Como rodar — Guia passo a passo

Guia para replicar o Invictus Prospect Template no seu recorte (segmento e cidade).

## Quickstart (3 comandos)

```bash
git clone https://github.com/maauricioozy/invictus-prospect-template
cd invictus-prospect-template
./setup.sh   # Windows: powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

O `setup.sh` cria a venv, instala dependências, baixa Chromium do
Playwright e prepara o `.env`. Depois disso, edite o `.env` (no mínimo
`GOOGLE_PLACES_API_KEY` e `AGENCIA`) e rode:

```bash
claude < PROMPT.md
```

O Claude Code orquestra o pipeline inteiro. Se quiser entender ou
debugar fase por fase, siga o guia detalhado abaixo.

## Pré-requisitos

1. **Python 3.10 ou superior** instalado. Verifique com `python --version`.
2. **Chave Google Places API**. Obtenha em https://console.cloud.google.com/apis/credentials. Ative "Places API (New)". O Google dá US$ 200 de crédito mensal gratuito, que cobrem extração de dezenas de milhares de leads.
3. **Conta Vercel** (ou qualquer host estático equivalente).
4. **Claude Code** instalado e autenticado.
5. **Opcional**: Evolution API self-hosted para validar WhatsApp real. Guia oficial: https://doc.evolution-api.com/. Sem ela, pule a Fase 06.

## Estrutura de pastas sugerida

```
meu-crm-leads/
  .env                          # GOOGLE_PLACES_API_KEY=...
  extrator.py                   # Extrator GMN (ver repositório-mãe)
  merge.py                      # Parte do template
  fase_a_cnpj.py
  fase_b_brasilapi.py
  gerar_lotes_v2.py
  fase_d_wa_validar.py
  fase_e_anuncia_real.py
  consolidate_v2.py
  template_crm.html
  build_html_v2.py
  prospects/                    # Saída do extrator
  lotes_v2/                     # Saída do gerar_lotes
```

## Passo 1 — Preparar os arquivos

Descompacte o ZIP do template na pasta escolhida. Ajuste os caminhos absolutos no topo de cada script Python (a variável `BASE`).

## Passo 2 — Configurar o arquivo .env

```env
GOOGLE_PLACES_API_KEY=AIzaSy...SUA_CHAVE
```

## Passo 3 — Rodar o extrator (Fase 01)

Rode entre oito e doze queries combinando o segmento com sinônimos e cidades vizinhas:

```bash
python extrator.py "[SEGMENTO] [CIDADE]"
python extrator.py "[SINÔNIMO_SEGMENTO] [CIDADE]"
python extrator.py "[SEGMENTO] [CIDADE_VIZINHA]"
```

Os CSVs ficam em `prospects/DATA_SEGMENTO_CIDADE.csv`.

## Passo 4 — Merge e dedup (Fase 02)

Edite `merge.py`:

- `DATE` para a data de hoje.
- `NICHE_TERMS` para os termos que aparecem no nome das empresas do segmento.
- `BLACKLIST_TERMS` para termos a evitar.
- Lista de DDDs do estado alvo (ex: `41` para Paraná, `11` para São Paulo, `71` para Bahia).

Rode:

```bash
python merge.py
```

Saída: CSV consolidado com o top 50.

## Passo 5 — Scrape de CNPJ (Fase 03)

```bash
python fase_a_cnpj.py
```

Taxa de acerto típica: 40 a 60 por cento. Sites institucionais costumam ter CNPJ no rodapé. Sites em Linktree ou WordPress gratuito normalmente não.

## Passo 6 — BrasilAPI (Fase 04)

```bash
python fase_b_brasilapi.py
```

Rate limit: três threads em paralelo. Para 30 CNPJs, leva cerca de dez segundos. Salva `cnpj_enriquecidos.json`.

## Passo 7 — Gerar lotes e disparar cinco subagentes de IA (Fase 05)

```bash
python gerar_lotes_v2.py
```

Cria cinco arquivos `lotes_v2/lote_v2_[1-5].json`.

No Claude Code, dispare cinco subagentes `general-purpose` em paralelo. O prompt de cada subagente está documentado no PROMPT.md (seção Fase 05). Cada um lê o seu lote e salva `enriched_v2_X.json`.

Tempo típico com cinco em paralelo: três a cinco minutos.

## Passo 8 — Validar WhatsApp (Fase 06, opcional)

Se você tem Evolution API:

```bash
python fase_d_wa_validar.py
```

O script faz SSH para o servidor (ajuste o nome do host). Valida todos os 50 números de uma vez. Saída: `wa_validado.json`.

Sem Evolution API, pule este passo. O CRM mostra "não verificado" no campo de WhatsApp ativo.

## Passo 9 — Validar anúncios no Meta via Playwright (Fase 07)

Instale o Playwright e o Chromium uma vez:

```bash
pip install playwright
python -m playwright install chromium
```

Rode a validação:

```bash
python fase_e_anuncia_real.py
```

Consulta a Meta Ad Library pública para cada lead. Tempo típico para 50 leads: entre seis e oito minutos. Saída: `anuncia_validado.json`.

## Passo 10 — Consolidar (Fase 08)

```bash
python consolidate_v2.py
```

Merge final em `leads_final.json`. Imprime as estatísticas finais no stdout.

Modos disponíveis:

```bash
python consolidate_v2.py                  # default: merge dos JSONs locais
python consolidate_v2.py --source=supabase   # pull do estado da nuvem
python consolidate_v2.py --source=hybrid     # local + complementa status do cloud
```

## Passo 10b — Sync incremental no Supabase (Fase 08a, opcional)

Apenas se você configurou Supabase no `.env`:

```bash
python fase_sync_supabase.py
```

Este passo é o que torna o pipeline incremental real. Ele:

- Busca leads existentes da sua agência no Supabase
- Identifica quais leads do `leads_final.json` são novos versus já
  conhecidos (match por CNPJ, depois WhatsApp, depois nome normalizado)
- Insere os novos com `first_seen_at = agora`
- Atualiza apenas campos voláteis dos existentes (sinais Maps, contagem
  Meta Ads). **Nunca toca em status, notas, atividade ou rapport.**
- Registra a rodada na tabela `execucoes`
- Atualiza o `leads_final.json` local com a flag `novo_nesta_rodada`

Use `--dry-run` para simular sem escrever no Supabase. Use `--input
outro.json` para sincronizar um JSON alternativo.

Para ver no CRM apenas os leads adicionados nesta rodada, use o filtro
"Novos nesta rodada". Para ignorar quem já saiu do status "novo", use
"Apenas não contactados".

## Passo 11 — Build do HTML (Fase 09)

```bash
python build_html_v2.py
```

Gera `index.html`. Pode abrir direto no navegador, sem servidor.

## Passo 12 — Deploy na Vercel

```bash
cd pasta-do-projeto
vercel --prod --yes --name meu-crm-leads
```

Na primeira execução, o Vercel pergunta o escopo e cria o projeto. Nas seguintes, é só redeploy.

## Adaptando para outro segmento ou cidade

Três arquivos precisam ser ajustados:

**`merge.py`**:
- `NICHE_TERMS` — termos que aparecem no nome de empresas do novo segmento (ex: `['odontolog', 'dentista', 'ortodontia']`).
- `BLACKLIST_TERMS` — termos a evitar.
- Lista de DDDs do novo estado.

**`gerar_lotes_v2.py`**: nada a mudar, é genérico.

**PROMPT do subagente (Fase 05)**: ajuste a descrição de contexto do nicho (ex: "certificadoras competem com Certisign e Valid" vira "dentistas competem com OdontoCompany e Orthodontic Center").

**`template_crm.html`**: pode ajustar `title`, `meta description` e, opcionalmente, a paleta no `tailwind.config` se quiser outra identidade visual.

## Dicas

- Comece com três a cinco queries no extrator. Se vier menos de 100 empresas brutas, adicione mais três a cinco.
- Cidades pequenas (menos de 500 mil habitantes) podem ter menos de 30 leads de um nicho. Combine cidade com região metropolitana.
- O extrator Google Places não acha leads que não estão no Maps. Para nichos não-locais (e-commerce, SaaS), use outras fontes.
- Se a BrasilAPI começar a retornar HTTP 400 para vários CNPJs, o regex do scraping provavelmente está pegando números errados. Revise a Fase 03.

## Problemas comuns

- **extrator.py retorna poucos leads com query boa**: Google Places está rate-limitando ou a chave da API está sem billing ativo.
- **CNPJs não encontrados na maioria dos sites**: os sites são Linktree ou redes sociais. Taxa de 30 a 40 por cento sem CNPJ é normal.
- **BrasilAPI HTTP 429**: está rodando rápido demais. Aumente o delay de `0.3` para `0.5` em `fase_b_brasilapi.py`.
- **Subagente retorna JSON malformado**: o prompt da Fase 05 precisa ser seguido à risca. Se falhar, cole o prompt novamente reforçando o formato JSON exato.
- **Playwright Meta Ad Library trava**: verifique se o Chromium foi instalado (`python -m playwright install chromium`). Se persistir, aumente o delay entre requests.

## Tempo total estimado (50 leads, uma cidade)

- Fase 01 (extração): cinco a dez minutos para várias queries.
- Fase 02 (merge): dez segundos.
- Fase 03 (CNPJ): dois a três minutos.
- Fase 04 (BrasilAPI): dez segundos.
- Fase 05 (cinco subagentes): três a cinco minutos.
- Fase 06 (WhatsApp): 30 segundos (opcional).
- Fase 07 (Meta Ads): seis a oito minutos.
- Fase 08 (consolidar): um segundo.
- Fase 09 (build HTML): um segundo.
- Deploy Vercel: 15 segundos.

**Total: entre 18 e 28 minutos por execução completa.**

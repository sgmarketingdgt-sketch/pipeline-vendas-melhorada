# RUNBOOK — Operação de Prospecção Yonzza Digital

Guia completo e autossuficiente. Sem precisar do Claude.

---

## Fluxo para qualquer nicho novo

### Passo 1 — Editar o `.env`

Abra o arquivo `.env` e mude as 3 linhas marcadas com ⚠️:

```
SEGMENTO="Nome do Nicho"    ← nome exato do nicho (ex: "Blindagem Automotiva")
CIDADE="São Paulo"           ← cidade alvo
SERVICO=generico             ← sempre "generico" para nicho novo
```

> Nichos com mensagens personalizadas: use `seguranca_trabalho` ou `trafego_pago_aviacao` no lugar de `generico`.

---

### Passo 2 — Rodar as queries de extração

```bash
cd ~/Downloads/invictus-prospect-template

python3 extrator.py "[SEGMENTO] [CIDADE]"
python3 extrator.py "[SINONIMO] [CIDADE]"
python3 extrator.py "[SEGMENTO] [CIDADE VIZINHA]"
# ... 8 a 12 queries no total
```

**Meta:** 80–120 resultados brutos em `prospects/`. Se sair menos, rode mais queries.

---

### Passo 3 — Rodar o pipeline completo

**Opção A — 1 comando (recomendado)**

```bash
./pipeline.sh
```

Faz tudo automaticamente: merge → CNPJ → BrasilAPI → WhatsApp → Meta Ads → e-mail → Instagram → consolidação → Supabase → build → deploy.

Aguarda terminar (~30–60 min) e exibe:
```
CONCLUÍDO!
CRM no ar: https://invictus-prospect-yonzza.vercel.app
```

> **Nicho nacional** (ex: aviação): rode antes do pipeline:
> ```bash
> python3 merge_aviacao.py
> ./pipeline.sh
> ```

---

**Opção B — Fases separadas (para debugar ou rodar parcialmente)**

```bash
python3 merge.py                  # dedup e filtro (usar merge_aviacao.py para nichos nacionais)
python3 fase_a_cnpj.py            # busca CNPJ nos sites
python3 fase_b_brasilapi.py       # enriquece via BrasilAPI (razão social, sócios)
python3 fase_d_wa_validar.py      # valida WhatsApp (requer Evolution API)
python3 fase_e_anuncia_real.py    # verifica anúncios Meta e Google Ads
python3 fase_email.py             # busca e-mails (RDAP + scraping + CNPJ)
python3 fase_instagram.py         # busca Instagram da empresa e do dono
python3 consolidate_v2.py         # monta leads_final.json
python3 fase_sync_supabase.py     # sincroniza com Supabase
python3 build_html_v2.py          # gera index.html
npx vercel --prod --yes --force   # deploy
npx vercel alias set [url-gerada].vercel.app invictus-prospect-yonzza.vercel.app
```

Use a Opção B quando quiser reprocessar só uma fase específica sem rodar tudo do zero.

---

## Nichos ativos

| Nicho | SEGMENTO no .env | SERVICO |
|---|---|---|
| Hamburguerias SP | `Hamburgueria` | `trafego_pago` |
| Escolas de Aviação | `Escola de Aviação` | `trafego_pago_aviacao` |
| Segurança do Trabalho | `Segurança do Trabalho` | `seguranca_trabalho` |
| Operador de Máquinas | `Operador de Máquinas` | `generico` |
| Blindagem Automotiva | `Blindagem Automotiva` | `generico` |
| Qualquer outro nicho | *(qualquer nome)* | `generico` |

---

## Queries sugeridas por nicho

### Segurança do Trabalho — SP
```
curso nr10 São Paulo
treinamento nr35 São Paulo
curso segurança do trabalho São Paulo
treinamento NR33 espaço confinado São Paulo
brigada de incêndio treinamento São Paulo
curso nr10 Campinas / Guarulhos / ABC paulista
treinamento NR18 construção civil São Paulo
curso trabalho em altura nr35 São Paulo
treinamento segurança trabalho ABC paulista
```

### Operador de Máquinas — SP
```
curso operador de máquinas São Paulo
curso operador de empilhadeira São Paulo
curso operador de ponte rolante São Paulo
curso operador de guindaste São Paulo
curso operador de retroescavadeira São Paulo
curso NR11 empilhadeira São Paulo
curso operador de máquinas ABC / Campinas / Guarulhos
treinamento operador de máquinas pesadas São Paulo
```

### Blindagem Automotiva — SP
```
blindagem automotiva São Paulo
PPF proteção de pintura São Paulo
insulfilm premium São Paulo
envelopamento automotivo São Paulo
estética automotiva premium São Paulo
vitrificação automotiva São Paulo
blindagem veicular São Paulo
proteção de pintura automotiva São Paulo
```

### Escolas de Aviação — Brasil
```
escola de aviação Brasil
formação de pilotos Brasil
escola piloto privado Brasil
escola de pilotagem avião ATPL Brasil
curso piloto comercial Brasil
instrução de voo aeroclube Brasil
flight school Brasil
```

### Para qualquer nicho novo
```
[segmento] [cidade]
[segmento] [cidade vizinha 1]
[segmento] [cidade vizinha 2]
[sinônimo do segmento] [cidade]
```

---

## Regras importantes

1. **Sempre edite o `.env` antes de rodar** — SEGMENTO e CIDADE definem o nicho inteiro
2. **SEGMENTO deve ser idêntico** entre rodadas do mesmo nicho (letras maiúsculas, acentos — tudo igual)
3. **Nunca edite `index.html` diretamente** — sempre `template_crm.html` → `build_html_v2.py`
4. **Nunca apague os arquivos de cache** (`wa_validado.json`, `anuncia_validado.json` etc.) — levam horas para recriar
5. **`./pipeline.sh` já faz o alias** — não precisa rodar o alias manualmente

---

## Troubleshooting rápido

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 400 INVALID_ARGUMENT` | Query sem resultado na API | Normal — continue para a próxima query |
| `Nenhum CSV com segmento X` | SEGMENTO no .env diferente do CSV | Corrija o SEGMENTO no `.env` |
| CRM mostra 150 após deploy | Alias apontando para deploy antigo | `npx vercel alias set [url-nova].vercel.app invictus-prospect-yonzza.vercel.app` |
| Lead volta como "Novo" entre rodadas | (corrigido) | Já resolvido na versão atual |

---

URL do CRM: **https://invictus-prospect-yonzza.vercel.app**

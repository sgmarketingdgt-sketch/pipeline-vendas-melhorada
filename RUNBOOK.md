# RUNBOOK — Operação de Prospecção Yonzza Digital

Guia completo e autossuficiente. Sem precisar do Claude.

---

## Fluxo para qualquer nicho novo

### Passo 1 — Editar o `.env` (3 linhas)

```
SEGMENTO="Nome do Nicho"
CIDADE="São Paulo"
SERVICO=generico
```

Só isso. O pipeline detecta o nicho automaticamente e usa mensagens genéricas de Google Ads.
Se quiser mensagens personalizadas para o nicho, troque `SERVICO=generico` pelo ID do serviço específico (ex: `seguranca_trabalho`).

---

### Passo 2 — Rodar as queries de extração

```bash
cd ~/Downloads/invictus-prospect-template

python3 extrator.py "[SEGMENTO] [CIDADE]"
python3 extrator.py "[SINONIMO] [CIDADE]"
python3 extrator.py "[SEGMENTO] [CIDADE VIZINHA]"
# ... 8 a 12 queries no total
```

**Meta:** 80–120 resultados brutos em `prospects/`.

---

### Passo 3 — Dedup e filtro

Nicho local (uma cidade):
```bash
python3 merge.py
```

Nicho nacional (ex: aviação):
```bash
python3 merge_aviacao.py
```

**Meta:** 45–50 leads após filtro. Se sair menos, rode mais queries.

---

### Passo 4 — Enriquecimento

```bash
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py
```

---

### Passo 5 — Consolidar e publicar

```bash
python3 consolidate_v2.py
python3 fase_sync_supabase.py
python3 build_html_v2.py
npx vercel --prod --yes --force
npx vercel alias set [url-gerada].vercel.app invictus-prospect-yonzza.vercel.app
```

---

## Nichos ativos (já com mensagens personalizadas)

| Nicho | SEGMENTO | SERVICO |
|---|---|---|
| Hamburguerias SP | `Hamburgueria` | `trafego_pago` |
| Escolas de Aviação | `Escola de Aviação` | `trafego_pago_aviacao` |
| Segurança do Trabalho | `Segurança do Trabalho` | `seguranca_trabalho` |
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
[segmento] bairro [nome do bairro]
```

---

## Regras importantes

1. **`SEGMENTO` no `.env` deve ser consistente** entre rodadas do mesmo nicho (mesmas letras, mesmo texto)
2. **Nunca edite `index.html` diretamente** — sempre `template_crm.html` → `build_html_v2.py`
3. **Nunca apague os arquivos de cache** (`wa_validado.json`, `email_validado.json` etc.)
4. **Sempre fixe o alias** após o deploy

---

## Troubleshooting rápido

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 400 INVALID_ARGUMENT` | Campo inválido na API Google | Normal — query sem resultado, continue |
| `Nenhum CSV com segmento X` | `.env` com SEGMENTO diferente do CSV | Corrija o SEGMENTO no `.env` |
| Lead aparece como "Novo" após nova extração | (corrigido) | Atualizar para versão atual |
| Score Maps nulo | (corrigido) | Atualizar para versão atual |

---

URL do CRM: **https://invictus-prospect-yonzza.vercel.app**

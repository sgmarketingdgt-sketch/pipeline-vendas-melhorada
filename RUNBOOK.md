# RUNBOOK — Operação de Prospecção Yonzza Digital

Guia completo e autossuficiente. Siga na ordem. Sem precisar do Claude.

---

## Nichos já configurados (prontos para usar)

| Nicho | SEGMENTO no .env | SERVICO no .env | IDs | Merge |
|---|---|---|---|---|
| Hamburguerias | `Hamburgueria` | `trafego_pago` | 1–99 | `merge.py` |
| Escolas de Aviação | `Escola de Aviação` | `trafego_pago_aviacao` | 101–199 | `merge_aviacao.py` |
| Segurança do Trabalho | `Segurança do Trabalho` | `seguranca_trabalho` | 201–299 | `merge.py` |
| Clínicas Odontológicas | `Clínica Odontológica` | *(criar JSON)* | 301–399 | `merge.py` |
| Academias | `Academia` | *(criar JSON)* | 401–499 | `merge.py` |
| Advocacia | `Advocacia` | *(criar JSON)* | 501–599 | `merge.py` |
| Contabilidade | `Contabilidade` | *(criar JSON)* | 601–699 | `merge.py` |
| Autoescolas | `Autoescola` | *(criar JSON)* | 701–799 | `merge.py` |
| Clínicas Veterinárias | `Clínica Veterinária` | *(criar JSON)* | 801–899 | `merge.py` |
| Estética | `Estética` | *(criar JSON)* | 901–999 | `merge.py` |

---

## Passo a passo para cada nova leva

### Passo 1 — Configurar o .env

Abra o arquivo `.env` e ajuste as 3 linhas:

```
SEGMENTO="Nome do Nicho"    ← exatamente como na tabela acima
CIDADE="São Paulo"           ← cidade alvo
SERVICO=id_do_servico        ← id do JSON em servicos/
```

**Exemplo para odontologia:**
```
SEGMENTO="Clínica Odontológica"
CIDADE="São Paulo"
SERVICO=odontologia
```

---

### Passo 2 — Criar o JSON do serviço (se for nicho novo)

Copie um existente como base e edite:

```bash
cp servicos/seguranca_trabalho.json servicos/odontologia.json
```

Edite os campos: `id`, `nome`, `nicho_alvo`, `ticket_inicial`, `mensagem_wa_template`, `rapport_humano`, `gancho_dor`.

**Regra:** `nicho_alvo` deve ser o SEGMENTO em letras minúsculas.

---

### Passo 3 — Rodar as queries de extração

```bash
cd ~/Downloads/invictus-prospect-template

python3 extrator.py "[SEGMENTO] [CIDADE]"
python3 extrator.py "[SINONIMO] [CIDADE]"
python3 extrator.py "[SEGMENTO] [CIDADE VIZINHA]"
# ... 8 a 12 queries no total
```

**Dica:** use sinônimos e variações de nome + cidades vizinhas para ampliar a base.

---

### Passo 4 — Dedup e filtro

Use `merge.py` para nichos locais (SP):
```bash
python3 merge.py
```

Use `merge_aviacao.py` para nichos nacionais (ex: aviação):
```bash
python3 merge_aviacao.py
```

**Meta:** 45–50 leads após o filtro. Se sair menos, rode mais queries no Passo 3.

---

### Passo 5 — Enriquecimento (rodar em sequência)

```bash
python3 fase_a_cnpj.py
python3 fase_b_brasilapi.py
python3 fase_d_wa_validar.py
python3 fase_e_anuncia_real.py
python3 fase_email.py
python3 fase_instagram.py
```

Cada fase usa cache — se já rodou antes, pula automaticamente os leads já processados.

---

### Passo 6 — Consolidar e publicar

```bash
python3 consolidate_v2.py
python3 fase_sync_supabase.py
python3 build_html_v2.py
npx vercel --prod --yes --force
npx vercel alias set [url-gerada].vercel.app invictus-prospect-yonzza.vercel.app
```

---

## Regras importantes

1. **Nunca reutilize faixas de ID** — cada nicho tem 100 IDs reservados na tabela acima
2. **SEGMENTO no .env deve bater exatamente** com o que está na tabela (case insensitive)
3. **Nunca edite `index.html` diretamente** — sempre `template_crm.html` → `build_html_v2.py`
4. **Nunca apague os arquivos de cache** (`wa_validado.json`, `email_validado.json` etc.)
5. **Sempre fixe o alias** após o deploy

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
```

### Clínicas Odontológicas — SP
```
clínica odontológica São Paulo
dentista São Paulo
ortodontia São Paulo
implante dentário São Paulo
clínica odontológica Guarulhos / ABC / Campinas
```

### Academias — SP
```
academia musculação São Paulo
academia fitness São Paulo
academia crossfit São Paulo
academia de ginástica São Paulo
academia Guarulhos / ABC / Campinas
```

### Advocacia — SP
```
escritório de advocacia São Paulo
advogado trabalhista São Paulo
advogado empresarial São Paulo
advocacia previdenciária São Paulo
```

### Contabilidade — SP
```
escritório contábil São Paulo
contabilidade empresarial São Paulo
contador São Paulo
BPO financeiro São Paulo
```

### Autoescolas — SP
```
autoescola São Paulo
centro de formação condutores São Paulo
CFC São Paulo
autoescola Guarulhos / ABC
```

---

## Rotação de nichos para chegar a 300 leads

| Rodada | Nicho | Meta | Status |
|---|---|---|---|
| 1 | Hamburguerias SP | 50 leads | ✅ |
| 2 | Escolas de Aviação Brasil | 50 leads | ✅ |
| 3 | Segurança do Trabalho SP | 45 leads | 🔄 em andamento |
| 4 | Clínicas Odontológicas SP | 50 leads | ⏳ |
| 5 | Academias SP | 50 leads | ⏳ |
| 6 | Advocacia SP | 50 leads | ⏳ |
| **Total** | | **295 leads** | |

---

## Troubleshooting rápido

| Erro | Causa | Solução |
|---|---|---|
| `HTTP 400 INVALID_ARGUMENT` | Campo inválido na API | Verifique FIELD_MASK no extrator.py |
| `Nenhum CSV com segmento X` | .env com SEGMENTO errado | Corrija o SEGMENTO no .env |
| `dict contains fields not in fieldnames` | CSVs de nichos diferentes misturados | merge.py filtra por SEGMENTO automaticamente |
| Lead aparece como "Novo" após nova extração | ID mudou entre rodadas | Corrigido — consolidate_v2.py preserva IDs |
| Score Maps nulo | Campo `nota` vs `score` | Corrigido — consolidate_v2.py usa fallback |

---

URL do CRM: **https://invictus-prospect-yonzza.vercel.app**

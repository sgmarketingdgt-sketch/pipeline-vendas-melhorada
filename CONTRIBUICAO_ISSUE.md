# Texto da Issue para abrir em: https://github.com/maauricioozy/invictus-prospect-template/issues/new

---

**Titulo da issue:**
feat: régua de follow-up de 7 dias e registro de motivo de perda no CRM

---

**Corpo da issue:**

## Contexto

Ao usar o CRM em prospecção ativa percebemos dois pontos de atrito recorrentes:

1. Sem uma cadência visivel, os leads ficam parados em "Abordado" sem indicacao de quando agir novamente.
2. Ao mover um lead para "Perdeu" nao havia forma de registrar o motivo — impossibilitando analise de padroes ao longo do tempo.

## O que esta proposta adiciona

### Regua de follow-up de 7 dias

Ao mover um lead para **Abordado**, o CRM registra automaticamente a data como marco zero e calcula as proximas acoes:

| Etapa | Quando | Objetivo |
|---|---|---|
| 1 | Dia 0 | Abordagem inicial |
| 2 | D+2 | Novo angulo |
| 3 | D+5 | Verificacao direta |
| 4 | D+7 | Saida honrosa |

Cada etapa exibe uma mensagem sugerida (gerada a partir dos campos `gancho_dor` e `mensagem_wa` do lead) com botao de copia e botao "Marcar como enviado". As datas das proximas etapas se ajustam a partir da data real de envio — nao da data planejada.

Um badge discreto no card do kanban indica o estado atual:
- `D+2 · 08/05` — proxima etapa prevista
- `HOJE` em amarelo — etapa vence hoje
- `ATRASADO` em vermelho — prazo ultrapassado
- `CONCLUIDO` em verde — regua completa

Um filtro rapido **Follow-up hoje** na barra exibe apenas os leads com acao pendente no dia.

### Novo status: Sem resposta

Status separado de "Perdeu" para leads que completaram a regua sem nenhuma interacao. Permite reabordar em ciclos futuros com angulo diferente.

### Motivo de perda

Ao mover um lead para "Perdeu", um popup solicita o motivo antes de confirmar. Opcoes:

- Sem resposta apos regua completa
- Nao tem interesse no momento
- Ja tem fornecedor
- Preco / orcamento
- Nao e o decisor
- Outro (campo livre)

O motivo fica visivel no card do kanban (linha discreta abaixo do nome) e registrado no historico de atividade com data.

## Implementacao

Todas as alteracoes sao exclusivamente em `template_crm.html` — JavaScript puro, sem dependencias externas. Sem alteracoes em Python, schema ou APIs.

O estado (datas, etapas enviadas, motivo de perda) persiste em localStorage e sincroniza com Supabase via o mecanismo existente de `cloudUpsertLead`.

## O que nao muda

- Estrutura do kanban
- Colunas existentes
- Fluxo de notas e atividade
- Nenhum arquivo Python

## Pergunta ao mantenedor

Faz sentido para o escopo do projeto? Se sim, abro o PR com o codigo revisado seguindo as convencoes do CONTRIBUTING.

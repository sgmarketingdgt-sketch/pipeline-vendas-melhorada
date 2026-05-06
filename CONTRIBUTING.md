# Como contribuir

Obrigado pelo interesse em melhorar o Invictus Prospect Template.
Contribuições são bem-vindas em qualquer formato: bug report, ideia de
feature, correção de doc, ajuste de copy, refatoração de script.

## Antes de abrir uma PR

1. Abra uma issue antes de mudanças grandes. Para correções pequenas
   (bug óbvio, typo, link quebrado), pode ir direto na PR.
2. Mantenha o tom didático e calibrado da documentação. Sem hipérbole,
   sem gatilhos comerciais — o projeto se posiciona como método aberto,
   não como produto.
3. PT-BR com acentuação completa em qualquer texto novo (READMEs,
   comentários, mensagens de log). Sem emoji em código ou docs. Sem
   travessão (use hífen ou dois pontos).
4. Não commit data privado. O `.gitignore` cobre os caminhos óbvios
   (`leads_final.json`, `lotes/`, `prospects/`, `.env`), mas confira
   antes do push.

## Código

- Python 3.10+. Siga PEP 8. CI roda `flake8` em cada PR.
- Scripts devem ser idempotentes sempre que possível e ter `--dry-run`
  quando fazem alteração externa (Supabase, Evolution API).
- Mensagens de erro úteis: explique o que faltou e como resolver. Evite
  `print("erro")` sem contexto.

## CRM (HTML/JS)

- Vanilla JS, sem framework. Tailwind via CDN apenas para layout, não
  para componentes.
- Paleta visual fixa: dark `#0A0A0A` + accent `#3B82F6`, fontes Plus
  Jakarta Sans + Inter. Não introduza outras cores sem motivo.
- Mude `template_crm.html`, nunca o `index.html` gerado.

## Schema Supabase

- Mudanças de schema viram migrações em `supabase/migrations/NNN_nome.sql`
  (a serem criadas quando o primeiro upgrade vier). Nunca edite o
  `schema.sql` original retroativamente — ele é a base para novos
  usuários.

## Setup local para desenvolver

```bash
git clone https://github.com/maauricioozy/invictus-prospect-template
cd invictus-prospect-template
./setup.sh
cp .env.example .env
# Edite .env apontando para um projeto Supabase de teste
python setup_supabase.py
```

Para testar uma rodada completa, use uma cidade pequena e segmento
nichado (ex: `padarias artesanais` em `Florianópolis`) para evitar
gastos de quota da Google Places API.

## Filosofia

Este projeto não vai virar SaaS. Não vai ter monetização direta.
Cada usuário cria a própria infra (Supabase, Evolution, chaves API)
porque o objetivo é ensinar o método e dar autonomia, não criar
dependência. Mantenha esse espírito nas contribuições.

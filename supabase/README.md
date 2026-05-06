# Supabase — guia rápido

Cada usuário do Invictus Prospect Template cria o próprio projeto Supabase
gratuito. Sem multi-tenancy, sem servidor compartilhado: seus leads ficam
no seu projeto, sob seu controle.

## Por que Supabase?

- Banco PostgreSQL de verdade, não localStorage do browser.
- Sync entre dispositivos (você prospecta no notebook, vê o status no celular).
- Modo incremental real (segunda execução só adiciona leads novos, preserva
  status, notas e atividade dos antigos).
- Free tier comporta cerca de 150 mil leads por projeto.
- Sem nenhuma dependência de infraestrutura do autor: você é dono do banco.

## Criar o projeto (5 minutos)

1. Acesse https://supabase.com e faça login (GitHub, Google ou e-mail).
2. Clique em **New project**.
3. Escolha:
   - **Name**: qualquer coisa (ex: `prospeccao-ethos`)
   - **Database Password**: gere uma forte e guarde em local seguro
   - **Region**: `South America (São Paulo)` se for prospecção BR
   - **Pricing Plan**: Free
4. Aguarde uns 2 minutos enquanto o projeto sobe.

## Pegar as chaves

Quando o projeto estiver pronto, abra **Project Settings** (ícone de engrenagem)
e copie:

- **Project URL**: em `Settings > API > Project URL` →
  vai para `SUPABASE_URL` no `.env`
- **anon public key**: em `Settings > API > Project API keys > anon public` →
  vai para `SUPABASE_ANON_KEY` no `.env` (esta é a chave que o CRM usa no browser)
- **service_role key**: em `Settings > API > Project API keys > service_role` →
  vai para `SUPABASE_SERVICE_ROLE_KEY` no `.env`. **Atenção: esta é secreta.**
  Só usamos para validar o setup; nunca exponha em código cliente.
- **Connection string** (opcional, modo automático): em
  `Settings > Database > Connection string > URI`. Substitua `[YOUR-PASSWORD]`
  pela senha do banco e cole em `SUPABASE_DB_URL` no `.env`.

## Aplicar o schema

Com o `.env` preenchido, na raiz do projeto:

```bash
python setup_supabase.py
```

O script tenta aplicar o `schema.sql` automaticamente via `SUPABASE_DB_URL`.
Se você não tiver configurado a connection string, ele te dá o link do SQL
Editor com instruções para colar o conteúdo manualmente. Em ambos os casos,
ao final ele valida se as tabelas `leads` e `execucoes` estão acessíveis.

## O que o schema cria

- Tabela `leads` — um registro por prospect, com cerca de 30 colunas
  cobrindo identificação, contato, sócios via CNPJ, sinais Maps e Meta Ads,
  rapport humano, gancho comercial, status, notas e atividade.
- Tabela `execucoes` — histórico de cada rodada do pipeline, com contagem
  de leads novos versus preservados.
- Índices únicos por `(cnpj, agencia)` e `(whatsapp_numero, agencia)` para
  upsert determinístico.
- Trigger `set_updated_at` para auditoria.
- Row Level Security ativada com policy aberta (default sensato para
  projeto pessoal). Comentário no SQL mostra como fechar com JWT se quiser.
- View `leads_stats` com contagem por status.

## Rodar de novo é seguro

O `schema.sql` usa `IF NOT EXISTS` em tudo. Pode rodar `setup_supabase.py`
quantas vezes quiser sem quebrar nada. Útil para revalidar depois de
alterar o `.env`.

## Custo

Zero. O free tier do Supabase dá 500 MB de banco e 2 GB de transferência
mensal, mais que suficiente para dezenas de milhares de leads. Quando
crescer, planos pagos começam em US$25/mês.

# Changelog

Todas as mudanças notáveis deste projeto são registradas aqui. O formato
segue [Keep a Changelog](https://keepachangelog.com/) e o projeto adere
ao [SemVer](https://semver.org/).

## [1.0.0] — 2026-04-24

Primeira versão pública. Pipeline completo de prospecção B2B local com
Claude Code, modo incremental e CRM kanban.

### Adicionado
- Pipeline em nove fases: Google Places, dedup, scraping CNPJ, BrasilAPI,
  rapport humano via IA, validação WhatsApp, checagem Meta Ad Library,
  consolidação, CRM kanban estático.
- Modo incremental real via Supabase: a partir da segunda execução,
  apenas leads novos entram; status, notas e atividade dos antigos são
  preservados.
- Sync multi-device opcional: cada usuário cria o próprio projeto
  Supabase grátis, sem multi-tenancy nem servidor compartilhado.
- CRM com kanban de seis colunas, drag-drop, dossiê quatro abas, command
  palette (`Cmd+K`/`Ctrl+K`), filtros chips, export CSV, badges "Novo",
  histórico de execuções, indicador de sync no header e fallback
  localStorage para uso offline.
- Schema SQL completo com RLS, índices únicos por `(cnpj, agencia)` e
  `(whatsapp, agencia)`, trigger de `updated_at`, view de stats por
  status.
- Setup automatizado em três comandos (`git clone`, `./setup.sh`,
  `claude < PROMPT.md`) para macOS, Linux e Windows.
- Documentação completa: README, arquitetura, COMO_RODAR e PROMPT.

### Limitações conhecidas
- Google Ads Transparency Center: a API só verifica anunciantes
  políticos no Brasil. Anunciantes comerciais não aparecem como "ativo"
  pelo método público.
- Validação de WhatsApp depende da Evolution API (auto-hospedada).
  Sem ela, o pipeline registra apenas "provável" baseado no DDD.
- Playwright para Meta Ad Library exige Chromium instalado localmente.

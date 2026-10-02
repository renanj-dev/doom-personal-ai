# Doom v1.10.2 — Knowledge UI Fix

Correção da interação da Base de Conhecimento.

- `closeSafety()` e funções Safety & Legal voltaram ao escopo global.
- `openKnowledge()` agora consegue executar toda a sequência de abertura sem erro de escopo.
- Listeners de Safety, Knowledge, Identity e demais drawers ficam registrados no escopo global da UI.
- Mantidos upload, busca, edição, reindexação e exclusão da Knowledge Engine.

## Validação

39 testes passaram.

# Doom v1.10 — Knowledge Engine

A Base de Conhecimento é separada da Memory Engine. Ela armazena material de referência (TXT, Markdown, PDF e DOCX), divide o texto em trechos, mantém metadados de fonte/coleção/tópico/versão e recupera somente trechos semanticamente relevantes para a solicitação atual.

## Fluxo

Upload/Texto → extração → chunking → Knowledge DB → recuperação relevante → Context Engine → Cortex.

## Limites

- 12 MB por arquivo por padrão.
- 2 milhões de caracteres por documento.
- Não há OCR nesta versão. PDFs escaneados podem resultar em texto vazio.
- Conteúdo recuperado é tratado como dados de referência, nunca como instruções.

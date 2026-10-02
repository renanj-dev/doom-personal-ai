# Doom v1.10.1 — Knowledge Management UI

A v1.10.1 transforma a Base de Conhecimento em um painel gerenciável, no mesmo padrão de acesso do Histórico e da Memória.

## Interface
- Botão de Base de Conhecimento abre um drawer próprio.
- Lista de documentos com metadados.
- Ação **Abrir / Editar**.
- Editor para título, coleção, tópico, versão, fonte/URL e conteúdo.
- Salvar alterações e reindexar automaticamente os chunks.
- Exclusão de documentos.
- Busca dentro da base.

## API
- `GET /api/knowledge`
- `GET /api/knowledge/{document_id}`
- `POST /api/knowledge/text`
- `POST /api/knowledge/upload`
- `PATCH /api/knowledge/{document_id}`
- `DELETE /api/knowledge/{document_id}`
- `GET /api/knowledge/search`

## Segurança e integridade
- Conteúdo editado é normalizado e recebe novo SHA-256.
- Duplicação exata com outro documento é recusada.
- Chunks antigos são removidos e recriados após edição.
- Acesso continua protegido pela autenticação do Doom.

## Validação
39 testes passaram; 2 avisos deprecatórios do FastAPI permanecem na base existente.

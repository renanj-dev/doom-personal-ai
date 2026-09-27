# Doom Memory Engine v1.1

The Memory Engine separates three concepts:

1. **Conversation history** — complete messages grouped into sessions.
2. **Persistent memory** — curated facts/preferences explicitly stored for future context.
3. **Current context** — a bounded slice of the active conversation plus relevant memory sent to the selected AI provider.

## History features

- create a conversation
- resume a conversation
- automatic short titles
- list recent conversations
- search message history
- archive conversations
- delete conversations
- count messages per conversation

History lives in the same SQL database as Doom's existing memory system. SQLite works locally; PostgreSQL is supported for cloud deployments.

## API

- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{session_id}`
- `PATCH /api/conversations/{session_id}`
- `DELETE /api/conversations/{session_id}`
- `GET /api/history/search?q=...`

The browser stores only the Doom access key and the active conversation id. Provider secrets remain server-side.

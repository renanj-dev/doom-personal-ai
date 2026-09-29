# Doom Memory Engine v1.2

The Memory Engine separates four concepts:

1. **Conversation history** — complete messages grouped into sessions.
2. **Persistent memory** — curated facts/preferences stored for future context.
3. **Memory proposals** — candidate memories that require explicit confirmation before becoming persistent.
4. **Current context** — a bounded slice of the active conversation plus relevant memories sent to the selected AI provider. The dedicated v1.3 Context Engine owns this assembly.

## Memory intelligence

- Natural-language memory requests such as `Doom, lembre que...` create a pending proposal.
- Doom asks for confirmation before saving the information permanently.
- `sim`, `pode`, or `confirma` approve the proposal; `não`, `cancela`, or similar replies reject it.
- Memories are categorized heuristically and can be edited/created through the UI/API.
- Context selection uses lightweight relevance scoring so only a small set of memories is sent to the model.
- The system does not use embeddings yet; it is intentionally dependency-light for the free/local prototype.

## Memory API

- `GET /api/memories`
- `GET /api/memories/search?q=...`
- `POST /api/memories`
- `DELETE /api/memories/{memory_id}`
- `GET /api/memory/pending/{session_id}`
- `POST /api/memory/propose`
- `POST /api/memory/proposals/{proposal_id}/approve`
- `POST /api/memory/proposals/{proposal_id}/reject`

History remains separate from memory. A conversation message is not automatically promoted to persistent memory.

## Privacy

Provider keys remain server-side. Persistent memory should contain only information the user wants Doom to retain. Sensitive information should not be stored automatically.

# Doom Context Engine v1.3

The Context Engine builds a compact context bundle for the active request instead of sending the same large profile and a fixed message window every time.

## Sources

1. **Recent conversation** — up to 12 newest messages from the current session.
2. **Relevant recall** — up to 8 older messages, including cross-conversation matches, ranked by lexical relevance.
3. **Persistent memory** — up to 8 active memories selected by the existing Memory Intelligence layer.
4. **Focused profile** — only profile sections related to the current task, with identity always included.

## Strategy

The first implementation is intentionally deterministic and dependency-free. It uses word overlap, phrase matching and small recency/session bonuses. This makes the behavior inspectable and allows a future embeddings/vector-search implementation to replace the scorer without changing the rest of Doom.

## Guarantees

- Doom and Renan remain separate identities.
- The current user message is not duplicated when building context.
- The engine limits recalled messages per conversation to reduce context flooding.
- Persistent memories remain distinct from chat history.
- The focused profile is contextual guidance, not a replacement for explicit memory.

## Debug endpoint

Authenticated clients can inspect a context bundle with:

`GET /api/context/preview?session_id=<id>&q=<query>`

This endpoint is for development/diagnostics and should not be exposed without authentication.

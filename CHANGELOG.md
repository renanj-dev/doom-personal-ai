# Changelog

## v1.3.0 — Doom Context Engine

- Added a dedicated Context Engine between Memory and Cortex.
- Uses 12 recent messages plus up to 8 relevant recalled messages.
- Supports cross-conversation lexical recall in the first semantic layer.
- Uses up to 8 relevant persistent memories.
- Uses a focused user profile for normal requests to reduce unnecessary context.
- Added context telemetry to chat responses and the Command Center.
- Added authenticated `/api/context/preview` for diagnostics.
- Kept profile/identity questions deterministic to avoid Doom/Renan identity confusion.
- Updated the project documentation and UI version markers to v1.3.

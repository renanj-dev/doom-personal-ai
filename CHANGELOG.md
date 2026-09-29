# Changelog

## v1.2.0 — Memory Intelligence

- Added confirmation-based memory proposals from natural-language requests.
- Added pending/approved/rejected memory proposal lifecycle.
- Added lightweight memory relevance ranking for current context.
- Added memory search API.
- Added memory management drawer to the web UI.
- Kept persistent memory separate from conversation history.


## v1.1.0 — Memory Engine

- Added persistent conversation history grouped by session.
- Added conversation list, resume, search, archive and delete APIs.
- Added automatic conversation titles and message counts.
- Added history drawer to the Doom web UI.
- Kept persistent memory and user profile separate from raw chat history.
- Kept provider secrets server-side.


## v1.0.0 — Doom Cortex

- Added Doom Cortex task classification and provider routing.
- Added provider fallback when a configured brain fails.
- Added provider-specific model configuration.
- Added `/api/cortex` status endpoint.
- Added brain/model/fallback metadata to chat responses.
- Updated the Command Center telemetry to show the selected brain.
- Preserved deterministic user-profile responses to avoid identity confusion.

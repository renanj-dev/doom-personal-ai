# Doom Tool Audit — v1.4.2

The audit layer is an observability component, not a permission system. The Tool Engine remains responsible for deciding whether a tool is safe, requires confirmation, or is blocked.

## Record fields

- `timestamp`
- `session_id`
- `tool`
- `action`
- `permission`
- `ok`
- `detail`
- `metadata_json`

## Why persist it?

Persistent logs make it possible to answer questions such as:

- Which tools were used in a session?
- Which requests required confirmation?
- Which executions failed?
- How often does a tool fail?
- What did Doom do immediately before an error?

## Privacy

Do not put secrets, API keys, passwords or raw authentication tokens into `detail` or `metadata_json`.

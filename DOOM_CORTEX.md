# Doom Cortex v1.0

The Cortex is the routing layer between the Doom Core and its AI providers.

## Responsibilities

- classify the user's task
- choose a suitable provider from the configured pool
- prefer stronger online providers for analysis, study, creation, and speculation
- prefer the local provider for simple chat and operational tasks when available
- fall back to another configured provider when the selected provider fails
- return provider/model metadata to the interface

## Configuration

`CORTEX_PROVIDERS` is a comma-separated ordered pool.

Examples:

```env
CORTEX_PROVIDERS=ollama,openrouter,openai
```

Local-first:

```env
CORTEX_PROVIDERS=ollama,openrouter,openai
```

Cloud-first:

```env
CORTEX_PROVIDERS=openrouter,openai
```

## Provider-specific models

- `OLLAMA_MODEL`
- `OPENROUTER_MODEL`
- `OPENAI_MODEL`

The Cortex never changes Doom's identity or memory. It only chooses which configured brain should answer a task.


## Context Engine integration (v1.3)

Before a normal request reaches Cortex routing, Doom builds a focused context bundle from recent messages, relevant older messages (including cross-conversation recall), relevant persistent memories, and a focused user profile. Cortex then selects the provider without owning memory or identity.

# Doom v0.7 — Cloud-first, free prototype

This version is prepared for a zero-cost cloud prototype:

- **Render Free** for the FastAPI/Docker web service.
- **Neon Free** for PostgreSQL persistence.
- **OpenRouter Free** for the online brain (`openrouter/free`).

The local Ollama path is still supported for the PC version.

## Current cloud architecture

`Browser/phone -> Render -> Doom Core -> Neon PostgreSQL`

`Doom Core -> OpenRouter Free -> selected free model`

## Deploy checklist

1. Put this repository in GitHub.
2. Create a **Neon Free** PostgreSQL project and copy its connection string.
3. In Render, create a new **Web Service** from the GitHub repository. The included `render.yaml` can also be used as a Blueprint.
4. Set the following Render environment variables:
   - `DOOM_API_KEY` = a private key you choose for the Doom web interface.
   - `OPENROUTER_API_KEY` = your OpenRouter API key.
   - `DATABASE_URL` = the Neon PostgreSQL URL; if needed, use `postgresql+psycopg://...` or let the app normalize `postgresql://...` automatically.
   - `SEED_MEMORIES` = `true` on first deploy so the curated profile is inserted.
5. Deploy. Render will provide an `onrender.com` URL.
6. Open the URL in the browser and enter the `DOOM_API_KEY` in the Doom interface.

## Important free-tier notes

- Render Free web services can spin down after 15 minutes without traffic and wake on the next request.
- Render's free PostgreSQL is intentionally not used here because the current free database expires after 30 days.
- Neon Free provides scale-to-zero PostgreSQL; current free limits should be checked in Neon before relying on them long-term.
- OpenRouter Free currently provides free-model routing but has a daily request limit. The free model pool can change.

## Secrets

Never commit `.env`, API keys, or database passwords. Put secrets in Render Environment Variables.


## Doom v1.5 — Deep Search
Deep Search é um modo opcional, desligado por padrão. Quando ativado, o Core executa pesquisas em múltiplas consultas, recupera fontes e entrega o material ao Cortex para síntese. As fontes recuperadas também aparecem na interface.


## Doom v1.5.1 — Tool Engine 2.0

A v1.5.1 adiciona controle operacional das ferramentas, permissões persistentes, confirmações e execução estruturada.

## Doom v1.5.0 — Deep Search
Deep Search is disabled by default and requires a configured web-search provider key before it can be activated.

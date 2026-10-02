# Doom v1.12 — Identity + Google Login

Google login is an optional identity provider layered on top of Doom Identity.

## Flow
1. Sign in normally with the legacy Doom key.
2. In Identity, link the current Doom identity to a Google account.
3. Future sessions can use the Google account without storing a Google password in Doom.

The backend verifies the Google ID token signature, issuer, audience and expiry, and uses the Google `sub` as the stable external identifier.

## Configuration
- `GOOGLE_LOGIN_ENABLED=true`
- `GOOGLE_CLIENT_ID=<web client id>`

The client ID is not a secret. No Google client secret is stored in the browser or database.

# Carole Google OAuth token service

This Cloudflare Worker supplies the Google-issued Desktop client secret during
authorization-code exchanges and refreshes. The Python package contains the
public client ID and this service's HTTPS endpoint, never the client secret.

Google consent and its `127.0.0.1` callback still happen on the user's computer.
Carole checks browser state, binds the connection to the signed-in local user,
and generates a fresh S256 PKCE verifier for each authorization. The local
backend posts the code and verifier to `/token`. This service sends them to
Google with its encrypted `GOOGLE_CLIENT_SECRET` binding, then returns Google's
tokens to the local backend. Refresh requests use the same endpoint.

Access and refresh tokens transit this service in memory. They are not stored
in a cloud database or logged by the application. Their persistent copy stays
in the user's OS credential vault. Google API calls go directly from Carole
to Google. Cloudflare necessarily processes the token requests; the privacy
policy should describe this before public release.

## Controls and limitations

- Only the configured client ID is accepted. No arbitrary token endpoint,
  supplied client secret, or additional upstream parameter is forwarded.
- Code exchanges require a PKCE verifier and an exact loopback callback path.
- Refreshes cannot request broader scopes. Possession of the refresh token is
  required; the service does not pretend to authenticate installed app binaries.
- No browser CORS; requests with an Origin header are rejected.
- 16 KiB maximum request, 15 second upstream timeout, no upstream redirects.
- A Cloudflare rate-limit binding allows 30 requests per minute per IP.
  This is an approximate per-location abuse control, not a global quota.
- Responses are never cacheable; provider error descriptions are sanitized.
- Worker observability is disabled. Do not enable body logging or capture real
  token traffic in debugging tools.
- The Workers Free daily cap still applies; hitting it interrupts connection
  and refresh until capacity returns. Carole preserves tokens on transient
  refresh failure. No paid plan, database, KV, or custom domain is required.
- Google branding and sensitive/restricted-scope verification remain necessary
  for general distribution. Hosting this service does not grant verification.

## Deploy

Use Wrangler 4.147.0 (the version used for this deployment):

```powershell
npx --yes wrangler@4.147.0 login --use-keyring --scopes account:read user:read workers_scripts:write workers:write workers_routes:write
node --test worker.test.mjs
npx --yes wrangler@4.147.0 deploy --dry-run
npx --yes wrangler@4.147.0 deploy
npx --yes wrangler@4.147.0 secret put GOOGLE_CLIENT_SECRET
```

Enter only the secret belonging to the Desktop client ID in `wrangler.jsonc`.
Never put it in source, environment-variable plaintext bindings, command-line
arguments, or a client package. If deployment happens before secret setup, the
token endpoint fails closed with HTTP 503.

The deployed URL is:
`https://carole-google-oauth.google-oauth.workers.dev/token`

`GET /health` reports readiness without returning credentials. Carole's release
endpoint lives in `backend/carole_ai/resources/google_oauth_token_endpoint.txt`.
An explicit `CAROLE_GOOGLE_CREDENTIALS` file continues to use its own OAuth
client directly, useful for development and self-hosted installations.

## Verification

Run `node --test worker.test.mjs` and
`python -m pytest tests/test_google_workspace_oauth.py -q` from `backend`.
Before publishing a Python release, verify a real consent callback, vault
reload in a new process, refresh through this service, and read-only calls to
the enabled Google APIs. Unit tests use dummy credentials and cannot establish
that the Google project or production secret is configured correctly.

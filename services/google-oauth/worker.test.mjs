import {test} from "node:test";
import assert from "node:assert/strict";
import worker, {handle} from "./worker.mjs";

const env = {
  GOOGLE_CLIENT_ID: "test.apps.googleusercontent.com",
  GOOGLE_CLIENT_SECRET: "server-only-test-value",
  TOKEN_RATE_LIMITER: {async limit() { return {success: true}; }},
};
const auth = {
  client_id: env.GOOGLE_CLIENT_ID, grant_type: "authorization_code", code: "test-code",
  code_verifier: "a".repeat(64), redirect_uri: "http://127.0.0.1:8001/api/auth/google/callback",
};
function request(fields = auth, headers = {}) {
  return new Request("https://broker.example/token", {method: "POST",
    headers: {"Content-Type": "application/x-www-form-urlencoded", ...headers},
    body: new URLSearchParams(fields),
  });
}
const noUpstream = () => { throw new Error("Upstream must not be called"); };

test("exchange injects server secret, preserves PKCE, and excludes unexpected response fields", async () => {
  let called = false;
  const result = await handle(request(), env, async (url, init) => {
    called = true;
    assert.equal(url, "https://oauth2.googleapis.com/token");
    assert.equal(init.body.get("client_secret"), env.GOOGLE_CLIENT_SECRET);
    assert.equal(init.body.get("code_verifier"), auth.code_verifier);
    assert.equal(init.redirect, "manual");
    return Response.json({access_token: "test-token", expires_in: 3600, client_secret: "must-not-leak"});
  });
  assert.equal(called, true);
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("Cache-Control"), "no-store");
  assert.equal(result.headers.get("Access-Control-Allow-Origin"), null);
  assert.deepEqual(await result.json(), {access_token: "test-token", expires_in: 3600});
});

test("refresh accepts google-auth's empty client secret and never broadens scopes", async () => {
  const result = await handle(request({client_id: env.GOOGLE_CLIENT_ID, client_secret: "",
    grant_type: "refresh_token", refresh_token: "test-refresh", scope: "arbitrary"}), env, async (_, init) => {
    assert.equal(init.body.get("refresh_token"), "test-refresh");
    assert.equal(init.body.get("client_secret"), env.GOOGLE_CLIENT_SECRET);
    assert.equal(init.body.has("scope"), false);
    return Response.json({access_token: "renewed", expires_in: 3600});
  });
  assert.equal(result.status, 200);
});

for (const [name, changes] of [
  ["other client", {client_id: "other"}],
  ["supplied secret", {client_secret: "client-value"}],
  ["missing PKCE", {code_verifier: ""}],
  ["invalid PKCE", {code_verifier: "/".repeat(64)}],
  ["external callback", {redirect_uri: "https://attacker.example/api/auth/google/callback"}],
  ["lookalike loopback", {redirect_uri: "http://127.0.0.1.attacker.example:8000/api/auth/google/callback"}],
  ["callback query", {redirect_uri: auth.redirect_uri + "?redirect=evil"}],
  ["unsupported grant", {grant_type: "client_credentials"}],
  ["arbitrary upstream", {token_uri: "https://attacker.example"}],
]) {
  test(`rejects ${name} before contacting Google`, async () => {
    assert.equal((await handle(request({...auth, ...changes}), env, noUpstream)).status, 400);
  });
}

test("duplicate fields rejected", async () => {
  const fields = new URLSearchParams(auth);
  fields.append("client_id", env.GOOGLE_CLIENT_ID);
  assert.equal((await handle(request(fields), env, noUpstream)).status, 400);
});
test("browser cross-origin submission rejected", async () => {
  assert.equal((await handle(request(auth, {Origin: "https://attacker.example"}), env, noUpstream)).status, 403);
});
test("rate limit fails closed", async () => {
  const limited = {...env, TOKEN_RATE_LIMITER: {async limit() { return {success: false}; }}};
  assert.equal((await handle(request(), limited, noUpstream)).status, 429);
  assert.equal((await handle(request(), {...env, TOKEN_RATE_LIMITER: undefined}, noUpstream)).status, 503);
});
test("chunked oversized bodies rejected", async () => {
  assert.equal((await handle(request({...auth, code: "a".repeat(17000)}), env, noUpstream)).status, 413);
});
test("provider diagnostics cannot echo tokens or secrets", async () => {
  const response = await handle(request(), env, async () => Response.json({
    error: "invalid_grant", error_description: "test-code server-only-test-value",
  }, {status: 400}));
  const result = await response.text();
  assert.match(result, /invalid_grant/);
  assert.doesNotMatch(result, /test-code|server-only/);
});
test("upstream failure is retryable without leaking response", async () => {
  assert.equal((await handle(request(), env, async () => { throw new Error("private"); })).status, 503);
});
test("Cloudflare entrypoint accepts its execution context", async () => {
  const result = await worker.fetch(new Request("https://broker.example/health"), env, {});
  assert.deepEqual(await result.json(), {service: "carole-google-oauth", configured: true});
});

test("redirects never forward credentials to another endpoint", async () => {
  const result = await handle(request(), env, async () => new Response(null, {
    status: 307, headers: {Location: "https://attacker.example"},
  }));
  assert.equal(result.status, 502);
  assert.equal((await result.json()).reason, "upstream_redirect_rejected");
});

// A narrowly scoped token relay for Carole's installed Desktop OAuth client.
// No database, token persistence, browser CORS, or request logging.
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const MAX_BODY = 16384;
const ERRORS = {
  invalid_request: "The OAuth request is invalid.",
  invalid_client: "The OAuth client configuration is invalid.",
  invalid_grant: "Authorization expired or was revoked. Reconnect Google.",
  unauthorized_client: "The OAuth client is not authorized.",
  unsupported_grant_type: "This grant type is not supported.",
  invalid_scope: "The requested scope is not available.",
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "Pragma": "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

function error(code, status = 400, reason) {
  return json({error: code, error_description: ERRORS[code] || "OAuth service unavailable. Try again later.", ...(reason ? {reason} : {})}, status);
}

function localCallback(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["127.0.0.1", "[::1]"].includes(url.hostname)
      && url.port !== "" && !url.username && !url.password && !url.search && !url.hash
      && url.pathname === "/api/auth/google/callback";
  } catch { return false; }
}

async function boundedBody(request) {
  if (Number(request.headers.get("Content-Length")) > MAX_BODY) throw new Error("body");
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > MAX_BODY) { await reader.cancel(); throw new Error("body"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder("utf-8", {fatal: true}).decode(bytes);
}

export async function handle(request, env, upstream = fetch) {
  const url = new URL(request.url);
  if (url.pathname === "/health" && request.method === "GET") {
    return json({service: "carole-google-oauth", configured: Boolean(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET && env.TOKEN_RATE_LIMITER)});
  }
  if (url.pathname !== "/token" || url.search) return error("invalid_request", 404);
  if (request.method !== "POST") return error("invalid_request", 405);
  if (!env.GOOGLE_CLIENT_ID || !env.GOOGLE_CLIENT_SECRET || !env.TOKEN_RATE_LIMITER) return error("temporarily_unavailable", 503);
  // This endpoint is for the local backend, never browser JavaScript.
  if (request.headers.has("Origin")) return error("invalid_request", 403);
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const limited = await env.TOKEN_RATE_LIMITER.limit({key: ip});
  if (!limited.success) return error("temporarily_unavailable", 429);
  if (request.headers.get("Content-Type")?.split(";")[0].trim() !== "application/x-www-form-urlencoded") return error("invalid_request", 415);
  let fields;
  try { fields = new URLSearchParams(await boundedBody(request)); }
  catch { return error("invalid_request", 413); }
  const allowed = new Set(["grant_type", "client_id", "client_secret", "code", "code_verifier", "redirect_uri", "refresh_token", "scope"]);
  for (const key of fields.keys()) {
    if (!allowed.has(key) || fields.getAll(key).length !== 1) return error("invalid_request");
  }
  if (fields.get("client_id") !== env.GOOGLE_CLIENT_ID || fields.get("client_secret")) return error("invalid_client");
  const body = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    grant_type: fields.get("grant_type") || "",
  });
  if (fields.get("grant_type") === "authorization_code") {
    if (!fields.get("code") || fields.get("code").length > 4096
        || !/^[A-Za-z0-9._~-]{43,128}$/.test(fields.get("code_verifier") || "")
        || !localCallback(fields.get("redirect_uri")) || fields.has("refresh_token")) return error("invalid_request");
    for (const key of ["code", "code_verifier", "redirect_uri"]) body.set(key, fields.get(key));
  } else if (fields.get("grant_type") === "refresh_token") {
    if (!fields.get("refresh_token") || fields.get("refresh_token").length > 4096
        || ["code", "code_verifier", "redirect_uri"].some(key => fields.has(key))) return error("invalid_request");
    body.set("refresh_token", fields.get("refresh_token"));
    // Omitting scope retains the original grant and cannot broaden it.
  } else return error("unsupported_grant_type");
  let stage = "upstream_transport";
  try {
    const response = await upstream(TOKEN_URL, {
      method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body, redirect: "manual", signal: AbortSignal.timeout(15000),
    });
    if (response.status >= 300 && response.status < 400) {
      return error("temporarily_unavailable", 502, "upstream_redirect_rejected");
    }
    stage = "upstream_response";
    const data = await response.json();
    if (!response.ok) {
      const code = Object.hasOwn(ERRORS, data.error) ? data.error : "temporarily_unavailable";
      return error(code, response.status >= 500 || response.status === 429 ? 503 : 400, `google_http_${response.status}`);
    }
    if (typeof data.access_token !== "string" || typeof data.expires_in !== "number") return error("temporarily_unavailable", 502);
    const result = {};
    for (const key of ["access_token", "refresh_token", "expires_in", "scope", "token_type", "id_token", "refresh_token_expires_in"]) {
      if (data[key] !== undefined) result[key] = data[key];
    }
    return json(result);
  } catch (failure) {
    const category = /[Ii]llegal invocation|this.*reference/.test(failure?.message || "")
      ? "fetch_binding" : /redirect/.test(failure?.message || "")
      ? "redirect" : /AbortSignal|timeout/.test(failure?.message || "")
      ? "timeout" : "transport";
    return error("temporarily_unavailable", 503, `${stage}_${category}`);
  }
}

export default {fetch(request, env) { return handle(request, env); }};

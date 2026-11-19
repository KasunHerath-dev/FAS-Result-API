---
name: secure-api-builder
description: Use when designing, building, or reviewing a REST/HTTP API so it follows a full security checklist: auth, access control, input validation, rate limits, headers, secrets and more.
---

# Secure API Builder

Use this whenever you build a new API, add endpoints, or review existing API code. Work through every section below. When writing code, apply the rules directly; when reviewing, report each problem with the file/line, why it matters, and the fix.

Note: no API is ever "100% secure". The goal is defense in depth: many layers, so one mistake does not expose everything.

## 1. Authentication (who are you?)
- Use a proven standard: OAuth 2.0 / OpenID Connect, or JWT issued by your own auth service. Never invent your own crypto or token format.
- Passwords: hash with Argon2id or bcrypt (cost >= 12). Never store plain text, MD5 or SHA-1.
- JWT rules:
  - Always verify the signature; reject `alg: none`; pin the expected algorithm.
  - Check `exp`, `iss`, `aud`.
  - Do not put secrets or personal data in the payload (it is only base64, not encrypted).
- Token expiration: short-lived access tokens (5-15 min) + refresh tokens with rotation and revocation.
- Store tokens in the browser in `HttpOnly; Secure; SameSite` cookies, not localStorage, when possible.
- Offer MFA for sensitive accounts.
- API keys (for machine clients): random, high-entropy, stored hashed, scoped, rotatable.

## 2. Authorization / Access Control (what may you do?)
- Check permissions on EVERY request, server-side. Deny by default.
- Granular roles/scopes per endpoint (RBAC or ABAC).
- Object-level checks (OWASP API #1, BOLA/IDOR): `GET /orders/123` must verify order 123 belongs to the caller.
- Function-level checks: admin endpoints must verify admin role, not just be "hidden".
- Property-level checks: never let a client set fields like `role`, `isAdmin`, `balance` (mass assignment). Use explicit allow-lists / DTOs.

## 3. Transport Security
- HTTPS (TLS 1.2+) everywhere, including internal services. Redirect HTTP -> HTTPS.
- Send HSTS: `Strict-Transport-Security: max-age=31536000; includeSubDomains`.

## 4. Input Validation & Sanitization
- Validate every input (body, query, params, headers) against a schema (Zod, Joi, Pydantic, JSON Schema): type, length, format, range, enum.
- Reject unknown fields.
- SQL: parameterized queries / ORM only. Never build SQL with string concatenation.
- Also guard against NoSQL injection, command injection, path traversal (`../`), and XSS when data is later rendered.
- Limit request body size (e.g. 1 MB) and array lengths.
- File uploads: check type by content (not just extension), size limit, random filename, store outside web root, scan if possible.
- SSRF: if the API fetches user-supplied URLs, allow-list domains and block internal IPs (169.254.x.x, 10.x, 127.x, localhost).

## 5. Output: only return what is needed
- Never return whole DB objects. Use response DTOs; strip password hashes, internal IDs, tokens.
- Paginate lists and cap `limit` (e.g. max 100).

## 6. Rate Limiting & Abuse Protection
- Global and per-user/per-IP rate limits; return `429 Too Many Requests` with `Retry-After`.
- Throttle login attempts: progressive delay or temporary lockout + CAPTCHA after repeated failures. Same for OTP, password reset.
- Set timeouts on requests, DB queries and outbound calls.
- Use idempotency keys for payment/create operations.

## 7. Error Handling
- Generic messages to clients ("Invalid email or password", not "email not found").
- No stack traces, SQL errors, framework versions, or file paths in responses. Disable debug/default error pages in production.
- Log full details server-side with a request ID; return only the request ID to the client.

## 8. Security Headers
- `Content-Security-Policy` (for any HTML responses)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` (or CSP `frame-ancestors 'none'`)
- `Referrer-Policy: no-referrer`
- `Strict-Transport-Security` (see section 3)
- Remove `X-Powered-By` / server version headers.
- Note: `X-XSS-Protection` is deprecated in modern browsers; set it to `0` or omit it and rely on CSP.

## 9. CORS
- Allow-list exact trusted origins. Never use `*` together with credentials.
- Restrict allowed methods and headers.
- CORS is not authentication; still check auth on every request.

## 10. CSRF
- Needed when auth uses cookies: use CSRF tokens and/or `SameSite=Lax/Strict` cookies, and check `Origin`.
- Pure bearer-token APIs (Authorization header) are not exposed to classic CSRF.

## 11. Session Management
- Regenerate session ID on login; invalidate on logout, password change, and role change.
- Idle and absolute session timeouts.
- Allow users to see/revoke active sessions.

## 12. Data Protection
- Encrypt in transit (TLS) and at rest (DB/disk encryption; field-level encryption for very sensitive data).
- Secrets (DB passwords, API keys, JWT keys) in env vars or a secret manager, never in code or git. Add `.env` to `.gitignore`.
- Database user with least privilege (no root/superuser for the app).
- Collect only data you need; define retention and deletion.

## 13. Logging, Monitoring & Auditing
- Log auth events, permission failures, admin actions, rate-limit hits, with timestamp, user ID, IP, request ID.
- Never log passwords, tokens, card numbers or full personal data.
- Alert on unusual patterns (many 401/403, spikes).
- Protect logs from tampering.

## 14. API Versioning & Inventory
- Version the API (`/v1/...` or header). Keep backward compatibility; announce deprecation.
- Keep an inventory of all endpoints and environments; shut down old/unused versions and test endpoints (OWASP API #9).

## 15. Safe Documentation
- Public docs (OpenAPI/Swagger) must not contain real keys, internal hosts, or hidden admin endpoints.
- Disable Swagger UI in production or put it behind auth.

## 16. Third-party & Webhooks
- Verify webhook signatures (HMAC) and timestamps to block replays.
- Treat data from other APIs as untrusted input; validate it.

## 17. Dependencies & Updates
- Keep framework, libraries, runtime and OS patched.
- Run `npm audit` / `pip-audit` / Dependabot / Snyk in CI. Pin versions with a lockfile.

## 18. Security Testing
- Automated tests for authz (user A cannot read user B's data).
- SAST + dependency scanning in CI; DAST (e.g. OWASP ZAP) against staging.
- Periodic penetration test; follow OWASP API Security Top 10.

## Example (Node.js / Express baseline)
```js
import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import rateLimit from 'express-rate-limit';

const app = express();
app.disable('x-powered-by');
app.use(helmet());
app.use(express.json({ limit: '1mb' }));
app.use(cors({ origin: ['https://myapp.com'], credentials: true }));
app.use('/api', rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));
app.use('/api/auth/login', rateLimit({ windowMs: 15 * 60 * 1000, max: 5 }));

// Generic error handler: no internals leaked
app.use((err, req, res, next) => {
  console.error(req.id, err);
  res.status(err.status || 500).json({ error: 'Something went wrong', requestId: req.id });
});
```

## Final checklist before shipping
- [ ] Every endpoint has auth + object-level authorization
- [ ] All inputs schema-validated; queries parameterized
- [ ] HTTPS + HSTS; security headers set
- [ ] Rate limits + login throttling
- [ ] Short-lived tokens, refresh rotation, logout invalidation
- [ ] Generic errors; debug off
- [ ] CORS allow-list; CSRF handled if cookies used
- [ ] Secrets out of code; least-privilege DB user
- [ ] Logs without sensitive data; alerts set
- [ ] Dependencies scanned; security tests in CI
- [ ] Docs safe; old versions retired

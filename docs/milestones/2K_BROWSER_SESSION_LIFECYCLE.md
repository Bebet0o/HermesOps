# Milestone 2K — Browser Session Lifecycle

Milestone 2K adds the authentication boundary required by the dedicated
HermesOps Console without removing the private Controller token used by local
service probes and administrative scripts.

## Runtime routes

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/logout`
- existing `POST /api/v1/auth/csrf`

The browser sends credentials only in the JSON login body. The response never
contains a password or session token. A successful login returns the
`hermesops_session` cookie with `HttpOnly`, `Secure`, `SameSite=Strict`, and a
bounded lifetime.

## Persistence

Migration 017 adds:

- one local operator credential using Python/OpenSSL `scrypt`;
- browser sessions stored only by SHA-256 token hash;
- keyed authentication idempotency records;
- immutable authentication audit records;
- revocation timestamps used by HTTP and WebSocket authentication.

Raw passwords, raw browser tokens, CSRF tokens and idempotency keys are not
persisted. Browser tokens use the explicit `bws_` namespace, so a rotated or
stale bootstrap token is rejected as `401` before any browser-session database
lookup.

## Compatibility boundary

The existing `/opt/docker/hermesops/secrets/controller-session` value remains a
private bootstrap credential for local probes and CLI automation. It is not the
operator password and is never returned to the Console. Browser sessions and
the bootstrap credential share the existing cookie name only so all established
Controller route, cursor and CSRF code keeps one authenticated secret boundary.

## Initial operator password

On first service start after migration 017, the Controller creates one operator
credential and writes the generated initial password to:

```text
/opt/docker/hermesops/secrets/controller-initial-password
```

The file is owned by the service user with mode `0600`. The password is never
printed to logs. The operator should replace it interactively with:

```bash
python3 scripts/hermesops-controller-operator.py set-password
```

Changing the password revokes every browser session and removes the initial
password file.

## Browser origin and CORS

Only the configured Console origin may perform credentialed browser requests.
The default is `http://127.0.0.1:8787`. Preflight requests are limited to the
Controller API methods and headers required by the Console. Arbitrary origins,
headers, methods, paths and credentials in URLs are rejected.

## Invalidation

Logout revokes the durable browser session. HTTP requests immediately return
`401`, and open event WebSockets close with policy code `1008` during their next
bounded session check. Rotation of the bootstrap Controller token continues to
invalidate bootstrap connections as before.

## Non-goals

- multiple users or external identity providers;
- password recovery over the network;
- bearer tokens in URLs;
- direct Console access to SQLite, Docker or Hermes Agent;
- removal of the local probe credential.

## Adversarial hardening

The final 2K review adds migration 018 and enforces the following properties:

- password derivation occurs outside SQLite write transactions;
- at most two scrypt derivations execute concurrently per Controller process;
- malformed durable credentials fail readiness and login with service-unavailable semantics;
- logout replay remains idempotent after the browser session has been revoked;
- repeated blocked attempts do not indefinitely extend the lockout window or amplify audit rows;
- browser session identity and expiry fields are immutable after insertion;
- authentication idempotency rows are immutable;
- authentication timestamps are canonical RFC 3339 UTC values;
- a failed initial-password write removes the partial secret file.

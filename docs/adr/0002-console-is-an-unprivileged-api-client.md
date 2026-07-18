# ADR 0002: Console Is an Unprivileged API Client

Status: **Accepted**
Date: 2026-07-18

## Context

HermesOps Console will expose powerful operations such as project creation,
run cancellation, recovery, sandbox activation, backup restore, and secret
configuration.

Giving the WebUI direct access to Docker, filesystem paths, SQLite, or Hermes
Agent would expand the browser trust boundary and make safe policy enforcement
impossible.

## Decision

HermesOps Console communicates only with the authenticated Controller HTTP and
WebSocket APIs.

It receives structured read models and submits structured commands.

It never receives:

- Docker sockets;
- database files;
- arbitrary server shell access;
- provider secret values;
- direct Hermes Agent credentials.

Dangerous commands are evaluated and confirmed by the Controller.

## Consequences

Positive:

- browser compromise has a smaller blast radius;
- server implementation details remain private;
- all commands are validated and audited;
- the same Controller API can support a future CLI or automation client.

Costs:

- the Controller must expose every supported operator workflow;
- UI development depends on explicit API contracts;
- low-level emergency repair remains a terminal operation.

## Rejected alternatives

### Embed a server terminal

Rejected for the first beta because it bypasses command semantics and
confirmation policy.

### Proxy Docker API through the browser

Rejected because it exposes an implementation primitive instead of safe
HermesOps intent.

### Let the Console call Hermes Agent directly

Rejected because Agent output must be normalized and reconciled with durable
Controller state.

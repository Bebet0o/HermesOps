# Milestone 2J — Authenticated WebSocket transport

Milestone 2J exposes the durable Controller journal implemented by milestone 2I
through an authenticated RFC 6455 stream.

## Scope

- same loopback listener as the Controller HTTP API;
- endpoint `ws://127.0.0.1:8765/api/v1/events`;
- Python standard library only;
- Controller session cookie authentication;
- exact configured Console `Origin` validation;
- bounded concurrent connections;
- replay from `Last-Event-Sequence` or a `subscribe` frame;
- topic filtering without changing global sequence semantics;
- at-least-once ordered delivery from the durable journal;
- replay-unavailable snapshot fallback;
- heartbeat frames;
- ping, pong and close handling;
- bounded masked client frames;
- automatic stream invalidation after session rotation;
- no credentials or replay cursor in query strings.

## Defaults

| Setting | Default |
| --- | --- |
| Controller endpoint | `ws://127.0.0.1:8765/api/v1/events` |
| Console origin | `http://127.0.0.1:8787` |
| Maximum WebSocket connections | `8` |
| Maximum client frame | `65536` bytes |
| Replay batch | `100` events |
| Heartbeat | `15` seconds |
| Subscription timeout | `5` seconds |

The Console origin can be changed with
`HERMESOPS_CONTROLLER_CONSOLE_ORIGIN`. The connection limit can be changed with
`HERMESOPS_CONTROLLER_MAX_WEBSOCKETS`; invalid values make the Controller fail
closed during startup validation.

## Subscription

A client may provide `Last-Event-Sequence` during the handshake. This starts an
immediate all-topic subscription. Otherwise the first text frame must be:

```json
{
  "type": "subscribe",
  "after_sequence": 0,
  "topics": ["objectives", "runs", "reviews"]
}
```

An empty topic list means all topics. `all` is also accepted but must be the
only topic.

Topic filters affect delivery only. The server cursor still advances across
non-matching durable events, preserving the global sequence and preventing
replay loops.

## Failure behavior

Handshake failures remain HTTP problem responses. After upgrade, protocol and
policy failures use WebSocket close frames. A cursor outside the retained
journal window receives `replay_unavailable` followed by a normal close, and
the client must refresh authoritative HTTP snapshots before reconnecting.

The WebSocket transport is not an authoritative state store. HTTP snapshots and
Controller command responses remain authoritative.

## Adversarial hardening

The final review reserves normal HTTP request capacity while WebSocket sessions
are open, redacts all query values from HTTP access logs, requires HTTP/1.1 for
RFC 6455 upgrades, and validates close codes and UTF-8 close reasons. Replay is
limited to 500 global journal events; clients outside that window receive
`replay_unavailable` and must refresh authoritative HTTP snapshots. Replay work
is yielded between batches so session rotation, heartbeats, pings, and close
frames remain responsive under sustained event load.

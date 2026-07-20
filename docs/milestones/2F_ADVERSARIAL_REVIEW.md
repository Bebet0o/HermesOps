# Milestone 2F adversarial review RC2

RC1 reproduced ten weaknesses and passed every local regression suite, but the
installed-service probe returned HTTP 503 on the real review row. The failure
occurred before commit and the transactional rollback restored the published
feature head.

## Root-cause class

Two RC1 rules coupled immutable historical execution records to mutable current
role policy:

- historical reviewer CPU and memory snapshots had to equal the current role
  limits;
- current commit, push, and network policy changes could hide historical
  reviewer or recovery records.

RC1 also rejected any structured payload deeper than sixteen levels or larger
than 1,024 JSON nodes, although the endpoint never returns nested values and
already enforces a 64 KiB source limit.

## RC2 semantics

RC2 keeps the ten useful protections while using the correct time domain:

- stored reviewer workspace must remain `read_only`;
- stored reviewer network access must remain disabled;
- stored CPU and memory values remain type-checked and bounded;
- role identity, kind, profile, workspace class, network invariant, and enabled
  state remain verified where recorded and meaningful;
- current mutable resource and mutation settings do not retroactively invalidate
  past records;
- review and recovery JSON remain capped at 64 KiB and 256 top-level entries;
- only safe first-level field names are returned; nested values are never
  projected;
- malformed, oversized, or recursive-parser failures remain fail-closed;
- opaque transaction references remain aligned with the 2E domain;
- filtered pagination, decision/outcome consistency, redaction, ETags, cursor
  binding, and read-only behavior remain covered.

No route, migration, database write, raw artifact access, or systemd change is
introduced.

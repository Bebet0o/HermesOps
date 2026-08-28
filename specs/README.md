# HermesOps Machine-Readable Contracts

This directory contains machine-readable contracts created during the 0.2
design and implementation milestones. The product release is HermesOps 0.2.0;
individual API and schema versions remain independent contracts.

- `controller-api-v1.openapi.json`: OpenAPI 3.1 Controller HTTP contract.
- `events-v1.schema.json`: JSON Schema for persisted event envelopes.
- `hermesfile-v0.schema.json`: JSON Schema for parsed Hermesfile v0 data.

They are validated by:

```text
tests/test-controller-contracts.sh
```

Schemas alone are not proof that a runtime feature exists. Current support is
documented by the corresponding integration/security tests and product docs.

- `controller-events-v1.asyncapi.json`: authenticated replayable WebSocket transport.
- `hermesfile-v1.schema.json`: executable source contract for Hermesfile v1 sandbox profiles.

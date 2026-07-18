# ADR 0006: Dangerous Actions Require Controller Confirmation

Status: **Accepted**
Date: 2026-07-18

## Context

HermesOps automates Git transactions, recovery, sandbox activation, backup
restore, project deletion, and policy changes. Some valid actions can discard
work or broaden execution permissions.

A simple browser confirmation dialog is insufficient because a compromised or
buggy client could bypass it.

## Decision

The Controller evaluates risk and creates a server-side confirmation record for
dangerous commands.

The record seals:

- actor;
- target;
- normalized original command;
- consequences;
- risk class;
- expiration;
- optional typed phrase.

The follow-up request references the confirmation ID and cannot change the
original command.

Confirmations are actor-bound, single-use, expiring, and audited.

## Consequences

Positive:

- safety does not depend on UI behavior;
- command parameters cannot change between warning and execution;
- recovery and destructive actions have clear evidence;
- CLI and Console use the same safety mechanism.

Costs:

- dangerous workflows require an extra round trip;
- confirmation lifecycle and expiration must be implemented;
- automation clients cannot silently bypass human gates.

## Rejected alternatives

### Browser-only `confirm()`

Rejected because it is not authoritative and is easy to bypass.

### Global “dangerous mode” toggle

Rejected because broad standing permission weakens contextual review.

### Never allow destructive actions

Rejected because legitimate recovery, restore, cleanup, and uninstall
operations still need a controlled path.

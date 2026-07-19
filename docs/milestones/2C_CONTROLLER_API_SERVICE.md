# Milestone 2C — Durable Controller API service

## Status

Implementation milestone. This installs the read-only Controller API from
Milestone 2B as a durable systemd user service.

## Scope

Milestone 2C adds:

- `hermesops-controller-api.service` under the existing user-service model;
- secure, idempotent generation of the local Controller session file;
- authenticated health probing without exposing the session value;
- automatic enablement and startup through `install.sh`;
- conservative removal through `uninstall.sh` while preserving the session;
- static installation-contract tests;
- real start, restart, stop, and start lifecycle validation;
- runtime validation of service activity and all three probes.

## Runtime paths

| Resource | Path |
| --- | --- |
| Repository | `/opt/docker/hermesops/repo` |
| SQLite database | `/opt/docker/hermesops/state/controller/hermesops.db` |
| Session file | `/opt/docker/hermesops/secrets/controller-session` |
| Installed unit | `~/.config/systemd/user/hermesops-controller-api.service` |
| Listen address | `127.0.0.1:8765` |

## Session lifecycle

The session helper never prints the session value. It validates that:

- the secrets directory is owned by the service user and has mode `0700`;
- the session is a regular file owned by the service user;
- the file has mode `0600` and exactly one hard link;
- symbolic links are rejected with `O_NOFOLLOW`;
- the value is ASCII and matches the Controller API session format.

Commands:

```bash
scripts/hermesops-controller-session.py ensure
scripts/hermesops-controller-session.py check
scripts/hermesops-controller-session.py rotate
```

`ensure` is idempotent. `rotate` replaces the session atomically. Rotation
invalidates existing Console cookies and requires a Controller API restart only
if a future implementation caches the token; Milestone 2B reads it for every
protected request.

## Service startup

The service performs these steps:

1. validate the session file;
2. validate Controller database readiness;
3. start the API on `127.0.0.1:8765`;
4. probe `/health`, `/ready`, and authenticated capabilities;
5. report startup failure to systemd if any probe fails.

The service remains loopback-only. It is not suitable for direct Internet or
LAN exposure.

## Hardening

The unit uses:

- `NoNewPrivileges=true`;
- private temporary and device namespaces;
- read-only system mounts;
- hidden home directories;
- kernel/control-group protections;
- namespace, realtime, and SUID restrictions;
- write/execute memory denial;
- address-family restriction to Unix and IP sockets;
- `UMask=0077`;
- bounded startup and shutdown timeouts.

## Installer behavior

A normal installation or upgrade:

- creates or validates the session before installing the unit;
- copies all user units;
- enables and restarts the Controller after existing HermesOps services;
- verifies every service is active;
- performs an authenticated Controller probe.

`--skip-start` still installs the unit and creates the session, but does not
enable or start any service.

## Uninstall behavior

The conservative uninstaller stops and removes the Controller unit before
stopping Docker services. The session file is intentionally preserved with the
other HermesOps secrets and state.

## Non-goals

- final login/session endpoints;
- reverse proxy or TLS;
- LAN or Internet binding;
- Controller write endpoints;
- database migrations;
- Console code;
- secret display or export.


## systemd user-manager portability correction

The first real lifecycle execution failed before Python started with
`status=218/CAPABILITIES`. The original user unit used `PrivateDevices=true`
and multiple `ProtectKernel*` directives. Those settings alter capability
bounding sets or require private user/mount namespaces that are not portable
to every non-root `systemd --user` manager.

RC2 keeps portable controls only: `NoNewPrivileges`, `RestrictSUIDSGID`,
`RestrictRealtime`, `RestrictNamespaces`, `LockPersonality`,
`MemoryDenyWriteExecute`, the restricted address-family list and `UMask=0077`.

The principal security boundary remains loopback-only binding, private local
session authentication, SQLite `mode=ro` plus `PRAGMA query_only`, disabled HTTP
mutation methods, and omission of host paths from API responses.

The lifecycle test now dumps complete systemd status and journal output before
rollback whenever a future startup fails.

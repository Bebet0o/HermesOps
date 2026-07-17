#!/usr/bin/env python3
"""HermesOps entrypoint for a controller-created reusable sandbox."""

from __future__ import annotations

import os
from typing import Any

from tools import credential_files

credential_files.get_credential_file_mounts = lambda: []
credential_files.get_skills_directory_mount = lambda: []
credential_files.get_cache_directory_mounts = lambda: []

task_id = os.environ.get("HERMESOPS_SANDBOX_TASK_ID", "").strip()
profile_name = os.environ.get("HERMESOPS_SANDBOX_PROFILE", "").strip()

if not task_id or not profile_name:
    raise RuntimeError("HermesOps sandbox reuse identity is absent")

from tools.environments import docker as docker_backend

docker_backend._get_active_profile_name = lambda: profile_name
_original_docker_init = docker_backend.DockerEnvironment.__init__


def _strip_network_args(arguments: list[str] | None) -> list[str]:
    source = list(arguments or [])
    result: list[str] = []
    index = 0

    while index < len(source):
        token = source[index]

        if token == "--network":
            index += 2
            continue

        if token.startswith("--network="):
            index += 1
            continue

        result.append(token)
        index += 1

    return result


def _hermesops_docker_init(
    self: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    kwargs["network"] = False
    kwargs["disk"] = 0
    kwargs["persist_across_processes"] = True
    kwargs["extra_args"] = _strip_network_args(
        kwargs.get("extra_args")
    )
    _original_docker_init(self, *args, **kwargs)


docker_backend.DockerEnvironment.__init__ = _hermesops_docker_init

from tools import terminal_tool as terminal_runtime

_original_get_env_config = terminal_runtime._get_env_config


def _hermesops_get_env_config() -> dict[str, Any]:
    config = _original_get_env_config()

    if config.get("env_type") == "docker":
        config["docker_network"] = False
        config["container_disk"] = 0
        config["docker_persist_across_processes"] = True
        config["docker_orphan_reaper"] = False
        config["docker_extra_args"] = []

    return config


terminal_runtime._resolve_container_task_id = lambda _: task_id
terminal_runtime._get_env_config = _hermesops_get_env_config
terminal_runtime._DockerEnvironment = docker_backend.DockerEnvironment

effective = terminal_runtime._get_env_config()

if effective.get("env_type") != "docker":
    raise RuntimeError("HermesOps terminal backend is not Docker")

if effective.get("docker_network") is not False:
    raise RuntimeError("HermesOps network lockdown is not active")

print("HERMESOPS_SANDBOX_AUTOMOUNTS_DISABLED", flush=True)
print(
    "HERMESOPS_PRECREATED_SANDBOX_REUSE "
    f"task={task_id} profile={profile_name}",
    flush=True,
)

from hermes_cli.main import main

if __name__ == "__main__":
    main()

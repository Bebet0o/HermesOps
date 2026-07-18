#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
REPO="${ROOT}/repo"
TARGET_USER=""
REMOVE_REPO=0
CONFIRM=""

while (($#)); do
    case "$1" in
        --user) TARGET_USER="${2:?Utilisateur manquant}"; shift 2 ;;
        --remove-repo) REMOVE_REPO=1; shift ;;
        --confirm) CONFIRM="${2:-}"; shift 2 ;;
        -h|--help)
            echo "Usage: ./uninstall.sh [--user USER] [--remove-repo --confirm REMOVE_REPO]"
            exit 0
            ;;
        *) echo "Option inconnue: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$TARGET_USER" ]]; then
    [[ "$EUID" == 0 ]] && TARGET_USER="${SUDO_USER:-}" || TARGET_USER="$(id -un)"
fi
[[ -n "$TARGET_USER" ]] || { echo "Préciser --user USER." >&2; exit 1; }
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

sudo_run() { [[ "$EUID" == 0 ]] && "$@" || sudo "$@"; }
user_run() {
    if [[ "$(id -u)" == "$TARGET_UID" ]]; then
        "$@"
    elif [[ "$EUID" == 0 ]]; then
        runuser -u "$TARGET_USER" -- env \
            HOME="$TARGET_HOME" USER="$TARGET_USER" LOGNAME="$TARGET_USER" \
            XDG_RUNTIME_DIR="/run/user/${TARGET_UID}" "$@"
    else
        sudo -u "$TARGET_USER" env HOME="$TARGET_HOME" USER="$TARGET_USER" \
            LOGNAME="$TARGET_USER" XDG_RUNTIME_DIR="/run/user/${TARGET_UID}" "$@"
    fi
}

for unit in hermesops-notifier.service hermesops-orchestrator.service hermesops-supervisor.service; do
    user_run systemctl --user disable --now "$unit" 2>/dev/null || true
done
for unit in hermesops-notifier.service hermesops-orchestrator.service hermesops-supervisor.service; do
    sudo_run rm -f "${TARGET_HOME}/.config/systemd/user/${unit}"
done
user_run systemctl --user daemon-reload 2>/dev/null || true

if [[ -x "${REPO}/scripts/hermes-agent-compose.sh" ]]; then
    user_run env HERMESOPS_ROOT="$ROOT" "${REPO}/scripts/hermes-agent-compose.sh" down || true
fi

if [[ "$REMOVE_REPO" == 1 ]]; then
    [[ "$CONFIRM" == "REMOVE_REPO" ]] || {
        echo "Suppression refusée. Utiliser --confirm REMOVE_REPO." >&2
        exit 1
    }
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    BACKUP="${ROOT}/backups/uninstall-${STAMP}"
    sudo_run install -d -m 0750 -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" "$BACKUP"
    if [[ -d "$REPO/.git" ]]; then
        user_run git -C "$REPO" bundle create "${BACKUP}/hermesops-before-uninstall.bundle" --all
        user_run git -C "$REPO" bundle verify "${BACKUP}/hermesops-before-uninstall.bundle"
    fi
    sudo_run rm -rf "$REPO"
fi

echo "HERMESOPS_UNINSTALL_PASS"
echo "État, secrets, workspaces, données projet et backups conservés."

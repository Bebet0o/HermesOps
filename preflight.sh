#!/usr/bin/env bash
set -uo pipefail
export LC_ALL=C
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
TARGET_USER="${USER:-$(id -un)}"
CI_MODE=0

while (($#)); do
    case "$1" in
        --target-user)
            TARGET_USER="${2:?Utilisateur manquant}"
            shift 2
            ;;
        --ci)
            CI_MODE=1
            shift
            ;;
        --help|-h)
            cat <<'HELP'
Usage: ./preflight.sh [--target-user USER] [--ci]

Lecture seule. Vérifie Debian 12, Docker, Compose, dépendances,
ports et contenu public du dépôt.
HELP
            exit 0
            ;;
        *)
            echo "Option inconnue: $1" >&2
            exit 2
            ;;
    esac
done

FAILURES=0
WARNINGS=0
pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf 'FAIL  %s\n' "$*"; FAILURES=$((FAILURES + 1)); }

printf 'HermesOps preflight\n'
printf 'Source       : %s\n' "$SOURCE"
printf 'Racine cible : %s\n' "$ROOT"
printf 'Utilisateur  : %s\n\n' "$TARGET_USER"

if [[ "$CI_MODE" == 0 ]]; then
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        [[ "${ID:-}" == "debian" && "${VERSION_ID:-}" == "12" ]] \
            && pass "Debian 12 détecté" \
            || fail "Debian 12 requis"
    else
        fail "/etc/os-release absent"
    fi

    ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
    [[ "$ARCH" == "amd64" || "$ARCH" == "x86_64" ]] \
        && pass "Architecture amd64" \
        || fail "Architecture non prise en charge: $ARCH"
fi

for command_name in \
    bash tar sha256sum systemctl loginctl timeout flock install \
    stat find grep sed awk apt-get apt-cache dpkg-query getent
 do
    command -v "$command_name" >/dev/null 2>&1 \
        && pass "Commande système présente: $command_name" \
        || fail "Commande système absente: $command_name"
done

STATIC_VALIDATION_READY=1

for command_name in git python3 sqlite3 curl rsync gzip; do
    if command -v "$command_name" >/dev/null 2>&1; then
        pass "Dépendance présente: $command_name"
    else
        warn "Dépendance absente; install.sh peut installer: $command_name"
        case "$command_name" in
            python3|sqlite3|rsync)
                STATIC_VALIDATION_READY=0
                ;;
        esac
    fi
done

if command -v runuser >/dev/null 2>&1; then
    pass "Commande système présente: runuser"
else
    warn "runuser absent; install.sh installera le paquet util-linux"
fi

if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY' >/dev/null 2>&1
import yaml
PY
    then
        pass "Module Python yaml présent"
    else
        warn "Module Python yaml absent; install.sh installera python3-yaml"
        STATIC_VALIDATION_READY=0
    fi
else
    warn "Contrôle du module yaml reporté"
    STATIC_VALIDATION_READY=0
fi

if [[ "$EUID" != 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    fail "sudo absent pour une installation non-root"
fi

if [[ "$CI_MODE" == 0 ]]; then
    command -v docker >/dev/null 2>&1 || warn "Docker absent; install.sh peut installer Docker CE"
    if command -v docker >/dev/null 2>&1; then
        docker version >/dev/null 2>&1 \
            && pass "Docker Engine accessible" \
            || warn "Docker Engine inaccessible; install.sh tentera de le démarrer"
        docker compose version >/dev/null 2>&1 \
            && pass "Docker Compose disponible" \
            || warn "Plugin Docker Compose absent; install.sh peut l’installer"
    fi

    id "$TARGET_USER" >/dev/null 2>&1 \
        && pass "Utilisateur cible présent" \
        || fail "Utilisateur cible absent: $TARGET_USER"
    if id "$TARGET_USER" >/dev/null 2>&1; then
        TARGET_UID="$(id -u "$TARGET_USER")"
        TARGET_GID="$(id -g "$TARGET_USER")"
        [[ "$TARGET_UID" == "1000" && "$TARGET_GID" == "1000" ]] \
            && pass "Contrat UID/GID 1000:1000" \
            || fail "0.1.0-alpha exige UID/GID 1000:1000; observé ${TARGET_UID}:${TARGET_GID}"
        id -nG "$TARGET_USER" | tr ' ' '\n' | grep -Fxq docker \
            && pass "Utilisateur membre du groupe docker" \
            || warn "install.sh ajoutera $TARGET_USER au groupe docker puis demandera une reconnexion"
    fi

    for port in 8642 8787; do
        if command -v ss >/dev/null 2>&1 &&
           ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q .; then
            if docker ps --format '{{.Names}}' 2>/dev/null |
               grep -Eq '^hermesops-(agent|webui)$'; then
                warn "Port ${port} déjà utilisé par l'installation HermesOps"
            else
                fail "Port ${port} déjà utilisé"
            fi
        else
            pass "Port ${port} disponible"
        fi
    done
fi

for required in \
    VERSION README.md compose/agent.yaml compose/images.lock.env \
    config/controller.toml config/roles.toml migrations \
    profiles scripts systemd/user tests
do
    [[ -e "${SOURCE}/${required}" ]] \
        && pass "Présent: ${required}" \
        || fail "Absent: ${required}"
done

if [[ -x "${SOURCE}/scripts/check-secrets.sh" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        "${SOURCE}/scripts/check-secrets.sh" --root "$SOURCE" \
            && pass "Contrôle anti-secrets" \
            || fail "Contrôle anti-secrets"
    else
        warn "Contrôle anti-secrets reporté jusqu’à l’installation de Python"
    fi
else
    fail "scripts/check-secrets.sh absent"
fi

if [[ -x "${SOURCE}/validate.sh" ]]; then
    if [[ "$STATIC_VALIDATION_READY" == "1" ]] &&
       command -v docker >/dev/null 2>&1 &&
       docker compose version >/dev/null 2>&1; then
        "${SOURCE}/validate.sh" --static --quiet \
            && pass "Validation statique complète" \
            || fail "Validation statique complète"
    else
        warn "Validation statique complète reportée après installation des dépendances"
    fi
else
    fail "validate.sh absent"
fi

printf '\nRésumé: failures=%d warnings=%d\n' "$FAILURES" "$WARNINGS"
if ((FAILURES)); then
    echo "HERMESOPS_PREFLIGHT_FAIL"
    exit 1
fi
echo "HERMESOPS_PREFLIGHT_PASS"

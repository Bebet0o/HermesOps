#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT="/opt/docker/hermesops"
SECRET_DIR="${ROOT}/secrets"
SECRET_FILE="${SECRET_DIR}/notifications.env"
NOTIFIER="${ROOT}/repo/scripts/hermesops-notifier.py"
UNIT="hermesops-notifier.service"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

[[ "$(id -un)" == "trader" ]] || {
    echo "Ce script doit être lancé sous trader." >&2
    exit 1
}

read -rsp "Token du bot Telegram : " BOT_TOKEN
echo
read -rp "Chat ID Telegram : " CHAT_ID

[[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{20,}$ ]] || {
    echo "Format de token Telegram invalide." >&2
    exit 1
}
[[ "$CHAT_ID" =~ ^-?[0-9]+$ ]] || {
    echo "Chat ID Telegram invalide." >&2
    exit 1
}

install -d -m 0700 "$SECRET_DIR"
umask 077
TEMP="$(mktemp "${SECRET_DIR}/notifications.env.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT

cat >"$TEMP" <<EOF
HERMESOPS_TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
HERMESOPS_TELEGRAM_CHAT_ID=${CHAT_ID}
EOF

chmod 0600 "$TEMP"
mv "$TEMP" "$SECRET_FILE"
trap - EXIT

systemctl --user restart "$UNIT"
for _ in $(seq 1 30); do
    [[ "$(systemctl --user is-active "$UNIT" 2>/dev/null || true)" == "active" ]] && break
    sleep 1
done

"$NOTIFIER" test-message \
    --channel TELEGRAM \
    --text "HermesOps : notifications Telegram activées." \
    --dedupe-key "telegram-configuration-test-$(date +%s)" \
    --deliver

echo
echo "Configuration Telegram enregistrée dans : ${SECRET_FILE}"
echo "Service : $(systemctl --user is-active "$UNIT")"

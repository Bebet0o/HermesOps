#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT="${HERMESOPS_ROOT:-/opt/docker/hermesops}"
FIXTURE_ROOT="${ROOT}/workspaces/.fixtures"
DATA_ROOT="${ROOT}/project-data/.fixtures"
PRIMARY="${FIXTURE_ROOT}/transaction-fixture"
SECONDARY="${FIXTURE_ROOT}/transaction-fixture-b"

mkdir -p "$FIXTURE_ROOT" "$DATA_ROOT/transaction-fixture" "$DATA_ROOT/transaction-fixture-b"

create_primary() {
    mkdir -p "$PRIMARY"
    git -C "$PRIMARY" init -b main
    git -C "$PRIMARY" config user.name "HermesOps Fixture"
    git -C "$PRIMARY" config user.email "fixture@hermesops.invalid"
    cat >"${PRIMARY}/README.md" <<'EOF'
# HermesOps Transaction Fixture

Repository used only by HermesOps foundation tests.
No remote is configured.
EOF
    git -C "$PRIMARY" add README.md
    git -C "$PRIMARY" commit -m "fixture: initialize transaction repository"
}

if [[ ! -d "${PRIMARY}/.git" ]]; then
    create_primary
fi

git -C "$PRIMARY" rev-parse --verify HEAD >/dev/null
[[ -z "$(git -C "$PRIMARY" status --porcelain)" ]]

if [[ ! -d "${SECONDARY}/.git" ]]; then
    rm -rf "$SECONDARY"
    git clone --no-hardlinks "$PRIMARY" "$SECONDARY"
    git -C "$SECONDARY" remote remove origin 2>/dev/null || true
fi

git -C "$SECONDARY" rev-parse --verify HEAD >/dev/null
[[ -z "$(git -C "$SECONDARY" status --porcelain)" ]]

for repo in "$PRIMARY" "$SECONDARY"; do
    while IFS= read -r remote; do
        [[ -n "$remote" ]] || continue
        git -C "$repo" remote remove "$remote"
    done < <(git -C "$repo" remote)
    [[ -z "$(git -C "$repo" status --porcelain)" ]]
done

echo "HermesOps test fixtures: PASS"

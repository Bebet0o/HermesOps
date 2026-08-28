#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
README="${REPO}/README.md"
CHANGELOG="${REPO}/CHANGELOG.md"
INSTALL_DOC="${REPO}/docs/PUBLIC_INSTALLATION.md"
INSTALLER="${REPO}/install.sh"
WORKER_LOCK="${REPO}/config/worker-sandbox.lock.toml"
WORKER_EXPORTER="${REPO}/scripts/export-worker-image.sh"
LICENSE_FILE="${REPO}/LICENSE"
VERSION_FILE="${REPO}/VERSION"

for file in "$README" "$CHANGELOG" "$INSTALL_DOC" "$INSTALLER" \
    "$WORKER_LOCK" "$WORKER_EXPORTER" "$LICENSE_FILE" "$VERSION_FILE"; do
    [[ -f "$file" ]]
done

[[ "$(cat "$VERSION_FILE")" == "0.2.0" ]]
[[ "$(wc -l <"$VERSION_FILE")" -eq 1 ]]

required_readme_text=(
    'HermesOps 0.2.0'
    'https://github.com/Bebet0o/Orchestra'
    'HermesRuntime'
    'NativeRuntime'
    'ModelProvider'
    'Hermesfiles'
    'hermesops-worker-sandbox-0.2.tar.gz'
    'hermesops-worker-sandbox-0.2.tar.gz.sha256'
    'Apache License 2.0'
)
for text in "${required_readme_text[@]}"; do
    grep -Fq "$text" "$README" || {
        echo "README text missing: $text" >&2
        exit 1
    }
done

grep -Fq '## [0.2.0] - 2026-08-27' "$CHANGELOG"
grep -Fq 'https://github.com/Bebet0o/Orchestra' "$CHANGELOG"
grep -Fq 'tag `v0.2.0`' "$INSTALL_DOC"
grep -Fq 'hermesops-worker-sandbox-0.2.tar.gz' "$INSTALL_DOC"
grep -Fq 'hermesops-worker-sandbox-0.2.tar.gz.sha256' "$INSTALL_DOC"
grep -Fq 'releases/download/v0.2.0' "$INSTALLER"
! grep -Fq 'releases/download/v0.1.0-alpha' "$INSTALLER"

python3 - \
    "$VERSION_FILE" \
    "$WORKER_LOCK" \
    "$WORKER_EXPORTER" \
    "$INSTALLER" \
    "$README" \
    "$INSTALL_DOC" <<'PY'
from pathlib import Path
import re
import sys
import tomllib

(
    version_path,
    lock_path,
    exporter_path,
    installer_path,
    readme_path,
    install_doc_path,
) = map(Path, sys.argv[1:])

release_version = version_path.read_text(encoding="utf-8").rstrip("\n")
expected_version = "0.2.0"
expected_release_tag = f"v{expected_version}"
expected_image = "hermesops-worker-sandbox:0.2"
expected_image_id = (
    "sha256:4bc8b8e521780ad786ee414643d1fc3bf6e094f4d0b8213c56599ea456bee48c"
)

if release_version != expected_version:
    raise SystemExit(
        f"release version mismatch: expected={expected_version!r} actual={release_version!r}"
    )

with lock_path.open("rb") as stream:
    lock = tomllib.load(stream)
try:
    lock_tag = lock["tag"]
    lock_image_id = lock["image_id"]
except KeyError as error:
    raise SystemExit(f"worker lock missing required field: {error.args[0]}") from error
if not isinstance(lock_tag, str) or not isinstance(lock_image_id, str):
    raise SystemExit("worker lock tag and image_id must be strings")
if lock_tag != expected_image:
    raise SystemExit(f"worker lock image mismatch: expected={expected_image!r} actual={lock_tag!r}")
if lock_image_id != expected_image_id:
    raise SystemExit(
        f"worker lock image ID mismatch: expected={expected_image_id!r} actual={lock_image_id!r}"
    )

# Mirror export-worker-image.sh's TAG//[:\/]/- transformation from the
# authoritative lock tag, then certify the resulting public asset names.
safe_tag = lock_tag.replace(":", "-").replace("/", "-")
archive_name = f"{safe_tag}.tar.gz"
checksum_name = f"{archive_name}.sha256"
expected_archive = "hermesops-worker-sandbox-0.2.tar.gz"
expected_checksum = f"{expected_archive}.sha256"
if archive_name != expected_archive:
    raise SystemExit(
        f"lock-derived archive mismatch: expected={expected_archive!r} actual={archive_name!r}"
    )
if checksum_name != expected_checksum:
    raise SystemExit(
        f"lock-derived checksum mismatch: expected={expected_checksum!r} actual={checksum_name!r}"
    )

exporter = exporter_path.read_text(encoding="utf-8")
exporter_requirements = {
    "worker lock path": '${REPO}/config/worker-sandbox.lock.toml',
    "lock tag read": 'print(data["tag"])',
    "lock image ID read": 'print(data["image_id"])',
    "tag authority": 'TAG="${LOCK_VALUES[0]}"',
    "image ID authority": 'EXPECTED_ID="${LOCK_VALUES[1]}"',
    "archive derived from tag": 'SAFE_TAG="${TAG//[:\\/]/-}"',
    "archive gzip suffix": 'ARCHIVE="${OUT_DIR}/${SAFE_TAG}.tar.gz"',
    "checksum derived from archive": 'CHECKSUM="${ARCHIVE}.sha256"',
    "locked image inspection": 'docker image inspect --format \'{{.Id}}\' "$TAG"',
    "immutable ID comparison": '[[ "$ACTUAL_ID" == "$EXPECTED_ID" ]]',
    "locked image export": 'docker image save "$TAG" | gzip -9 >"$ARCHIVE"',
    "checksum generation": 'sha256sum "$(basename "$ARCHIVE")"',
    "gzip validation": 'gzip -t "$ARCHIVE"',
}
for label, required in exporter_requirements.items():
    if required not in exporter:
        raise SystemExit(f"worker exporter contract missing {label}: {required}")

installer = installer_path.read_text(encoding="utf-8")
installer_requirements = {
    "release version lock": f'[[ "$(cat "${{REPO}}/VERSION")" == "{release_version}" ]]',
    "release tag": f'ASSET_BASE="https://github.com/Bebet0o/HermesOps/releases/download/{expected_release_tag}"',
    "worker lock path": '${REPO}/config/worker-sandbox.lock.toml',
    "lock tag read": 'print(data["tag"])',
    "lock image ID read": 'print(data["image_id"])',
    "archive destination": f'WORKER_ARCHIVE="${{DOWNLOAD_DIR}}/{archive_name}"',
    "archive download": f'"${{ASSET_BASE}}/{archive_name}" -o "$WORKER_ARCHIVE"',
    "checksum download": f'"${{ASSET_BASE}}/{checksum_name}" -o "$CHECKSUM_FILE"',
    "loaded image ID comparison": '[[ "$CURRENT_WORKER_ID" == "$WORKER_ID" ]]',
}
for label, required in installer_requirements.items():
    if required not in installer:
        raise SystemExit(f"installer contract mismatch for {label}: expected source fragment {required}")
if "releases/download/v0.1.0-alpha" in installer:
    raise SystemExit("installer retains forbidden v0.1.0-alpha release download")

for label, path in (("README", readme_path), ("public installation doc", install_doc_path)):
    text = path.read_text(encoding="utf-8")
    requirements = {
        "product version": release_version,
        "release tag": expected_release_tag,
        "worker image": lock_tag,
        "archive": archive_name,
        "checksum": checksum_name,
    }
    for field, value in requirements.items():
        if value not in text:
            raise SystemExit(f"{label} contract mismatch for {field}: missing {value!r}")

print(
    "HermesOps worker release asset contract: PASS "
    f"image={lock_tag} image_id={lock_image_id} "
    f"archive={archive_name} checksum={checksum_name} tag={expected_release_tag}"
)
PY

grep -Fq 'Apache License' "$LICENSE_FILE"
grep -Fq 'Version 2.0, January 2004' "$LICENSE_FILE"
grep -Fq 'END OF TERMS AND CONDITIONS' "$LICENSE_FILE"

python3 - "$README" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
if len(text.splitlines()) < 300:
    raise SystemExit("README is unexpectedly short")

required = (
    "# HermesOps",
    "## Overview",
    "## What HermesOps can do",
    "## Architecture",
    "## Console and CLI",
    "## Hermesfile",
    "## Runtime architecture",
    "## Security and isolation",
    "## Installation",
    "## Known limitations",
    "## HermesOps → Orchestra",
    "## License",
)
for heading in required:
    if heading not in text:
        raise SystemExit(f"Missing README heading: {heading}")

if text.index("final complete generation") > text.index("## Overview"):
    raise SystemExit("Final release positioning must precede the overview")
if "`HermesRuntime` remains the default control-plane path" not in text:
    raise SystemExit("README must identify the default runtime path")
if "does **not** build, pull, validate, activate, or roll back" not in text:
    raise SystemExit("README must preserve Hermesfile implementation limits")

print("HermesOps 0.2.0 release documentation structure: PASS")
PY

echo "HermesOps Apache-2.0 license: PASS"
echo "HermesOps 0.2.0 release documentation: PASS"

#!/usr/bin/env bash
# Full history plus public working files; never print credential values or
# scan the developer's ignored .env/data directories. CI needs no secrets.
set -euo pipefail

repo=$(git rev-parse --show-toplevel)
scan_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/badger-secrets.XXXXXX")
trap 'rm -rf -- "$scan_dir"' EXIT

# Update the version and digest together from the official release assets.
version=8.30.1
digest=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
curl --fail --silent --show-error --location --retry 3 \
  "https://github.com/gitleaks/gitleaks/releases/download/v${version}/gitleaks_${version}_linux_x64.tar.gz" \
  --output "$scan_dir/gitleaks.tar.gz"
printf '%s  %s\n' "$digest" "$scan_dir/gitleaks.tar.gz" | sha256sum --check --status
tar -xzf "$scan_dir/gitleaks.tar.gz" -C "$scan_dir" gitleaks

"$scan_dir/gitleaks" git "$repo" --log-opts=--all --redact=100 \
  --ignore-gitleaks-allow --no-banner

# Include tracked and unignored new files so local changes and merge results
# receive the same checks, while ignored local credentials stay excluded.
mkdir "$scan_dir/tracked"
cd "$repo"
git ls-files -z --cached --others --exclude-standard \
  | tar --null --verbatim-files-from --no-recursion -T - -cf - \
  | tar -xf - -C "$scan_dir/tracked"
"$scan_dir/gitleaks" dir "$scan_dir/tracked" --redact=100 \
  --ignore-gitleaks-allow --no-banner

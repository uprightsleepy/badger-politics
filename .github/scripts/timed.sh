#!/usr/bin/env bash
# Usage: timed.sh stage command [args...]. Preserve failures and retain timings
# and logs even when a gate fails. Each parallel stage owns its output files.
set -uo pipefail
stage=${1:?stage required}
shift
[[ "$stage" =~ ^[a-z0-9-]+$ ]] || { echo 'invalid timing stage' >&2; exit 2; }
[[ $# -gt 0 ]] || { echo 'command required' >&2; exit 2; }
out="${RUNNER_TEMP:-/tmp}/badger-ci"
mkdir -p "$out"
/usr/bin/time -f 'elapsed_seconds=%e\npeak_rss_kib=%M' -o "$out/$stage.time" \
  "$@" 2>&1 | tee "$out/$stage.log"
status=$?
printf 'exit_status=%s\n' "$status" >> "$out/$stage.time"
printf '\n%s: ' "$stage"
tr '\n' ' ' < "$out/$stage.time"
printf '\n'
exit "$status"

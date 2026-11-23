#!/usr/bin/env bash
# Writes the parity table to the job summary: the image tag each environment's service runs.
# After a full promotion all four should run <expected_tag>; a difference is a warning
# (for example development running a branch someone deployed by hand).
#
#   scripts/ci/parity_table.sh <expected_tag>
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

EXPECTED="$1"
mismatch=0
summary ""
summary "### Environment parity"
summary ""
summary "| Environment | Image tag | Same as production |"
summary "|---|---|---|"
for env in "${ENVIRONMENTS[@]}"; do
  tag=$(service_tag "$(env_cluster "$env")" "milk-$env")
  if [ "$tag" = "$EXPECTED" ]; then same=yes; else
    same=no
    mismatch=1
  fi
  log "parity: $env runs $tag"
  summary "| $env | \`$tag\` | $same |"
done
summary ""
if [ "$mismatch" -eq 1 ]; then
  warn "not every environment runs $EXPECTED (see the parity table)"
else
  log "all four environments run $EXPECTED"
fi

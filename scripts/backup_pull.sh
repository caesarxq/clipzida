#!/usr/bin/env bash
# Mac-side nightly backup pull from the VPS (Mac initiates outbound SSH — works behind NAT).
# Install as a launchd job (see deploy/README.md) or run manually.
set -euo pipefail
VPS_HOST="${CLIPZIDA_VPS_HOST:?set CLIPZIDA_VPS_HOST=user@ip}"
KEY="$HOME/.ssh/clipzida_vps_ed25519"
DEST="$HOME/clipping_tools_backup"
mkdir -p "$DEST"
rsync -az --delete \
  -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  "$VPS_HOST:~/clipping_tools/data/" "$DEST/data/"
rsync -az \
  -e "ssh -i $KEY" \
  "$VPS_HOST:~/clipping_tools/config/" "$DEST/config/"
echo "backup pulled $(date -u +%FT%TZ) -> $DEST"
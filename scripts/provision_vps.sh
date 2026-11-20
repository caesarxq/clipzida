#!/usr/bin/env bash
# Provision a fresh Contabo Ubuntu 24.04 VPS for the clipzida pipeline.
# Run as root:  bash provision_vps.sh
set -euo pipefail

echo "== base packages =="
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ffmpeg git rsync curl ca-certificates build-essential ufw fail2ban

echo "== service user =="
id -u clipzida >/dev/null 2>&1 || useradd -m -s /bin/bash clipzida
install -d -o clipzida -g clipzida /home/clipzida/clipping_tools /home/clipzida/data

echo "== uv + python 3.11 (as clipzida) =="
su - clipzida -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
su - clipzida -c '$HOME/.local/bin/uv python install 3.11'

echo "== firewall: ssh only (bot/queue need no inbound ports) =="
ufw allow OpenSSH
ufw --force enable

echo "== project sync =="
# From the Mac (outbound SSH works behind NAT):
#   rsync -az --exclude data --exclude .venv --exclude bin \
#     -e "ssh -i ~/.ssh/clipzida_vps_ed25519" \
#     ~/clipping_tools/ clipzida@<VPS_IP>:~/clipping_tools/
# Then on the VPS:
#   su - clipzida -c 'cd ~/clipping_tools && ~/.local/bin/uv sync && ~/.local/bin/uv run clipping-tools doctor'

echo "== verify =="
ffmpeg -version | head -1
ffmpeg -hide_banner -filters 2>/dev/null | grep -cE "subtitles|drawtext" || true
su - clipzida -c '$HOME/.local/bin/uv --version'
echo "PROVISION BASE OK — sync project, add .env credentials, then install systemd units per component."
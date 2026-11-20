# Deployment runbook — Clipzida pipeline on Contabo

## Server
- Contabo Cloud VPS 10: 4 vCPU / 8GB / 100GB SSD, Ubuntu 24.04 LTS, region Germany/EU, monthly billing.
- SSH key: `~/.ssh/clipzida_vps_ed25519` (Mac). Public key added at order time or via customer panel.
- Inbound: SSH only (ufw). Discord bot uses outbound WebSocket; no public ports needed.

## First boot
```bash
ssh -i ~/.ssh/clipzida_vps_ed25519 root@<VPS_IP>
# upload + run provisioning
scp -i ~/.ssh/clipzida_vps_ed25519 scripts/provision_vps.sh root@<VPS_IP>:/root/
ssh -i ~/.ssh/clipzida_vps_ed25519 root@<VPS_IP> 'bash /root/provision_vps.sh'
```

## Project sync (from Mac)
```bash
rsync -az --exclude data --exclude .venv --exclude bin --exclude .git \
  -e "ssh -i ~/.ssh/clipzida_vps_ed25519" \
  ~/clipping_tools/ clipzida@<VPS_IP>:~/clipping_tools/
ssh -i ~/.ssh/clipzida_vps_ed25519 clipzida@<VPS_IP> \
  'cd ~/clipping_tools && ~/.local/bin/uv sync && ~/.local/bin/uv run clipping-tools doctor'
```

## Credentials
- `.env` on the VPS (gitignored): Twitch, Google, Meta, TikTok, X tokens + OpenRouter key.
- Populate via `ssh ... 'cat > ~/clipping_tools/.env'` from the vault — never through chat.

## Workers (systemd, installed as components land)
- `clipzida-ingest.timer` — every 10 min: `clipping-tools ingest --hours 24 --no-dry-run`
- `clipzida-render.service` — queue worker (single concurrency)
- `clipzida-publish.service` — rate-limited post queue
- `clipzida-bot.service` — Discord review bot
- Keepalive cron (Oracle-free box only): light CPU tick to avoid idle reclamation.

## Backups (Mac pulls nightly)
- `scripts/backup_pull.sh` with `CLIPZIDA_VPS_HOST=clipzida@<VPS_IP>`; launchd daily 03:30 EAT.
- Contabo is oversold/unmanaged: the Mac copy is the source of truth for state recovery.

## Resize path
- If CPU steal hurts render throughput: Contabo next tier (€9/mo) or move renders to Mac offload.
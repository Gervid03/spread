#!/usr/bin/env bash
# From the laptop: sets up a fresh machine for the lab in one go.
#     scripts/vm-push.sh <user@host> <final|swarm> [ssh key, default ~/.ssh/verda_spread]
# Copies the repo's deploy key, the .env (without GEMINI_API_KEY on the final runner) and vm-setup.sh,
# runs vm-setup.sh as root, then deletes the copies from the login user's home.
set -euo pipefail
target=${1:?user@host}; role=${2:?final or swarm}; key=${3:-$HOME/.ssh/verda_spread}
root=$(git rev-parse --show-toplevel)
opts=(-i "$key" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20)
envfile=$(mktemp)
trap 'rm -f "$envfile"' EXIT
if [ "$role" = final ]; then grep -v '^GEMINI_API_KEY=' "$root/.env" > "$envfile"; else cp "$root/.env" "$envfile"; fi
# One SSH connection for everything (providers rate-limit new connections, and minimal images ship
# without an SFTP server): the files travel base64-encoded inside the script that installs them.
b64() { base64 -w0 < "$1" 2>/dev/null || base64 < "$1" | tr -d '\n'; }
{
  echo 'set -e'
  echo 'if [ "$(id -u)" = 0 ]; then S=""; else S=sudo; fi'
  echo "echo $(b64 "$HOME/.ssh/spread_deploy") | base64 -d | \$S tee /root/spread_deploy >/dev/null"
  echo "echo $(b64 "$envfile") | base64 -d | \$S tee /root/spread.env >/dev/null"
  echo "echo $(b64 "$root/scripts/vm-setup.sh") | base64 -d | \$S tee /root/vm-setup.sh >/dev/null"
  echo '$S chmod 600 /root/spread_deploy /root/spread.env'
  echo "\$S bash /root/vm-setup.sh $role"
  echo '$S rm -f /root/spread_deploy /root/spread.env'
} | ssh "${opts[@]}" "$target" 'bash -s'

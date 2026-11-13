#!/usr/bin/env bash
# Sets up a fresh Ubuntu 24.04 machine for the lab. Run it as root on the machine:
#     bash vm-setup.sh final    # the dedicated final runner (a systemd service, nothing else)
#     bash vm-setup.sh swarm    # the swarm host: Gemini CLI agents and their evaluations
# Copy two files to /root first (scripts/vm-push.sh does all of it from the laptop):
#     /root/spread_deploy   the repo's deploy key (write access to Gervid03/spread only)
#     /root/spread.env      the .env: SPREAD_KEY, and GEMINI_API_KEY on the swarm host
set -euo pipefail
role=${1:?usage: vm-setup.sh final|swarm}
export DEBIAN_FRONTEND=noninteractive

apt-get update -q
apt-get install -y -q git tmux curl ca-certificates jq ripgrep >/dev/null
id lab >/dev/null 2>&1 || useradd -m -s /bin/bash lab

# GitHub access through the deploy key, for the unprivileged user that runs everything
install -d -m 700 -o lab -g lab /home/lab/.ssh
install -m 600 -o lab -g lab /root/spread_deploy /home/lab/.ssh/spread_deploy
printf 'Host github.com\n  IdentityFile ~/.ssh/spread_deploy\n  IdentitiesOnly yes\n' > /home/lab/.ssh/config
ssh-keyscan -t ed25519 github.com > /home/lab/.ssh/known_hosts 2>/dev/null
chown lab:lab /home/lab/.ssh/config /home/lab/.ssh/known_hosts
chmod 600 /home/lab/.ssh/config
install -m 600 -o lab -g lab /root/spread.env /home/lab/spread.env

if [ "$role" = swarm ]; then
  if ! command -v node >/dev/null || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
    apt-get install -y -q nodejs >/dev/null
  fi
  npm install -g --silent @google/gemini-cli
fi

dir=spread
[ "$role" = final ] && dir=spread-final
runuser -u lab -- bash -s "$role" "$dir" <<'LAB'
set -euo pipefail
role=$1; dir=$2
cd ~
[ -x ~/.local/bin/uv ] || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
export PATH=~/.local/bin:$PATH
git config --global user.name "Swarm Dispatch lab ($role)"
git config --global user.email "swarm-dispatch-agents@users.noreply.github.com"
[ -d "$dir" ] || git clone -q git@github.com:Gervid03/spread.git "$dir"
cp ~/spread.env "$dir/.env"
if [ "$role" = swarm ]; then
  grep -q '^SPREAD_SLOTS=' "$dir/.env" || echo 'SPREAD_SLOTS=7' >> "$dir/.env"
fi
cd "$dir"
uv sync -q
mkdir -p runs
LAB

if [ "$role" = final ]; then
  cat > /etc/systemd/system/spread-final.service <<'UNIT'
[Unit]
Description=Spread final runner: plays every test final and the final with the champion on main
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
User=lab
WorkingDirectory=/home/lab/spread-final
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/home/lab/.local/bin:/usr/local/bin:/usr/bin:/bin
# Before each start, take the latest champion from main, unless the lead froze it with ~/spread-final/.freeze
ExecStartPre=-/bin/bash -c 'test -e /home/lab/spread-final/.freeze || git -C /home/lab/spread-final pull -q --ff-only'
ExecStart=/home/lab/.local/bin/uv run lab final
Restart=always
RestartSec=5
StandardOutput=append:/home/lab/spread-final/runs/final-service.log
StandardError=append:/home/lab/spread-final/runs/final-service.log

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now spread-final.service
fi
echo "vm-setup: $role ready"

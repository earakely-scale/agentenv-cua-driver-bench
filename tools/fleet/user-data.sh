#!/bin/bash
# A fleet worker's setup at first boot: Docker with a local registry, the agentenv framework in ~/venv, the bench in
# ~/bench. launch.sh or launch.py fills in the @...@ values. The VM shuts down, and so terminates, after @MAX_MINUTES@ minutes.
set -x
shutdown -h +@MAX_MINUTES@
systemctl stop unattended-upgrades || true
systemctl stop apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer || true
while fuser /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do sleep 3; done
apt-get -o DPkg::Lock::Timeout=300 update
apt-get -o DPkg::Lock::Timeout=300 install -y git curl jq psmisc unzip ffmpeg python3-venv
for attempt in 1 2 3 4 5; do
  while pgrep -x apt-get >/dev/null || pgrep -f unattended-upgrade >/dev/null || fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock >/dev/null 2>&1; do sleep 3; done
  curl -fsSL https://get.docker.com | sh && command -v docker && break
  sleep 5
done
mkdir -p /etc/docker && echo '{"default-address-pools":[{"base":"172.20.0.0/14","size":24}]}' > /etc/docker/daemon.json && systemctl restart docker
usermod -aG docker ubuntu
# A Windows run's computers boot under KVM, which agent-env uses only when the user can open /dev/kvm.
getent group kvm >/dev/null && usermod -aG kvm ubuntu
sysctl -w fs.inotify.max_user_instances=8192 fs.inotify.max_user_watches=1048576
docker run -d --restart=always -p 5000:5000 --name registry public.ecr.aws/docker/library/registry:2
sudo -iu ubuntu bash <<'INNER'
set -x
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=$HOME/.local/bin:$PATH
uv venv -q -p 3.12 ~/venv && VIRTUAL_ENV=~/venv uv pip install -q '@FRAMEWORK@' huggingface_hub pandas pyarrow
git clone -q @BENCH_REPO@ ~/bench
mkdir -p ~/fleet/logs ~/fleet/out
INNER
touch /var/tmp/setup-done

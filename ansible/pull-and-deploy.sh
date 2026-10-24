#!/usr/bin/env bash
# Fixed-source deployment; never resets local work or imports another server's data.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run as root on the application server'; exit 1; }
[[ -f /etc/dobhrap.env ]] || { echo 'Existing DOBHRAP application configuration is required'; exit 1; }
exec 9>/run/lock/dobhrap-pull-deploy.lock
flock -n 9 || { echo 'Another pull-and-deploy operation is running'; exit 1; }
repo=/opt/dobhrap-watchdog-source
export GIT_TERMINAL_PROMPT=0
if [[ -L "$repo" ]]; then echo 'Refuse a symlink source checkout'; exit 1; fi
if [[ ! -e "$repo" ]]; then
 git clone --branch main --single-branch https://github.com/olamidebello/DOBHRAP.git "$repo"
fi
[[ -d "$repo/.git" ]] || { echo 'Source directory is not a Git checkout; review it before deployment'; exit 1; }
[[ $(stat -c %u "$repo") == 0 ]] || { echo 'Source checkout must be root-owned'; exit 1; }
cd "$repo"
origin=$(git remote get-url origin)
case "$origin" in
 https://github.com/olamidebello/DOBHRAP|https://github.com/olamidebello/DOBHRAP.git) ;;
 *) echo 'Unexpected source origin; deployment stopped'; exit 1 ;;
esac
[[ $(git branch --show-current) == main ]] || { echo 'Source checkout must be on main'; exit 1; }
# Refuse tracked edits and untracked files; never discard operator work.
[[ -z $(git status --porcelain) ]] || { echo 'Source checkout has local changes; commit or move them before deployment'; exit 1; }
git fetch --prune origin main
git merge --ff-only origin/main
install -d -o root -g root -m 0700 /var/log/dobhrap-deploy
log="/var/log/dobhrap-deploy/pull-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
release=$(git rev-parse HEAD)
echo "Deploying committed release $release. Private deployment log: $log"
if ! ansible-playbook -i 'dobhrap,' -c local "$repo/ansible/communications-oob.yml" >"$log" 2>&1; then
 echo "Deployment failed. Review $log on this server. Do not delete the database, encryption key or provider credentials."
 exit 1
fi
printf 'Deployment and public HTTPS checks passed for release %s.\n' "$release"
echo "Private deployment log: $log"
echo 'Phone/PBX requires its SIP bridge and shared token. Email requires the existing approved OlamidePanel mail configuration. Unconfigured services remain disabled.'
echo 'Registration OTP and user management are installed. Configure Twilio privately under Super admin > Provider provisioning & keys, then provision/test/enable under Registration OTP & Twilio.'

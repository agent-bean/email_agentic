#!/usr/bin/env bash
set -eu
test "$(id -u)" = 0
test -n "${SSH_ADMIN_PUBLIC_KEY:-}"
if getent passwd email-admin >/dev/null; then
  echo 'Existing email-admin account preserved; inspect before running preparation again.'
  exit 1
fi
backup="/root/email-agentic-hardening-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup"
printf '%s\n' "$backup" > /root/email-agentic-hardening-backup-path
chmod 600 /root/email-agentic-hardening-backup-path
paths=(/etc/ssh /etc/apt/apt.conf.d /etc/sudoers /etc/sudoers.d /etc/systemd/journald.conf)
if test -e /etc/default/ufw; then paths+=(/etc/default/ufw); fi
tar -cpf "$backup/baseline-config.tar" "${paths[@]}" 2> "$backup/baseline-backup.log"
tar -tf "$backup/baseline-config.tar" >/dev/null
chmod 600 "$backup/baseline-config.tar"
dpkg-query -W > "$backup/packages-before.txt"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o DPkg::Lock::Timeout=180 update > "$backup/apt-update.log" 2>&1
echo 'Package lists updated.'
apt-get -o DPkg::Lock::Timeout=180 -o Dpkg::Options::=--force-confold -y upgrade > "$backup/apt-upgrade.log" 2>&1
echo 'Available package upgrades applied.'
apt-get -o DPkg::Lock::Timeout=180 -y install ufw fail2ban unattended-upgrades ca-certificates sudo > "$backup/apt-install.log" 2>&1
echo 'Security packages installed.'
adduser --disabled-password --gecos '' email-admin > "$backup/create-admin.log" 2>&1
usermod -aG sudo email-admin
chmod 750 /home/email-admin
install -d -m 700 -o email-admin -g email-admin /home/email-admin/.ssh
printf '%s\n' "$SSH_ADMIN_PUBLIC_KEY" > /home/email-admin/.ssh/authorized_keys
chown email-admin:email-admin /home/email-admin/.ssh/authorized_keys
chmod 600 /home/email-admin/.ssh/authorized_keys
printf '%s\n' 'email-admin ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/email-agentic-admin
chmod 440 /etc/sudoers.d/email-agentic-admin
visudo -cf /etc/sudoers.d/email-agentic-admin >/dev/null
echo 'email-admin created with supplied SSH public key and sudo.'
echo 'Root login and firewall have not been changed yet.'
test ! -f /var/run/reboot-required || echo 'REBOOT_REQUIRED'

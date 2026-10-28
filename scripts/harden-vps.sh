#!/usr/bin/env bash
set -eu
test "$(id -u)" = 0
backup=$(cat /root/email-agentic-hardening-backup-path)
test -f "$backup/admin-verified"
test ! -e /etc/ssh/sshd_config.d/00-email-agentic.conf
ufw status | grep -q 'Status: inactive'
cp -a /etc/ufw/user.rules /etc/ufw/user6.rules /etc/ufw/ufw.conf "$backup/"

cat > "$backup/rollback.sh" <<'ROLLBACK'
#!/bin/sh
set -eu
backup=$(dirname "$0")
systemctl disable --now fail2ban || true
ufw --force disable
cp -a "$backup/user.rules" /etc/ufw/user.rules
cp -a "$backup/user6.rules" /etc/ufw/user6.rules
cp -a "$backup/ufw.conf" /etc/ufw/ufw.conf
rm -f /etc/ssh/sshd_config.d/00-email-agentic.conf
/usr/sbin/sshd -t
systemctl reload ssh
touch "$backup/rollback-executed"
ROLLBACK
chmod 700 "$backup/rollback.sh"
systemd-run --unit=email-agentic-hardening-rollback --on-active=10m --collect /bin/sh "$backup/rollback.sh" >/dev/null

cat > /etc/ssh/sshd_config.d/00-email-agentic.conf <<'SSH'
# Administrative access uses the project key and the dedicated sudo account.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
PermitEmptyPasswords no
AllowUsers email-admin
X11Forwarding no
AllowAgentForwarding no
MaxAuthTries 3
LoginGraceTime 30
MaxStartups 10:30:60
SSH
chmod 644 /etc/ssh/sshd_config.d/00-email-agentic.conf
/usr/sbin/sshd -t
systemctl reload ssh
echo 'SSH configuration validated and reloaded; rollback timer active.'

ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment 'SSH key access' >/dev/null
ufw logging low >/dev/null
ufw --force enable >/dev/null
systemctl enable --now ufw >/dev/null
echo 'UFW enabled: inbound SSH only, outbound allowed.'

cat > /etc/fail2ban/jail.d/email-agentic.local <<'JAIL'
[sshd]
enabled = true
backend = systemd
port = 22
banaction = ufw
findtime = 10m
maxretry = 5
bantime = 1h
JAIL
fail2ban-client -t > "$backup/fail2ban-config-check.log" 2>&1
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban
echo 'Fail2ban sshd jail enabled.'

cat > /etc/apt/apt.conf.d/52-email-agentic-security <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "false";
APT
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades >/dev/null
install -d -m 755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/email-agentic.conf <<'JOURNAL'
[Journal]
Storage=persistent
SystemMaxUse=200M
MaxRetentionSec=30day
JOURNAL
systemctl restart systemd-journald
journalctl --flush
echo 'Automatic security updates and bounded persistent system logs configured.'
echo 'Verify a new admin SSH connection, then stop email-agentic-hardening-rollback.timer.'

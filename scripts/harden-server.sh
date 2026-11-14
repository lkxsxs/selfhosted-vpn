#!/usr/bin/env bash
# 服务器安全基线（Ubuntu 24.04，单协议 TUIC）
# 用法：sudo bash harden-server.sh
set -euo pipefail

echo "==> 1. 系统更新"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get -y -qq upgrade

echo "==> 2. 安装依赖"
apt-get -y -qq install ufw fail2ban unattended-upgrades python3 vnstat

echo "==> 3. SSH 改 2222（Ubuntu 24.04 socket 激活）"
mkdir -p /etc/systemd/system/ssh.socket.d
cat > /etc/systemd/system/ssh.socket.d/50-altport.conf <<'EOF'
[Socket]
ListenStream=
ListenStream=0.0.0.0:2222
ListenStream=[::]:2222
EOF
systemctl daemon-reload
systemctl restart ssh.socket
echo "  注意：请先确认 ssh -p 2222 可登录，再继续"

echo "==> 4. fail2ban"
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = 2222
findtime = 600
maxretry = 5
bantime = 86400
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> 5. UFW（只放行 3 个端口，先放行 SSH 防锁死）"
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp  comment 'SSH'
ufw allow 80/tcp    comment 'subscription'
ufw allow 8445/udp  comment 'tuic'
ufw --force enable

echo "==> 6. 自动安全更新"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades

echo "==> 完成"
ufw status verbose
systemctl is-active fail2ban unattended-upgrades vnstat

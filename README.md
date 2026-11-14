# 自建 TUIC VPN（单协议精简版）

Ubuntu 单机部署 TUIC v5 + 自建订阅服务，电脑/手机通用。**IP/密钥/token 均为占位符，部署前替换。**

## 架构

```
VPS (Ubuntu 24.04, 1C1G)
├─ TUIC v5   :8445/udp  BBR + h3           唯一代理协议
├─ vpn-sub   :80/tcp    订阅下发 + vnstat 流量统计
├─ sshd      :2222      SSH
└─ UFW / fail2ban / unattended-upgrades
```

单协议理由：实测 UDP 抗限速最好，且手机端 TUIC 明显优于 Hysteria2；少一个协议少一份维护成本。

## 实测

| 场景 | 速度 |
|---|---|
| 电脑有线，晚高峰 | 19–30 Mbps |
| 电脑有线，凌晨 | 37–44 Mbps |
| 手机 WiFi | 19–44 Mbps（Play 下载 8 MB/s） |
| 同线路 TCP 协议（对比） | 晚高峰仅 1–3 Mbps |

## 部署

### 0. 准备

```bash
apt update && apt upgrade -y
apt install -y curl wget unzip jq ufw fail2ban python3 openssl vnstat
```

### 1. 安全基线

`bash scripts/harden-server.sh`，或手动：

```bash
# SSH 改 2222（Ubuntu 24.04 用 socket 激活，改 sshd_config 无效）
mkdir -p /etc/systemd/system/ssh.socket.d
cat > /etc/systemd/system/ssh.socket.d/50-altport.conf <<'EOF'
[Socket]
ListenStream=
ListenStream=0.0.0.0:2222
ListenStream=[::]:2222
EOF
systemctl daemon-reload && systemctl restart ssh.socket
# 新窗口验证 ssh -p 2222 可登录后再继续

# fail2ban
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = 2222
findtime = 600
maxretry = 5
bantime = 86400
EOF
systemctl enable --now fail2ban

# UFW：只放行 3 个端口（先放行 SSH 再 enable）
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp   # SSH
ufw allow 80/tcp     # 订阅
ufw allow 8445/udp   # TUIC
ufw --force enable

# 自动安全更新
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades
```

### 2. TUIC v5

```bash
mkdir -p /etc/tuic /etc/xray
# 从 https://github.com/EAimTY/tuic/releases 下载 tuic-server
wget -O /usr/local/bin/tuic-server <TUIC_SERVER_BINARY_URL>
chmod +x /usr/local/bin/tuic-server

# 自签证书（客户端 skip-cert-verify: true）
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout /etc/xray/tls.key -out /etc/xray/tls.crt -days 3650 -nodes \
  -subj "/CN=www.microsoft.com"

# 配置见 configs/server/tuic-config.example.json（uuid/password 自己生成）
# systemd 见 configs/server/systemd/tuic-server.service
systemctl daemon-reload && systemctl enable --now tuic-server
```

密钥生成：`bash scripts/generate-secrets.sh`（或 `cat /proc/sys/kernel/random/uuid` + `openssl rand -hex 10`）。

### 3. 订阅服务 vpn-sub

```
/root/vpn-sub/
├── serve.py        # 订阅服务
├── config.yaml     # 下发的 Clash 配置
├── sub.env         # token/端口/总量/到期/统计
└── access.log
```

```bash
cp vpn-sub/serve.py /root/vpn-sub/
cp configs/server/vpn-sub.env.example /root/vpn-sub/sub.env   # 改成真实值
cp configs/server/systemd/vpn-sub.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now vpn-sub
```

流量统计：TUIC 无 stats API，用 **vnstat** 统计网卡月流量（`VNSTAT_IF=eth0`），订阅头返回 upload/download/total/expire。

### 4. 客户端配置

模板见 [configs/client/clash-subscription.example.yaml](configs/client/clash-subscription.example.yaml)，只有两个关键点：

```yaml
dns:
  enable: true
  enhanced-mode: fake-ip
  nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]
  fallback: [https://doh.dns.apple.com/dns-query, tls://8.8.8.8:853, https://dns.google/dns-query]
  fallback-filter: { geoip: true, geoip-code: CN, domain: ['+.google.com', '+.youtube.com', '+.openai.com', ...] }

rules:
  - DOMAIN-SUFFIX,xn--ngstr-lra8j.com,节点选择   # Play 下载 CDN，必须显式代理
  - DOMAIN-SUFFIX,gvt1.com,节点选择
  - DOMAIN-SUFFIX,gvt2.com,节点选择
  - GEOSITE,cn,DIRECT
  - GEOIP,CN,DIRECT
  - MATCH,节点选择
```

- 电脑：Clash Verge，订阅自动更新
- 手机：Clash Meta for Android，手动更新订阅
- 节点名建议 ≤ 11 字符（手机卡片会截断）

## 坑

| 现象 | 根因 | 解决 |
|---|---|---|
| 晚高峰只有 1–3 Mbps | GFW 对 TCP 代理限速 | 用 UDP 协议（TUIC） |
| Play 下载先快后卡死 | 本地 DNS 把下载 CDN 解析到国内 IP → GEOIP 直连超时 | fake-ip DNS + `xn--ngstr-lra8j.com` 显式代理 |
| Hysteria2 间歇断流 | 晚高峰 UDP 被干扰 | 端口跳跃 iptables（本项目改用 TUIC 规避） |
| Play 报 `DownloadService CANNOT_CONNECT` | Play 自更新失败，与代理无关 | 清 Play 数据/重装/重置 GMS |
| 规则加了反而更慢 | 关键规则写在 `GEOIP,CN` 之后 | 关键域名规则放最前 |
| 改 SSH 端口不生效 | Ubuntu 24.04 socket 激活 | 改 `ssh.socket.d` override |

详细排查见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 安全 / 备份

- SSH 非标端口 + 强密码 + fail2ban；有条件改密钥登录
- 订阅走 HTTP，token 明文传输有嗅探风险（有域名可上 HTTPS）
- 真实密钥不提交 Git；`.gitignore` 已排除证书/配置
- 备份：`/etc/tuic/config.json`、`/etc/xray/tls.{crt,key}`、`/root/vpn-sub/*`、systemd/fail2ban/ssh 配置

## 目录

```
├── README.md
├── configs/
│   ├── server/     tuic-config、vpn-sub.env、systemd、ssh、fail2ban
│   └── client/     clash 订阅模板
├── vpn-sub/serve.py
├── scripts/        generate-secrets.sh / harden-server.sh
└── docs/troubleshooting.md
```

## 参考

- [TUIC](https://github.com/EAimTY/tuic) · [mihomo](https://github.com/MetaCubeX/mihomo) · [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev)
- [hwdsl2/setup-ipsec-vpn](https://github.com/hwdsl2/setup-ipsec-vpn)（起点）

## 免责声明

仅供学习网络协议与服务器运维。请遵守当地法律法规，作者不对使用后果负责。

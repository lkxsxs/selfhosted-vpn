#!/usr/bin/env bash
# 生成随机密钥（Linux/macOS）
set -euo pipefail
uuid() { cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen; }

echo "================ 生成结果（仅本地保存，勿提交 Git） ================"
echo "订阅 TOKEN   : $(openssl rand -hex 16)"
echo "TUIC UUID    : $(uuid)"
echo "TUIC 密码    : Tuic$(openssl rand -hex 10)"
echo "=================================================================="
echo "证书（自签）："
echo "  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \\"
echo "    -keyout key.pem -out cert.pem -days 3650 -nodes -subj '/CN=www.microsoft.com'"

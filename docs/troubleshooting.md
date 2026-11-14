# 踩坑记录

## 1. TCP 协议晚高峰被限速

同一家宽、同一 VPS、100MB 持续下载：

| 协议 | 凌晨 | 晚高峰 |
|---|---|---|
| SS2022 / REALITY | 3–6 Mbps | 0.6–3 Mbps |
| VLESS+TLS | 36–44 Mbps | 3–8 Mbps |
| Hysteria2 | 34–64 Mbps | 25–45 Mbps |
| TUIC | 37–44 Mbps | 19–30 Mbps |

结论：TCP 限速是系统性的，UDP 作主力。

## 2. 手机端 Hysteria2 异常

同节点同网络：电脑 Hysteria2 34 Mbps，手机只有 1.9 Mbps；换 TUIC 后手机 19–44 Mbps。部分 Android 客户端 Hysteria2 实现差，手机用 TUIC。

## 3. DNS 泄漏导致 Play 下载卡死

服务端日志：

```
dial tcp4 58.63.233.67:443: i/o timeout
```

手机 logcat：

```
[TCP] com.android.vending --> rr2---sn-j5o76n7l.xn--ngstr-lra8j.com:443
  match GeoIP(cn) using DIRECT
  error: dial tcp 58.63.233.69:443: i/o timeout
```

- `58.63.x.x` 是国内 CDN 的 IP：Play 下载 CDN 域名被本地 DNS 解析到国内
- Clash 只看到目标 IP → 命中 `GEOIP,CN,DIRECT` → 直连超时

修复：

```yaml
dns:
  enhanced-mode: fake-ip
  nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]
  fallback: [https://doh.dns.apple.com/dns-query, tls://8.8.8.8:853, https://dns.google/dns-query]
  fallback-filter: { geoip: true, geoip-code: CN, domain: ['+.google.com', ...] }
rules:
  - DOMAIN-SUFFIX,xn--ngstr-lra8j.com,节点选择
  - DOMAIN-SUFFIX,gvt1.com,节点选择
  - DOMAIN-SUFFIX,gvt2.com,节点选择
```

Play 下载恢复 8 MB/s。该规则来自商业机场配置（其规则集同样显式代理了该 CDN 域名）。

## 4. Play 商店 `CANNOT_CONNECT`（与代理无关）

```
E/Finsky: Download Service Error: CANNOT_CONNECT (8)
```

- 换节点、换协议无效
- **完全关闭 VPN 后同样报错**（"无法完成更新"）
- 结论：Play 商店自更新失败，与代理无关
- 处理：清 Play 数据 → 卸载重装 Play → 仍失败则重置 GMS 数据（需重新登录）

## 5. 规则顺序错误导致变慢

`GEOIP,CN,DIRECT` 写在关键域名规则之前时，域名规则被绕过（先按解析出的国内 IP 判定直连）。
正确顺序：关键域名 → 私有 IP → 国内域名 → `GEOSITE,cn`/`GEOIP,CN` → `MATCH`。

## 6. Ubuntu 24.04 改 SSH 端口

只改 `sshd_config` 的 `Port` 不生效（socket 激活）。用 override：

```
/etc/systemd/system/ssh.socket.d/50-altport.conf
[Socket]
ListenStream=
ListenStream=0.0.0.0:2222
ListenStream=[::]:2222
```

## 7. 订阅流量统计

- TUIC 没有流量统计 API → 用 vnstat 统计网卡月流量（`VNSTAT_IF=eth0`）
- vnstat 的 `rx`=下载、`tx`=上传
- 若用 Hysteria2，则读其 `trafficStats`：`tx`=上传、`rx`=下载

## 8. 其它

- 手机节点名过长被卡片截断：≤ 11 字符
- 自签证书需客户端 `skip-cert-verify: true`
- 凌晨测速明显高于晚高峰，评估必须固定时段

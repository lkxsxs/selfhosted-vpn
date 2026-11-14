#!/usr/bin/env python3
"""vpn-sub：轻量级 Clash 订阅服务

功能：
1. 校验 /sub/<TOKEN>/config.yaml，返回 Clash 配置
2. 响应头 Subscription-Userinfo 显示流量/总量/到期
   - 优先用 vnstat 统计网卡月流量（单协议部署时最直接）
   - 回退：Xray stats API + Hysteria2 trafficStats
3. 记录访问日志（UA / 是否成功）

环境变量见 configs/server/vpn-sub.env.example
"""

import http.server
import json
import os
import socketserver
import subprocess
import threading
import time
import urllib.request

TOKEN = os.environ.get("SUB_TOKEN", "")
FILE = os.environ.get("SUB_FILE", "/root/vpn-sub/config.yaml")
PORTS = [
    int(x)
    for x in os.environ.get("SUB_PORTS", os.environ.get("SUB_PORT", "80")).split(",")
    if x.strip()
]
TOTAL = int(os.environ.get("SUB_TOTAL_BYTES", str(3 * 1024**4)))
EXPIRE = int(os.environ.get("SUB_EXPIRE_TS", "0"))
WEB_PAGE = os.environ.get("PROFILE_WEB_PAGE_URL", "")
HY2_URL = os.environ.get("HY2_STATS_URL", "")
HY2_SECRET = os.environ.get("HY2_STATS_SECRET", "")
VNSTAT_IF = os.environ.get("VNSTAT_IF", "")
LOG = os.environ.get("SUB_LOG", "/root/vpn-sub/access.log")


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def vnstat_traffic():
    """vnstat 当前月网卡流量：rx=下载, tx=上传"""
    if not VNSTAT_IF:
        return 0, 0
    try:
        out = subprocess.check_output(
            ["vnstat", "-i", VNSTAT_IF, "--json", "m"], timeout=5
        )
        d = json.loads(out)
        months = d["interfaces"][0]["traffic"]["month"]
        if months:
            m = months[-1]
            return int(m.get("tx", 0) or 0), int(m.get("rx", 0) or 0)
    except Exception:
        pass
    return 0, 0


def xray_traffic():
    up = down = 0
    try:
        out = subprocess.check_output(
            ["/usr/local/bin/xray", "api", "statsquery", "--server=127.0.0.1:10085"],
            timeout=5,
        )
        d = json.loads(out)
        for st in d.get("stat", []):
            name = st.get("name", "")
            try:
                val = int(st.get("value", 0) or 0)
            except Exception:
                val = 0
            if ">>>api>>>" in name:
                continue
            if "inbound>>>" in name and "traffic>>>uplink" in name:
                up += val
            elif "inbound>>>" in name and "traffic>>>downlink" in name:
                down += val
    except Exception:
        pass
    return up, down


def hy2_traffic():
    """Hysteria2 trafficStats：tx=上传, rx=下载"""
    up = down = 0
    if not HY2_URL:
        return up, down
    try:
        req = urllib.request.Request(HY2_URL, headers={"Authorization": HY2_SECRET})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode() or "{}")
        for _user, v in (d or {}).items():
            try:
                up += int(v.get("tx", 0) or 0)
                down += int(v.get("rx", 0) or 0)
            except Exception:
                pass
    except Exception:
        pass
    return up, down


def userinfo():
    up, down = vnstat_traffic()
    if not up and not down:
        x_up, x_down = xray_traffic()
        h_up, h_down = hy2_traffic()
        up, down = x_up + h_up, x_down + h_down
    return "upload=%d; download=%d; total=%d; expire=%d" % (up, down, TOTAL, EXPIRE)


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body=True):
        ok = TOKEN and self.path == "/sub/" + TOKEN + "/config.yaml"
        log("%s %s ua=%r ok=%s" % (self.command, self.path, self.headers.get("User-Agent", ""), ok))
        if not ok:
            self.send_error(404)
            return
        try:
            raw = open(FILE, "rb").read()
            data = ("# sub-update: %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S")).encode() + raw
        except Exception:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", 'attachment;filename="config.yaml"')
        self.send_header("Subscription-Userinfo", userinfo())
        self.send_header("Profile-Update-Interval", "24")
        if WEB_PAGE:
            self.send_header("Profile-Web-Page-Url", WEB_PAGE)
        self.end_headers()
        if body:
            self.wfile.write(data)

    def do_GET(self):
        self._send(True)

    def do_HEAD(self):
        self._send(False)

    def log_message(self, fmt, *args):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    for p in PORTS:
        srv = Server(("0.0.0.0", p), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("started on ports %r" % (PORTS,))
    while True:
        time.sleep(3600)

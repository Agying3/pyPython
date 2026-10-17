# -*- coding: utf-8 -*-
"""把参考站的**真实渲染值**读出来 —— 不是读源码猜。

为什么不能只抓 HTML/CSS：
  参考站是 PHP + WordPress + 一堆自定义 CSS，最终生效的值还叠了主题的
  CSS 变量、浏览器默认字型回退、`backdrop-filter` 的合成结果。
  源码里写着 `font-family: var(--font-sans)` 这种，光看文件不知道落到哪一款字。
  本项目栽过 #41（把注释里的示例色当成配置）和 #42（按文件名认定图片内容），
  所以这里只信 `getComputedStyle()`。

做法：开一个带 --remote-debugging-port 的无头 Edge，用 CDP 执行一段
      采集脚本，每类元素取"实际渲染出来的"字号/字重/行高/字色/背景/透明度/字体栈。
      顺便把计算样式里出现的所有自定义属性（--*）和 styleSheet 规则里的
      var() 定义一起捞回来，方便对账。

用法：
    python tools/probe_ref.py                     # 默认参考站
    python tools/probe_ref.py <url> <out.json>
    python tools/probe_ref.py <url> <out.json> --node   # 需要 node/npx 的 playwright

前置：已有一个 Edge/Chrome 在 9222 端口跑着（tools/probe_ref.py 会自己拉）。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_URL = "https://xing.xo.je/"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 一段尽量"只读"的采集脚本：不发送任何数据出去，只把计算结果塞进
# window.__REF_PROBE__，再由 CDP 取回。
COLLECT = r"""
(() => {
  const want = ['fontFamily','fontSize','fontWeight','fontStyle','lineHeight',
                'letterSpacing','color','opacity','backgroundColor',
                'backgroundImage','textShadow','textAlign','filter','backdropFilter',
                'borderRadius','fontVariant', 'textRendering'];
  const pick = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    const out = {};
    for (const k of want) out[k] = cs[k];
    const r = el.getBoundingClientRect();
    out._rect = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
    out._tag = el.tagName.toLowerCase();
    out._cls = el.className && el.className.toString().slice(0, 120);
    out._text = (el.textContent || '').trim().slice(0, 40);
    return out;
  };
  const q = (s) => pick(document.querySelector(s));
  const qa = (s) => Array.from(document.querySelectorAll(s)).slice(0, 6).map(pick);

  // 全站自定义属性
  const vars = {};
  const rootCS = getComputedStyle(document.documentElement);
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    if (!rules) continue;
    for (const r of Array.from(rules)) {
      if (r.style && r.selectorText && /:root|html/.test(r.selectorText)) {
        for (const p of Array.from(r.style)) {
          if (p.startsWith('--')) vars[p] = r.style.getPropertyValue(p).trim();
        }
      }
    }
  }

  // 字体栈实测：让浏览器自己告诉我们落到哪一款
  const probeFont = (fam, text) => {
    if (!fam) fam = 'sans-serif';
    const el = document.createElement('span');
    el.style.cssText = 'position:fixed;left:-9999px;top:0;font-size:100px;font-family:' + fam;
    el.textContent = text || 'mmmmmmmmmmlli中文字体测试';
    document.body.appendChild(el);
    const w = el.getBoundingClientRect().width;
    el.remove();
    return Math.round(w * 100) / 100;
  };

  return {
    url: location.href,
    title: document.title,
    dpr: window.devicePixelRatio,
    viewport: [window.innerWidth, window.innerHeight],
    body: pick(document.body),
    bodyVars: Object.fromEntries(['--themecolor','--themecolor-rgbstr'].map(k => [k, rootCS.getPropertyValue(k).trim()])),
    nav: q('header, nav, .navbar, #navbar'),
    navLinks: qa('header a, nav a'),
    brand: q('.navbar-brand, .brand, header .logo'),
    hero: q('.hero, .banner, .cover, .page-header, header + section, #hero'),
    heroTitle: q('.hero h1, h1, .banner h1'),
    heroSub: q('.hero p, .banner p, h1 + p, .subtitle'),
    sectionTitle: q('h2, .section-title, .card-title'),
    card: q('.card, .post-card, article, .post'),
    cardTitle: q('.card h2, .post-title, article h3, .card .title'),
    cardText: q('.card p, article p, .excerpt, .summary'),
    meta: q('.meta, .post-meta, time, .date, .info'),
    link: q('a'),
    sidebarWidget: q('.sidebar, .widget, aside'),
    widgetHead: q('.widget-head, .widget-title, .card-header, .box-title'),
    widgetBody: q('.widget-body, .box-body, .card-body'),
    footer: q('footer'),
    code: q('pre, code'),
    allCssVars: vars,
    fontMeasure: {
      bodyStack: probeFont(getComputedStyle(document.body).fontFamily),
      bodyFontSize: getComputedStyle(document.body).fontSize,
      serif: probeFont('serif'),
      sans: probeFont('sans-serif'),
      mono: probeFont('monospace'),
      quoteCN: probeFont('"Songti SC", "Noto Serif SC", serif'),
      raleway: probeFont('Raleway, sans-serif'),
      nunito: probeFont('Nunito, sans-serif'),
      poppins: probeFont('Poppins, sans-serif'),
    },
    // 页面上引到的外链样式 / 字体
    links: Array.from(document.querySelectorAll('link[href]')).map(l => l.rel + ' ' + l.href).slice(0, 60),
  };
})()
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def cdp(port, method, params=None, sid=None):
    """极简 CDP 客户端：一次连接一次调用。"""
    import socket

    ws_url = json.loads(
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port).read()
    )["webSocketDebuggerUrl"]
    # ws://127.0.0.1:port/devtools/browser/<id>
    host_port = ws_url.split("//")[1].split("/")[0]
    host, p = host_port.split(":")
    path = "/" + ws_url.split("//")[1].split("/", 1)[1]

    sock = socket.create_connection((host, int(p)), timeout=60)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    sock.sendall((
        "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host_port, key)
    ).encode())
    sock.recv(4096)

    def send(obj):
        payload = json.dumps(obj).encode()
        hdr = bytearray([0x81])
        n = len(payload)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += n.to_bytes(2, "big")
        else:
            hdr.append(0x80 | 127)
            hdr += n.to_bytes(8, "big")
        mask = os.urandom(4)
        hdr += mask
        sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv():
        buf = b""
        while True:
            while len(buf) < 2:
                buf += sock.recv(65536)
            b0, b1 = buf[0], buf[1]
            ln = b1 & 0x7F
            off = 2
            if ln == 126:
                while len(buf) < 4:
                    buf += sock.recv(65536)
                ln = int.from_bytes(buf[2:4], "big")
                off = 4
            elif ln == 127:
                while len(buf) < 10:
                    buf += sock.recv(65536)
                ln = int.from_bytes(buf[2:10], "big")
                off = 10
            while len(buf) < off + ln:
                buf += sock.recv(65536)
            data = buf[off:off + ln]
            rest = buf[off + ln:]
            if b0 & 0x0F == 0x1:
                return json.loads(data.decode("utf-8", "replace")), rest
            buf = rest

    send({"id": 1, "method": method, "params": params or {}})
    while True:
        msg, _ = recv()
        if msg.get("id") == 1:
            sock.close()
            return msg


def run(url, port=9222):
    edge = find_edge()
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        if not edge:
            return None, "没找到 Edge"
        proc = subprocess.Popen([
            edge, "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    try:
        t = cdp(port, "Target.createTarget", {"url": url})
        tid = t["result"]["targetId"]
        time.sleep(6)
        tgt = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/json/list" % port).read())
        sessions = cdp(port, "Target.getTargets")["result"]["targetInfos"]

        # 用 /json/list 里的 page 直接跑 Evaluation 需要 attach；
        # 简化：改用 page 级 WebSocket
        ws_page = None
        for x in tgt:
            if x.get("id") == tid:
                ws_page = x["webSocketDebuggerUrl"]
        if not ws_page:
            return None, "拿不到页面 ws 地址"

        globals()["_ws_page"] = ws_page
        res = eval_on_page(ws_page, COLLECT)
        return res, None
    finally:
        if proc:
            proc.terminate()


def eval_on_page(ws_url, expr):
    import socket

    host_port = ws_url.split("//")[1].split("/")[0]
    host, p = host_port.split(":")
    path = "/" + ws_url.split("//")[1].split("/", 1)[1]
    sock = socket.create_connection((host, int(p)), timeout=90)
    sock.sendall((
        "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host_port)).encode())
    sock.recv(4096)

    def send(o):
        pl = json.dumps(o).encode()
        h = bytearray([0x81])
        n = len(pl)
        if n < 126:
            h.append(0x80 | n)
        elif n < 65536:
            h.append(0x80 | 126)
            h += n.to_bytes(2, "big")
        else:
            h.append(0x80 | 127)
            h += n.to_bytes(8, "big")
        m = os.urandom(4)
        h += m
        sock.sendall(bytes(h) + bytes(b ^ m[i % 4] for i, b in enumerate(pl)))

    send({"id": 1, "method": "Runtime.evaluate",
          "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}})
    buf = b""
    deadline = time.time() + 90
    while time.time() < deadline:
        buf += sock.recv(1 << 20)
        # 粗暴但够用：找 JSON 边界
        s = buf.find(b"{")
        if s < 0:
            continue
        try:
            obj, idx = json.JSONDecoder().raw_decode(buf[s:].decode("utf-8", "replace"))
        except Exception:
            continue
        if obj.get("id") == 1:
            sock.close()
            r = obj.get("result", {})
            if "exceptionDetails" in r:
                return {"_error": r["exceptionDetails"]}
            return r.get("result", {}).get("value")
    sock.close()
    return {"_error": "timeout"}


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else REF_URL
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "_ref", "ref.json")
    data, err = run(url)
    if data is None:
        print("[跳过] %s" % err)
        return 0
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写入 %s" % out)
    for k in ("body", "heroTitle", "heroSub", "card", "cardTitle"):
        v = data.get(k)
        if not v:
            continue
        print("%-12s font=%s/%s/%s color=%s opacity=%s" % (
            k, v["fontSize"], v["fontWeight"], v["lineHeight"], v["color"], v["opacity"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""深色分支的截图核对：给 <html> 加上 darkmode 再截，确认深色玻璃没坏。

为什么单独写：默认改回浅色之后，深色那套（darkmode 分支）就没有页面会
自然走到它了 —— 只有用户点按钮才会进。这种"平时看不见"的分支最容易在
重构时被改坏而没人发现，所以留一个能单独截它的脚本。

用法：python tools/shot_dark.py [输出.png] [滚动像素]
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_ref", "dark.png")
    scroll = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    url = "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/")

    port = 9227
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        proc = subprocess.Popen([
            find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof6"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(4)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)

    eval_on_page(ws, "document.documentElement.classList.add('darkmode');"
                     "window.scrollTo(0,%d);" % scroll)
    time.sleep(1)

    host_port = ws.split("//")[1].split("/")[0]
    host, p = host_port.split(":")
    path = "/" + ws.split("//")[1].split("/", 1)[1]
    sock = socket.create_connection((host, int(p)), timeout=60)
    sock.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
                  "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                  "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host_port)).encode())
    sock.recv(4096)

    def send(o):
        pl = json.dumps(o).encode()
        hd = bytearray([0x81])
        if len(pl) < 126:
            hd.append(0x80 | len(pl))
        elif len(pl) < 65536:
            hd.append(0x80 | 126)
            hd += len(pl).to_bytes(2, "big")
        else:
            hd.append(0x80 | 127)
            hd += len(pl).to_bytes(8, "big")
        m = os.urandom(4)
        hd += m
        sock.sendall(bytes(hd) + bytes(b ^ m[i % 4] for i, b in enumerate(pl)))

    send({"id": 5, "method": "Page.captureScreenshot",
          "params": {"format": "png"}})
    buf = b""
    while True:
        buf += sock.recv(1 << 20)
        s = buf.find(b"{")
        if s < 0:
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(buf[s:].decode("utf-8", "replace"))
        except Exception:
            continue
        if obj.get("id") == 5:
            open(out, "wb").write(base64.b64decode(obj["result"]["data"]))
            print("已写入 %s" % out)
            break
    sock.close()
    if proc:
        proc.terminate()


if __name__ == "__main__":
    main()

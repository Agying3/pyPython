# -*- coding: utf-8 -*-
"""内容区截图：无头浏览器里先滚一屏，再截 —— 直接截会拍到壁纸封面。

为什么需要：`--screenshot` 只能截首屏或整页，而本站首屏是 100vh 封面，
整页截图的"内容区"落在 900px 以下，用 --window-size=1440,2400 截出来的
其实是"更长的封面"，不是滚动后的真实位置。

用法：python tools/shot_local.py [输出.png] [滚动像素] [宽] [高]
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_ref", "mine_content.png")
    scroll = int(sys.argv[2]) if len(sys.argv) > 2 else 880
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1440
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    url = "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/")

    port = 9224
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        proc = subprocess.Popen([
            find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof3"),
            "--window-size=%d,%d" % (w, h), "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(4)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)

    eval_on_page(ws, "window.scrollTo(0,%d); document.title='SCROLLED';" % scroll)
    time.sleep(1)

    # 用 CDP 的 Page.captureScreenshot 拿真实视口
    import socket

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

    send({"id": 9, "method": "Page.captureScreenshot",
          "params": {"format": "png", "captureBeyondViewport": False}})
    buf = b""
    shots = 0
    while shots < 400:
        buf += sock.recv(1 << 20)
        s = buf.find(b"{")
        if s < 0:
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(buf[s:].decode("utf-8", "replace"))
        except Exception:
            continue
        if obj.get("id") == 9:
            import base64
            open(out, "wb").write(base64.b64decode(obj["result"]["data"]))
            print("已写入 %s" % out)
            break
        shots += 1
    sock.close()
    if proc:
        proc.terminate()


if __name__ == "__main__":
    main()

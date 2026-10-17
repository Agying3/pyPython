# -*- coding: utf-8 -*-
"""把参考站的字体文件抓下来自己量 —— 不信 font-family 字符串。

为什么再写一个：`getComputedStyle().fontFamily` 只会告诉你"写的是谁",
不会告诉你"浏览器真的用了谁"。Argon 的字体栈第一项是 `echo`，
没装这款字时浏览器会逐级回退，肉眼看着像又不像，说不清。

做法：
  1. CDP 里用 document.fonts 列出所有已加载的 FontFace 及其 src / weight；
  2. 下载这些字体文件，用 fontTools 读 name 表拿到真正的中文名 / 英文名；
  3. 把字体路径注册进本机（用户字体目录），再让浏览器重新量宽度，
     证明"装上 echo 之后渲染宽度会变"。

用法：python tools/probe_fonts.py [url] [outdir]
依赖：fontTools（可选，没有就只落文件 + 报 hash）
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa: E402

COLLECT_FONTS = r"""
(async () => {
  // 等字体加载完
  try { await document.fonts.ready; } catch (e) {}
  const out = [];
  for (const f of Array.from(document.fonts)) {
    out.push({family: f.family, weight: f.weight, style: f.style,
              status: f.status, unicodeRange: f.unicodeRange});
  }
  // @font-face 规则里的 src（document.fonts 拿不到 url）
  const faces = [];
  const walk = (rules) => {
    for (const r of Array.from(rules || [])) {
      if (r.type === 5 || r.constructor.name === 'CSSFontFaceRule') {
        faces.push({txt: r.cssText.slice(0, 900)});
      } else if (r.cssRules) walk(r.cssRules);
    }
  };
  for (const sh of Array.from(document.styleSheets)) {
    try { walk(sh.cssRules); } catch (e) {}
  }
  return {loaded: out, faces: faces};
})()
"""


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://xing.xo.je/"
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "_ref", "fonts")
    os.makedirs(outdir, exist_ok=True)

    port = 9222
    import subprocess
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        edge = find_edge()
        proc = subprocess.Popen([
            edge, "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(8)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)
    data = eval_on_page(ws, COLLECT_FONTS)
    if proc:
        proc.terminate()

    with open(os.path.join(outdir, "fontfaces.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("=== document.fonts 已加载 %d 个 ===" % len(data["loaded"]))
    for f in data["loaded"]:
        print("  %-28s weight=%-8s style=%-6s %s" % (
            f["family"], f["weight"], f["style"], f["status"]))

    print()
    print("=== @font-face 规则 %d 条 ===" % len(data["faces"]))
    for f in data["faces"]:
        print("  " + f["txt"][:400].replace("\n", " "))


if __name__ == "__main__":
    main()

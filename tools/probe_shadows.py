# -*- coding: utf-8 -*-
"""把参考站 CSS 里所有 box-shadow 声明捞出来，看它的阴影体系有几档。

为什么要这个：#48 我抄了 shadow-sm（0 2px 4px .075），但那是 Bootstrap 的小档。
Argon 主题自己也有一套阴影（设计系统里通常是 0 0 2rem 级别的大扩散）。
"玻璃浮起来"的观感靠的是大档，不是小档；只抄小档，卡片就贴在壁纸上。

做法：遍历所有样式表规则，正则抓 box-shadow / --shadow* 自定义属性，
按"扩散半径"排序输出，方便挑出真正的浮起档。

用法：python tools/probe_shadows.py [url]
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa

SCAN = r"""
(() => {
  const out = [];
  const walk = (rules) => {
    for (const r of Array.from(rules || [])) {
      if (r.cssRules) { walk(r.cssRules); continue; }
      const st = r.style;
      if (!st) continue;
      const sel = r.selectorText || '';
      const sh = st.getPropertyValue('box-shadow');
      if (sh && sh !== 'none') out.push({sel: sel.slice(0, 80), v: sh.slice(0, 160)});
      for (const p of Array.from(st)) {
        if (p.startsWith('--') && /shadow/i.test(p)) {
          out.push({sel: sel.slice(0, 60) + ' [' + p + ']',
                    v: st.getPropertyValue(p).slice(0, 160)});
        }
      }
    }
  };
  for (const sh of Array.from(document.styleSheets)) {
    try { walk(sh.cssRules); } catch (e) {}
  }
  return out;
})()
"""


def spread(v):
    """粗取阴影里的模糊半径（第三个数），用来排序。"""
    m = re.findall(r"(-?\d*\.?\d+)px", v)
    nums = [float(x) for x in m]
    return nums[2] if len(nums) >= 3 else 0


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://xing.xo.je/"
    port = 9229
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        proc = subprocess.Popen([
            find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof8"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(8)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)
    data = eval_on_page(ws, SCAN)
    if proc:
        proc.terminate()

    seen, rows = set(), []
    for d in data or []:
        key = (d["sel"], d["v"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(d)

    rows.sort(key=lambda d: -spread(d["v"]))

    print("=" * 78)
    print("参考站 box-shadow 声明，共 %d 条（按模糊半径从大到小）" % len(rows))
    print("=" * 78)
    for d in rows[:35]:
        print("  blur=%5.1f  %-42s  %s" % (spread(d["v"]), d["sel"], d["v"]))

    dest = os.path.join(ROOT, "_ref", "shadows.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("\n完整清单：%s" % dest)


if __name__ == "__main__":
    main()

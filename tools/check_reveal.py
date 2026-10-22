# -*- coding: utf-8 -*-
"""验证滚动浮现真的生效：不是"我写了 CSS"，而是"浏览器真的先藏后现"。

做法（三步都为真才算过）：
  1. 首屏加载后，视口外的卡片 opacity 应该 ≈ 0（被 reveal-ready 藏起来）；
  2. 滚到它跟前，等过渡结束，opacity 应该 = 1 且带 is-in；
  3. 已经出现过的卡片，滚走再滚回来**不应该**重新变透明（只播一次）。

用法：python tools/check_reveal.py
退出码非 0 = 动画没按预期工作。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa

STATE = r"""
(() => {
  const cards = Array.from(document.querySelectorAll('.post-card'));
  return {
    ready: document.body.classList.contains('reveal-ready'),
    total: cards.length,
    cards: cards.map(el => {
      const c = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {op: parseFloat(c.opacity),
              top: Math.round(r.top), bottom: Math.round(r.bottom),
              inView: r.top < window.innerHeight && r.bottom > 0,
              isIn: el.classList.contains('is-in')};
    }),
    scrollY: Math.round(window.scrollY),
    vh: window.innerHeight
  };
})()
"""


def main():
    url = "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/")
    port = 9230
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        proc = subprocess.Popen([
            find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof9"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(4)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)

    ok, bad = [], []

    def check(cond, label, detail=""):
        (ok if cond else bad).append(label)
        print("  %s %-44s %s" % ("[OK]  " if cond else "[FAIL]", label,
                                 "" if cond else detail))

    print("=" * 72)
    print("滚动浮现验证")
    print("=" * 72)

    start = eval_on_page(ws, STATE)
    check(start["ready"] is True, "body 有 reveal-ready（JS 检测到能力）")
    hidden = [c for c in start["cards"] if not c["inView"]]
    check(bool(hidden), "首屏有视口外的卡片可测", str(start["cards"]))
    if hidden:
        check(all(c["op"] < 0.15 for c in hidden),
              "视口外卡片初始是隐藏的（opacity < .15）",
              str([round(c["op"], 2) for c in hidden]))

    # 滚到最后一张卡片
    eval_on_page(ws, "window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.6)
    after = eval_on_page(ws, STATE)
    visible = [c for c in after["cards"] if c["inView"]]
    check(bool(visible), "滚动后有卡片进入视口")
    if visible:
        check(all(abs(c["op"] - 1) < 0.02 for c in visible),
              "进入视口后 opacity 到 1",
              str([round(c["op"], 2) for c in visible]))
        check(all(c["isIn"] for c in visible),
              "进入视口后带 is-in")

    # 往回滚：出现过的卡片不该重新变透明
    eval_on_page(ws, "window.scrollTo(0, 0);")
    time.sleep(0.9)
    back = eval_on_page(ws, STATE)
    replayed = [c for c in back["cards"] if c["isIn"] and c["op"] < 0.5]
    check(not replayed, "滚回去不重播（已出现的仍是实心）",
          str([round(c["op"], 2) for c in replayed]))

    if proc:
        proc.terminate()

    print()
    print("通过 %d / 失败 %d" % (len(ok), len(bad)))
    for b in bad:
        print("   -", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""参考站的「往下滑弹出来」到底是怎么实现的：动画库？CSS 过渡？IntersectionObserver？

为什么不能猜：滚动浮现有五六种常见实现（AOS / wow.js / animate.css +
IntersectionObserver / 纯 CSS scroll-driven / JS 直接加 class），
不同实现写出来的效果差很多（位移距离、时长、缓动、是否只播一次）。
猜错就变成"我们自己发明了一种弹出"，不是参考站那个。

做法：
  1. 扫 document.styleSheets，把带 animation / transition 的规则全捞出来；
  2. 扫 body 和文章卡片上的 class，找 AOS/wow/animate/reveal 这类特征；
  3. 滚到某张卡片位置，读它滚动前后的 transform / opacity / class 变化。

用法：python tools/probe_reveal.py [url]
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa

SCAN = r"""
(() => {
  const anim = [];
  const walk = (rules, sheetHref) => {
    for (const r of Array.from(rules || [])) {
      if (r.cssRules) { walk(r.cssRules, sheetHref); continue; }
      const t = r.cssText || '';
      if (/transition\s*:|animation\s*:|@keyframes|opacity:\s*0|transform:\s*translate/i.test(t)
          && t.length < 600) {
        anim.push(t);
      }
    }
  };
  for (const sh of Array.from(document.styleSheets)) {
    try { walk(sh.cssRules, sh.href); } catch (e) {}
  }

  // 特征 class 扫描：整页所有 class 里出现 reveal/aos/wow/animate/rise/float 的
  const hits = [];
  document.querySelectorAll('*').forEach(el => {
    const c = (el.className || '').toString();
    if (/aos|wow|animate|reveal|rise|float|fade|slide|scroll-magic|scrollreveal/i.test(c)) {
      const r = el.getBoundingClientRect();
      if (r.height > 30) hits.push({cls: c.slice(0, 100),
        tag: el.tagName.toLowerCase(),
        rect: [Math.round(r.x), Math.round(r.y + window.scrollY),
               Math.round(r.width), Math.round(r.height)]});
    }
  });

  // 页面挂的第三方脚本
  const scripts = Array.from(document.scripts).map(s => s.src).filter(Boolean);

  // 卡片滚动前后的状态（先只看当前）
  const cards = Array.from(document.querySelectorAll('.post, article.post, .card')).slice(0, 4);
  const cardState = cards.map(el => {
    const c = getComputedStyle(el);
    return {cls: (el.className||'').toString().slice(0,80),
            opacity: c.opacity, transform: c.transform,
            transition: c.transition.slice(0, 200),
            animation: c.animationName + ' ' + c.animationDuration};
  });

  return {
    animRules: anim.slice(0, 80),
    featureHits: hits.slice(0, 30),
    scripts: scripts.slice(0, 40),
    cardState,
    bodyClass: document.body.className,
  };
})()
"""

# 滚到 1200 之后，同一批卡片的状态（看它是不是"浮现"过）
AFTER = r"""
(() => {
  const cards = Array.from(document.querySelectorAll('.post, article.post, .card')).slice(0, 4);
  return cards.map(el => {
    const c = getComputedStyle(el);
    return {cls: (el.className||'').toString().slice(0,80),
            opacity: c.opacity, transform: c.transform};
  });
})()
"""


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://xing.xo.je/"
    port = 9228
    proc = None
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2)
    except Exception:
        proc = subprocess.Popen([
            find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
            "--disable-gpu", "--hide-scrollbars",
            "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof7"),
            "--window-size=1440,900", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)

    tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
    time.sleep(9)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)

    before = eval_on_page(ws, SCAN)
    eval_on_page(ws, "window.scrollTo(0, 1400);")
    time.sleep(2)
    after = eval_on_page(ws, AFTER)

    if proc:
        proc.terminate()

    out = os.path.join(ROOT, "_ref", "reveal.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"before": before, "after": after,
                   "before_scroll_count": len(before.get("animRules") or [])},
                  f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("body class: %s" % before.get("bodyClass"))
    print("=" * 70)
    print("\n--- 疑似动画类名的元素（%d 个）---" % len(before.get("featureHits") or []))
    for h in before.get("featureHits") or []:
        print("  %-12s %-60s rect=%s" % (h["tag"], h["cls"], h["rect"]))

    print("\n--- 外来脚本 ---")
    for s in before.get("scripts") or []:
        print("  " + s[:110])

    print("\n--- 卡片滚动前 ---")
    for c in before.get("cardState") or []:
        print("  op=%s tf=%s cls=%s" % (c["opacity"], c["transform"][:30], c["cls"]))

    print("\n--- 卡片滚动后 ---")
    for c in after or []:
        print("  op=%s tf=%s cls=%s" % (c["opacity"], c["transform"][:30], c["cls"]))

    print("\n--- 含 transition/animation 的 CSS 规则（%d 条，列前 25）---"
          % len(before.get("animRules") or []))
    for r in (before.get("animRules") or [])[:25]:
        print("  " + r[:220].replace("\n", " "))


if __name__ == "__main__":
    main()

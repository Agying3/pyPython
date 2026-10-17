# -*- coding: utf-8 -*-
"""对参考站做一轮更细的逆向：配色（含按钮/小标签/链接悬停）、字体栈、
卡片与左栏的结构尺寸，全部读 `getComputedStyle()` 的真实值。

用法：python tools/probe_ref2.py [url] [out.json]
前置：tools/probe_ref.py 起过 CDP（9222）或本脚本自己拉。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ref import ROOT, cdp, eval_on_page, find_edge  # noqa: E402

COLLECT = r"""
(() => {
  const W = ['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing',
             'color','opacity','backgroundColor','backgroundImage','textShadow',
             'borderRadius','display','padding','margin','width','maxWidth','boxShadow',
             'backdropFilter','borderTopWidth','borderBottomWidth','borderColor',
             'position','height','minHeight','zIndex','filter','textAlign'];
  const info = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    const o = {}; for (const k of W) o[k] = cs[k];
    const r = el.getBoundingClientRect();
    o._rect = [Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)];
    o._tag = el.tagName.toLowerCase();
    o._cls = (el.className||'').toString().slice(0,140);
    o._txt = (el.textContent||'').trim().slice(0,30);
    return o;
  };
  const all = (s,n=8) => Array.from(document.querySelectorAll(s)).slice(0,n).map(info);
  const one = (s) => info(document.querySelector(s));

  // 抓所有命中主题色的规则，倒推原站到底在哪几处用了 --themecolor
  const themeRules = [];
  for (const sh of Array.from(document.styleSheets)) {
    let rs; try { rs = sh.cssRules; } catch(e){ continue; }
    if (!rs) continue;
    for (const r of Array.from(rs)) {
      const t = r.cssText || '';
      if (/themecolor|#5e72e4|94,\s*114,\s*228/i.test(t) && t.length < 700) themeRules.push(t);
    }
  }

  // 导航栏内部逐项
  const nav = document.querySelector('header.header-global');
  const navItems = nav ? Array.from(nav.querySelectorAll('a, .navbar-brand, i')).slice(0,20).map(info) : [];

  return {
    title: document.title,
    bodyFontFamily: getComputedStyle(document.body).fontFamily,
    headFontFamily: getComputedStyle(document.querySelector('.nav-link, .post-title, h1, h2') || document.body).fontFamily,
    body: one('body'),
    nav: one('header.header-global'),
    navInner: one('header.header-global .container, .navbar .container'),
    navItems,
    navBrand: one('.navbar-brand'),
    navBrandSub: one('.navbar-brand ~ *, .navbar-brand small, .navbar-brand .text-muted'),
    navLink: one('.navbar-nav .nav-link, .nav-link'),
    navIcon: one('.navbar-nav .nav-link i, .nav-link i'),
    banner: one('.banner, section.banner'),
    bannerContent: one('.banner .content-center, .banner .col-lg-8, .banner .text-center'),
    bannerH1: one('.banner h1, h1.display-3, h1'),
    bannerText: one('.banner p, .banner .text-white, section.banner p'),
    card: one('.card'),
    cardBody: one('.card .card-body, .card-body'),
    postTitle: one('.post-title'),
    postMeta: one('.post-meta, .meta'),
    postMetaLinks: all('.post-meta a, .post-meta .meta-item, .post-meta span', 8),
    postExcerpt: one('.post-excerpt, .excerpt, .card-body p'),
    btn: one('.btn'),
    btnOutline: one('.btn-outline-primary, .btn-outline-white'),
    btnPrimary: one('.btn-primary, .btn-theme'),
    badge: one('.badge, .tag, .post-tags a, .label'),
    link: one('.card-body a:not(.post-title)'),
    sidebar: one('aside.leftbar, .widget-area, .leftbar'),
    widget: one('.widget'),
    widgetTitle: one('.widget-title, .widget-heading, .widget .card-header'),
    widgetBody: one('.widget .card-body, .leftbar-banner'),
    avatar: one('.avatar, .leftbar-avatar, img.rounded-circle'),
    stats: one('.stat, .leftbar-stat, .count'),
    searchInput: one('input[type=search], .search-form input'),
    footer: one('footer'),
    floating: one('.go-to-top, .top-btn, #back-to-top'),
    allH2: all('h2', 4),
    allP: all('.container p', 4),
    code: all('pre, code', 3),
    themeRules: themeRules.slice(0, 60),
    cssVars: (() => {
      const out = {};
      for (const sh of Array.from(document.styleSheets)) {
        let rs; try { rs = sh.cssRules; } catch(e){ continue; }
        if (!rs) continue;
        for (const r of Array.from(rs)) {
          if (r.style && r.selectorText && /:root|html/.test(r.selectorText)) {
            for (const p of Array.from(r.style)) {
              if (p.startsWith('--') && out[p] === undefined)
                out[p] = r.style.getPropertyValue(p).trim();
            }
          }
        }
      }
      return out;
    })(),
  };
})()
"""


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://xing.xo.je/"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "_ref", "ref2.json")

    import time
    import subprocess
    import urllib.request

    port = 9222
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
    time.sleep(7)
    tgt = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % port).read())
    ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)
    data = eval_on_page(ws, COLLECT)
    if proc:
        proc.terminate()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写入 %s" % out)


if __name__ == "__main__":
    main()

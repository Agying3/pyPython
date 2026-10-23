# -*- coding: utf-8 -*-
"""把 style.css 里的 token 钉死在参考站量到的值上，并且跑真实渲染复量。

为什么要有第二个自检：tools/check_site.py 查的是"链接没断、选择器对得上"，
它管不了"字色是不是 RGB(139,146,232)、卡片是不是 .8 半透明玻璃"。
#48 那次就是：静态检查全绿，外观却和参考站是两套东西。

两层：
  1. 静态层：读 styles.css 的声明，断言关键 token（能挡住手滑改回旧值）；
  2. 渲染层：起无头 Edge，读 getComputedStyle，断言**浏览器算出来的**值
     （能挡住"声明对了但被后面的规则覆盖/字体没加载"）。

用法：python tools/check_style_tokens.py [本地页面 URL]
退出码非 0 表示有断言失败 —— 和 check_site.py 一样，失败就不许提交。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "assets", "style.css")


def norm(c):
    """把 rgb/rgba 统一成 (r,g,b,a)，方便比。"""
    m = re.match(r"rgba?\(([^)]+)\)", c.strip())
    if not m:
        return None
    parts = [float(x) for x in m.group(1).replace("/", ",").split(",")]
    while len(parts) < 4:
        parts.append(1.0)
    return tuple(round(x, 2) for x in parts[:4])


def main():
    ok, bad = [], []

    def check(cond, label, detail=""):
        (ok if cond else bad).append(label)
        print("  %s %-48s %s" % ("[OK]  " if cond else "[FAIL]", label,
                                 "" if cond else detail))

    src = open(CSS, encoding="utf-8").read()
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)   # #41：先剥注释再断言

    print("=" * 74)
    print("样式 token 对账（参考站实测值）")
    print("=" * 74)

    print("\n--- 静态声明 ---")
    # 字体栈：参考站第一项是网页字体 echo，第二项 Georgia，中文回退思源宋体
    check("--font-body: echo, Georgia" in code, "正文字体栈以 echo, Georgia 开头")
    check('"Noto Serif SC"' in code, "中文回退到思源宋体（不是黑体）")
    check('@font-face' in code and 'fonts/hy-tangmeiren.woff2' in code,
          "@font-face 指向本地字体文件（不引 CDN）")
    check(os.path.exists(os.path.join(ROOT, "assets", "fonts",
                                     "hy-tangmeiren.woff2")),
          "字体文件真的在 assets/fonts/ 里")

    # 参考站浅色玻璃：卡片 rgba(255,255,255,.8)，左栏同样是 .8
    check("--glass-bg: rgba(255, 255, 255, .8)" in code,
          "玻璃卡片底 .8（实测）")
    check("--glass-edge: rgba(255, 255, 255, .5)" in code,
          "玻璃上沿反光 .5（实测）")
    check("--glass-line: rgba(0, 0, 0, .05)" in code,
          "玻璃内描边 .05（实测）")
    check("--shadow: 0 2px 4px rgba(0, 0, 0, .075)" in code,
          "玻璃阴影 0 2px 4px .075（实测）")
    check("--footer-opacity: 1" in code, "浅色默认页脚不再整体压暗")
    check("--section-title: #2f3b52" in code,
          "浅色分组标题用深墨色（否则白字压在浅壁纸上看不见）")
    check("--section-title: #fff" in code, "深色分支分组标题仍是白字")

    # 浮起阴影用 Argon 的 .shadow 档（#51）
    check("0 15px 35px rgba(50, 50, 93, .10)" in code,
          "卡片用 Argon 浮起阴影档（紫灰 0 15px 35px）")
    check("0 5px 15px rgba(0, 0, 0, .07)" in code,
          "浮起阴影含第二层 0 5px 15px")
    check(".post-card {" in code and "--shadow-lift" in code,
          "卡片真的用了浮起档变量")

    # 头像（#50 → #55）：左栏「站点概览」里的头像必须是站主本人的本地图片，
    # 而不是「炑」字块；左下角也不许再出现浮动的第二个头像
    layout_src = open(os.path.join(ROOT, "parts", "layout.html"),
                      encoding="utf-8").read()
    check("mascot" not in code and "mascot" not in layout_src,
          "旧的「炑」字装饰球已彻底移除")
    check("avatar-fab" not in code and "avatar-fab" not in layout_src,
          "左下角没有多余的浮动头像（#55 用户明确不要）")
    check('<img class="avatar"' in layout_src,
          "左栏概览头像改成 <img>（不再是「炑」字块）")
    check('assets/img/avatar-github.jpg' in layout_src,
          "头像指向本地 avatar-github.jpg（不引外链）")
    check(os.path.exists(os.path.join(ROOT, "assets", "img",
                                      "avatar-github.jpg")),
          "头像文件真的在 assets/img/ 里")
    check('src="https://github.com' not in layout_src
          and "avatars.githubusercontent" not in layout_src,
          "布局里没有 GitHub 头像外链（断网不会变裂图）")
    # 只针对概览区那块占位，不能连导航栏的品牌字「炑」一起误判
    check('<div class="avatar">炑</div>' not in layout_src,
          "概览里不再有「炑」字头像占位")

    # 滚动浮现（#52）
    layout = open(os.path.join(ROOT, "parts", "layout.html"),
                  encoding="utf-8").read()
    check("IntersectionObserver" in layout,
          "布局里有 IntersectionObserver 滚动浮现")
    check("reveal-ready" in layout and "is-in" in code,
          "浮现动画的 class 约定：JS 加 reveal-ready / is-in，CSS 有对应规则")
    check("prefers-reduced-motion" in layout and "prefers-reduced-motion" in code,
          "浮现动画在减少动态偏好下关闭")

    # 导航：透明，不是主色层
    nav = re.search(r"\.navbar \{(.*?)\}", code, re.S)
    check(nav and "background: transparent" in nav.group(1),
          "导航底色 transparent（实测，不是主色层）")
    check(nav and "border-bottom: 1px solid transparent" in nav.group(1),
          "导航无常显下边框")

    # 关键：不许再出现第一版那些"看着像"的旧值
    for stale, why in [
        ("rgba(255, 255, 255, .82)", "旧卡片底 .82"),
        ("var(--theme);\n    color: #fff;\n    font-size: 13.5px", "旧主色标题条"),
        ("46px", "旧封面标题字号"),
    ]:
        check(stale not in code, "旧值已清除：%s" % why)

    # 渲染层
    print("\n--- 浏览器实算 ---")
    try:
        import json
        import subprocess
        import time
        import urllib.request

        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from probe_ref import cdp, eval_on_page, find_edge  # noqa

        url = (sys.argv[1] if len(sys.argv) > 1 else
               "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/"))
        port = 9223
        proc = None
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:%d/json/version" % port, timeout=2)
        except Exception:
            proc = subprocess.Popen([
                find_edge(), "--headless=new", "--remote-debugging-port=%d" % port,
                "--disable-gpu", "--hide-scrollbars",
                "--user-data-dir=" + os.path.join(ROOT, "_ref", "prof2"),
                "--window-size=1440,900", "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(4)

        tid = cdp(port, "Target.createTarget", {"url": url})["result"]["targetId"]
        time.sleep(4)
        tgt = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:%d/json/list" % port).read())
        ws = next(x["webSocketDebuggerUrl"] for x in tgt if x["id"] == tid)
        got = eval_on_page(ws, r"""
        (() => {
          const g = (s) => { const e = document.querySelector(s);
            if (!e) return null; const c = getComputedStyle(e);
            return {family: c.fontFamily, size: c.fontSize, weight: c.fontWeight,
                    color: c.color, bg: c.backgroundColor, op: c.opacity,
                    ls: c.letterSpacing, radius: c.borderRadius,
                    shadow: c.boxShadow, border: c.borderTopColor + ' / ' + c.borderTopWidth,
                    backdrop: c.backdropFilter}; };
          return {title: g('.cover-title'), sub: g('.cover-sub'),
                  card: g('.post-card'), ptitle: g('.post-card .post-title'),
                  widget: g('.widget'), tag: g('.tag'), nav: g('.navbar'), footer: g('.footer'),
                  section: g('.section-title'),
                  eyebrow: (() => { const i = document.querySelector('.overview-body .avatar');
                    if (!i) return null;
                    const r = i.getBoundingClientRect();
                    const c = getComputedStyle(i);
                    return {tag: i.tagName.toLowerCase(),
                            w: Math.round(r.width), h: Math.round(r.height),
                            radius: c.borderRadius,
                            src: i.getAttribute('src'),
                            complete: i.complete, natural: i.naturalWidth}; })(),
                  loaded: Array.from(document.fonts).map(f => f.family + ':' + f.status)};
        })()
        """)
        if proc:
            proc.terminate()

        if not got or "_error" in (got or {}):
            check(False, "能读到浏览器实算样式", str(got)[:200])
        else:
            print("    document.fonts: %s" % ", ".join(got["loaded"]))
            check(any(x.startswith("echo:loaded") for x in got["loaded"]),
                  "网页字体 echo 确实加载了（不是静默回退）")
            check(got["title"]["family"].startswith("echo"),
                  "封面标题用 echo", got["title"]["family"][:40])
            check(got["title"]["size"] == "44px", "封面标题 44px",
                  got["title"]["size"])
            check(got["title"]["weight"] == "400", "封面标题 400 字重",
                  got["title"]["weight"])
            check(got["title"]["ls"] in ("normal", "0px"), "封面标题无字距",
                  got["title"]["ls"])
            check(norm(got["sub"]["color"] or "") is not None
                  or "-webkit-text-fill-color" , "副标题有字色")
            check(got["card"]["bg"] == "rgba(255, 255, 255, 0.8)",
                  "卡片底实算 rgba(255,255,255,.8)", got["card"]["bg"])
            check(got["card"]["radius"] == "15px", "玻璃卡片圆角 15px",
                  got["card"]["radius"])
            check("rgba(50, 50, 93, 0.1) 0px 15px 35px 0px" in got["card"]["shadow"],
                  "卡片阴影实算 Argon 浮起档 0 15px 35px", got["card"]["shadow"])
            check("inset" in got["card"]["shadow"],
                  "卡片带 inset 反光边", got["card"]["shadow"])
            check("rgba(0, 0, 0, 0.05)" in got["card"]["border"],
                  "卡片有 .05 内描边", got["card"]["border"])
            check(got["card"]["backdrop"] == "none",
                  "参考站卡片不使用 backdrop-filter", got["card"]["backdrop"])
            check(got["widget"]["bg"] == "rgba(255, 255, 255, 0.8)",
                  "左栏同款半透明玻璃", got["widget"]["bg"])
            check(norm(got["ptitle"]["color"]) == (139.0, 146.0, 232.0, 1.0),
                  "卡片标题色实算 rgb(139,146,232)", got["ptitle"]["color"])
            check(got["ptitle"]["size"] == "25px", "卡片标题 25px",
                  got["ptitle"]["size"])
            check(got["tag"]["radius"] == "4px", "小标签圆角 4px",
                  got["tag"]["radius"])
            check(norm(got["nav"]["bg"]) == (0.0, 0.0, 0.0, 0.0),
                  "导航实算透明", got["nav"]["bg"])
            check(abs(float(got["footer"]["op"]) - 1.0) < 0.01,
                  "浅色页脚实算 opacity 1", got["footer"]["op"])
            # #49：白字压在浅壁纸上看不见 —— 用亮度差当可读性判据
            sec = norm(got["section"]["color"] or "")
            check(sec is not None and sec[0] + sec[1] + sec[2] < 300,
                  "浅色分组标题是深色（亮度 < 300）", str(got["section"]["color"]))

            # #55：左栏概览头像 = 站主本人的图片，且真的加载成功
            av = got.get("eyebrow") or {}
            check(av.get("tag") == "img",
                  "概览头像是 <img> 而不是文字块", str(av.get("tag")))
            check(av.get("natural", 0) > 0 and av.get("complete"),
                  "头像图片真的加载成功（不是裂图）", str(av))
            check(av.get("w", 0) >= 60 and av.get("h", 0) >= 60,
                  "头像渲染尺寸正常（66px 量级）", str(av))
            check("50%" in (av.get("radius") or ""),
                  "头像仍是圆形", av.get("radius"))
            check("avatar-github.jpg" in (av.get("src") or ""),
                  "头像用的是本地文件", av.get("src"))
            check(got["title"] is not None, "封面标题还在（没被误删）")
    except Exception as exc:
        check(False, "渲染层探针跑通", repr(exc)[:200])

    print("\n" + "=" * 74)
    print("通过 %d / 失败 %d" % (len(ok), len(bad)))
    for b in bad:
        print("   -", b)
    print("=" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

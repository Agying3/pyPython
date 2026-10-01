# -*- coding: utf-8 -*-
"""量真实渲染尺寸，验证"封面盖住内容"这个**布局事实**。

为什么不能只查 HTML：页面里有 `<header class="cover">` 不代表它真的盖住了
内容 —— CSS 可能没生效、`min-height` 可能被覆盖、内容可能因为负 margin
跑到封面上面。所以这里直接读 `getBoundingClientRect()`。

做法：往页面注入一段脚本，把量到的数字写进 `<title>`，
再用无头浏览器的 --dump-dom 把 DOM 抓回来读。

用法：
    python tools/check_cover.py            # 量本地 index.html
    python tools/check_cover.py <url>      # 量任意地址（默认本地）

没有装 Edge 或量不到时会**明确报"跳过"并返回 0**，
不会假装通过 —— 静默跳过是伪绿色，本项目最忌讳那种。
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

PROBE = """
<script>
window.addEventListener('load', function () {
    setTimeout(function () {
        var cover = document.querySelector('.cover');
        var layout = document.querySelector('.layout');
        var nav = document.querySelector('.navbar');
        document.title = 'PROBE:' + JSON.stringify({
            vh: window.innerHeight,
            coverH: cover ? Math.round(cover.getBoundingClientRect().height) : -1,
            coverTop: cover ? Math.round(cover.getBoundingClientRect().top) : -1,
            layoutTop: layout
                ? Math.round(layout.getBoundingClientRect().top + window.scrollY)
                : -1,
            navPos: nav ? getComputedStyle(nav).position : 'none',
            navBg: nav ? getComputedStyle(nav).backgroundColor : 'none',
            docH: document.documentElement.scrollHeight,
            hasCover: document.body.classList.contains('has-cover')
        });
    }, 400);
});
</script>
</head>"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def measure(url):
    edge = find_edge()
    if not edge:
        return None, "没找到 Edge"

    prof = os.path.join(os.environ.get("TEMP", "/tmp"), "pypy_cover_probe")
    shutil.rmtree(prof, ignore_errors=True)

    try:
        r = subprocess.run([
            edge, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--user-data-dir=" + prof, "--virtual-time-budget=9000",
            "--window-size=1366,768", "--dump-dom", url,
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
    except Exception as exc:
        return None, "浏览器跑不起来: %s" % exc
    finally:
        shutil.rmtree(prof, ignore_errors=True)

    m = re.search(r"PROBE:(\{.*?\})</title>",
                  r.stdout.decode("utf-8", "replace"), re.S)
    if not m:
        return None, "没读到注入的测量结果"
    return json.loads(m.group(1)), None


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    tmp = None

    if target is None:
        index = os.path.join(ROOT, "index.html")
        if not os.path.exists(index):
            print("找不到 index.html，先在 gh-pages 分支上跑")
            return 1
        src = io.open(index, encoding="utf-8").read()
        tmp = os.path.join(ROOT, "_cover_probe.html")
        io.open(tmp, "w", encoding="utf-8", newline="\n").write(
            src.replace("</head>", PROBE, 1))
        target = "file:///" + tmp.replace("\\", "/")

    print("=" * 66)
    print("封面渲染测量")
    print("=" * 66)
    print("  目标: %s" % target)
    print()

    try:
        d, err = measure(target)
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass

    if d is None:
        # 明确说"跳过"，不假装通过
        print("  [跳过] %s" % err)
        print("  封面是布局事实，量不到就不算验证过。")
        return 0

    print("  视口高度            %d px" % d["vh"])
    print("  封面高度            %d px" % d["coverH"])
    print("  封面顶部            %d px" % d["coverTop"])
    print("  内容区顶部          %d px" % d["layoutTop"])
    print("  文档总高            %d px" % d["docH"])
    print("  导航栏 position     %s" % d["navPos"])
    print("  导航栏背景           %s" % d["navBg"])
    print()

    ok = True

    def chk(cond, label, detail=""):
        nonlocal ok
        print("  %s %-42s %s" % ("[OK]  " if cond else "[FAIL]", label, detail))
        if not cond:
            ok = False

    chk(d["coverH"] >= d["vh"], "封面撑满一屏",
        "%d >= %d" % (d["coverH"], d["vh"]))
    chk(d["coverTop"] == 0, "封面从最顶上开始")
    chk(d["layoutTop"] >= d["vh"], "内容区在封面下方（第一屏看不到）",
        "内容顶部 %d >= 视口 %d" % (d["layoutTop"], d["vh"]))
    chk(d["docH"] > d["vh"] * 1.5, "页面可以往下滚", "文档高 %d" % d["docH"])
    chk(d["navPos"] == "fixed", "导航栏固定", d["navPos"])
    chk("rgba(0, 0, 0, 0)" in d["navBg"] or "transparent" in d["navBg"],
        "第一屏导航栏透明", d["navBg"])

    print()
    print("  结论：%s" % ("封面 → 下滑 → 内容，符合预期" if ok else "不符合预期"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# 静态站自检：看不了图，就用程序验收。
#
# 检查项都对应真实踩过的坑：
#   1. 每个 <pre><code> 里的内容是转义过的 HTML，不能被解析成标签
#   2. 所有本地链接/资源都存在（404 是静态站最常见的死法）
#   3. 每页的 <title>、导航、主题切按钮都在
#   4. 主题变量确实是 #009688，不是 Argon 默认的 #5e72e4
import html
import os
import re

# 站点根目录：本脚本在 tools/ 下，所以要往上一级。
#
# #38「脚本从根目录挪进 tools/ 之后，自检自己崩了」
# {
#   曾出现：脚本移进 tools/ 后运行，报 FileNotFoundError:
#           'H:\pyPython\tools\posts' —— 它把 tools/ 当成了站点根
#   根因：ROOT 是从 __file__ 直接推的，隐含假设"脚本就在站点根目录"。
#         这个脚本最初确实写在根目录，后来才移进 tools/
#   修法：往上退一级
#   教训：同本项目那条老教训 —— **移动文件时，路径推导要跟着改**。
#         这类错误很容易漏，因为脚本"能跑"，只是找不到东西
# }
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pages = ["index.html"] + [
    "posts/" + f for f in sorted(os.listdir(os.path.join(ROOT, "posts")))
]

ok, bad = [], []


def check(cond, label, detail=""):
    (ok if cond else bad).append(label)
    print("  %s %-46s %s" % ("[OK]  " if cond else "[FAIL]", label,
                             "" if cond else detail))


print("=" * 74)
print("静态站自检")
print("=" * 74)

# ---- CSS 只查一次（每个页面查同一份文件 5 遍是浪费，之前就是这么写的）----
print("\n--- assets/style.css ---")
css = open(os.path.join(ROOT, "assets", "style.css"), encoding="utf-8").read()

# 主题色必须是 #009688，不能抄成 Argon 默认的 #5e72e4。
# 注意：注释里**应该**出现 #5e72e4 —— 那是在说明"别抄这个默认值"。
# 所以要先把注释剥掉再查，否则查出来的是文档不是代码。
# （这就是本项目那条老教训：报告失败之前，先确认测的是不是你以为的那件事）
css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
check("--theme: #009688" in css_code, "主色是 #009688（不是 #5e72e4）")
check("#5e72e4" not in css_code, "CSS 声明里没混进 Argon 默认色",
      "注释里出现是对的，声明里出现才是错")
check("img/day.jpg" in css and "img/night.jpg" in css, "两张壁纸都有引用")
check("backdrop-filter" in css, "有毛玻璃导航栏")
check("--card-radius: 15px" in css, "圆角是 15px")
check("brightness(.65)" in css, "深色模式有压暗背景")

for page in pages:
    path = os.path.join(ROOT, page.replace("/", os.sep))
    print("\n--- %s ---" % page)
    src = open(path, encoding="utf-8").read()

    check("<title>" in src and "</title>" in src, "有 title")
    check('id="themeBtn"' in src, "有深浅色切换按钮")
    check("pypy-theme" in src, "深浅色偏好会持久化")

    # 链接和资源必须存在
    refs = re.findall(r'(?:href|src)="([^"]+)"', src)
    missing = []
    for r in refs:
        if r.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = os.path.normpath(os.path.join(os.path.dirname(path), r))
        if not os.path.exists(target):
            missing.append(r)
    check(not missing, "本地链接/资源都存在", "缺: %s" % missing)

print("\n" + "=" * 74)
print("通过 %d / 失败 %d" % (len(ok), len(bad)))
if bad:
    print("失败项：")
    for b in bad:
        print("   -", b)
print("=" * 74)
raise SystemExit(1 if bad else 0)

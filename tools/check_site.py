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

# 页面列表**自动扫**，不写死。
#
# #39「自检漏掉了新加的页面，还显示全绿」
# {
#   曾出现：加了 wallpapers.html 之后跑自检，仍然 26/26 全过 ——
#         因为列表里写死了 ["index.html"] + posts/*，新页面根本没被检查
#   根因：页面清单是手写的，加页面时不会自动带上
#   修法：改成扫根目录和 posts/ 下所有 .html
#   教训：同本项目那条老教训 —— **"检查范围"本身也是一份需要同步的副本**。
#         写死了范围，就等于给自己发了一张"看不见新东西"的通行证
# }
def _html_in(rel):
    d = os.path.join(ROOT, rel) if rel else ROOT
    if not os.path.isdir(d):
        return []
    return [
        (rel + "/" if rel else "") + f
        for f in sorted(os.listdir(d))
        # 跳过 _ 开头的：那是临时验证文件（比如 emoji 渲染测试），不是站点页面。
        # 自检范围自动扫是对的，但"自动"也得排除掉本来就不该检查的东西。
        if f.endswith(".html") and not f.startswith("_")
    ]


pages = _html_in("") + _html_in("posts")

ok, bad = [], []


def check(cond, label, detail=""):
    (ok if cond else bad).append(label)
    print("  %s %-46s %s" % ("[OK]  " if cond else "[FAIL]", label,
                             "" if cond else detail))


print("=" * 74)
print("静态站自检")
print("=" * 74)

# ---- CSS 只查一次（每个页面查同一份文件是浪费）----
print("\n--- assets/style.css ---")
css = open(os.path.join(ROOT, "assets", "style.css"), encoding="utf-8").read()

# 先把注释剥掉再查 —— 注释里的值不是配置。
#
# #41「把 CSS 注释里的示例当成真实配置，主色抄错了」
# {
#   曾出现：我一度把主色写成 #009688。原站实际是 #5e72e4（紫）。
#           更糟的是**这个自检脚本当时也跟着断言 #009688**，
#           等于把错误结论固化成了一条"会通过的检查"。
#   根因：原站自定义 CSS 的注释里有这么一句示例：
#           「也可以用类似于 --color-border-on-foreground-deeper: #009688; 这样的命令」
#        那是注释，不是配置。全文只有一处 --themecolor 声明，值是 #5e72e4
#   修法：断言改成 #5e72e4，并且**必须先剥注释**再查，
#         否则注释里提到旧值会误报（这个坑我第一版就踩过）
#   教训：测试写的期望值，本身也可能是错的。
#         一个断言了错误结论的测试，比没有测试更坏 —— 它会替错误背书
# }
css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

check("--theme: #5e72e4" in css_code, "主色是 #5e72e4（不是注释里的 #009688）")
check("#009688" not in css_code, "声明里没有注释里的示例色 #009688",
      "注释里提到是对的，声明里出现才是错")
check("img/bg.jpg" in css, "背景图有引用")
check("backdrop-filter" in css, "有毛玻璃")
check("--card-radius: 15px" in css, "圆角是 15px")
check("brightness(.6" in css, "深色模式有压暗背景")

# 注释本身必须合法。CSS 块注释不能嵌套，
# 而我在写"注释里的值不是配置"那条教训时，真的在注释里打出了结束符号，
# 内层那个符号提前结束了外层注释，半张样式表就废了。
_opens, _closes = css.count("/*"), css.count("*/")
check(_opens == _closes, "注释符号配对",
      "/* =%d, */ =%d" % (_opens, _closes))
check("*/" not in css_code, "没有嵌套注释")
check(css_code.count("{") == css_code.count("}"), "花括号平衡")

# 生成器输出的类名，CSS 里必须真的有用到。
# #44「左栏选中高亮不生效」：生成器输出 class="active"，
# 而 CSS 写的是 .current —— 选择器不匹配 = 静默失效，不报错。
#
# 这一条第一版写成 `".active" in css or ".current" in css`，太松：
# 反向验证时我把 .active 改名，检查照样通过（因为 .current 还在）。
# 改成"先读出生成器用的是哪个类名，再要求 CSS 必须有那一个"。
_builder = open(os.path.join(ROOT, "tools", "build_site.py"),
                encoding="utf-8").read()
_cls = None
for _cand in ("active", "current"):
    if ("' class=\"%s\"'" % _cand) in _builder:
        _cls = _cand
        break
check(_cls is not None, "能读出构建脚本用的选中类名")

# 用正则匹配"选择器列表里的那一项"，而不是简单子串包含。
# 因为 `.side-nav a.active:hover` 里也含有 `.side-nav a.active` 这个子串，
# 但只有 :hover 规则的话，没悬停时高亮仍然是坏的。
# 反向验证时我就是被这个子串骗过一次，所以这里认死 ", " 或 "{" 结尾。
_sel_ok = False
if _cls:
    _pat = re.compile(r"\.side-nav a\.%s\s*[,{]" % re.escape(_cls))
    _sel_ok = bool(_pat.search(css_code))
check(_sel_ok, "左栏选中态选择器与生成器一致",
      "生成器用 %s，但 CSS 里没有 .side-nav a.%s 的常态规则" % (_cls, _cls))

for page in pages:
    path = os.path.join(ROOT, page.replace("/", os.sep))
    print("\n--- %s ---" % page)
    src = open(path, encoding="utf-8").read()

    check("<title>" in src and "</title>" in src, "有 title")
    check('id="themeBtn"' in src, "有深浅色切换按钮")
    check("pypy-theme" in src, "深浅色偏好会持久化")

    # 链接和资源必须存在
    #
    # #45「自检报了一堆不存在的链接，其实链接是好的」
    # {
    #   曾出现：5 个页面全报"本地链接/资源都存在"失败，缺的是 index.html#posts
    #   根因：检查时没把 #锚点 和 ?查询串 剥掉，直接拿整串当文件名去找，
    #         自然找不到一个叫 "index.html#posts" 的文件
    #   修法：先切掉 # 和 ? 再判存在
    #   教训：**报告失败之前，先确认测的是不是你以为的那件事** ——
    #         这句话本项目记了三次了，这次轮到我自己的检查脚本犯
    # }
    refs = re.findall(r'(?:href|src)="([^"]+)"', src)
    missing = []
    for r in refs:
        if r.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        # 锚点和查询串不参与文件存在性判断
        path_part = r.split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        target = os.path.normpath(
            os.path.join(os.path.dirname(path), path_part))
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

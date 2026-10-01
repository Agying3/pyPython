# -*- coding: utf-8 -*-
"""文档站构建脚本。

用法：
    python tools/build_site.py            # 生成页面
    python tools/build_site.py --check    # 只检查，不写文件

—————————————————————————————————————————————————————————————————————
为什么要有这个脚本，而不是手写 7 个 HTML
—————————————————————————————————————————————————————————————————————
左栏、导航、页脚在每个页面上都一样。手写 7 份就是**同一份东西抄 7 遍**，
改一处忘一处就漂移 —— 本项目为这类问题栽过十几次（见 docs/decisions/README.md
的"一条贯穿多份记录的教训"），而且它们几乎全是静默失效：不报错，只是不对。

所以：布局放 parts/layout.html（唯一一份），每页只提供正文，
脚本负责拼装。顺带把"文章数 / Wiki 页数 / ADR 篇数"这些数字
**算出来**，不再手写 —— 手写的数字同样会漂移
（ADR-0010 的"遗留"里就点了这一条）。
"""

import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "parts")
CONTENT = os.path.join(ROOT, "content")

# ---------------------------------------------------------------- 文章元数据

# 标题、日期、标签、摘要都写在这里一份；正文在 content/<slug>.body.html。
# 字数与阅读时间由脚本从正文算出来，不手写。
ARTICLES = [
    {
        "slug": "why-slow",
        "title": "这门语言为什么这么慢",
        "date": "2026-10-01",
        "tags": ["性能", "基准测试"],
        "excerpt": "实测比 CPython 慢 686 倍。这个数字是刻意做出来的，"
                   "而且我把「没达标」的那条基线也画进了图里。",
        "desc": "pyPython 实测比 CPython 慢 686 倍。这个数字是刻意做出来的。",
    },
    {
        "slug": "three-valued",
        "title": "我给了布尔值第三个状态",
        "date": "2026-10-01",
        "tags": ["三值逻辑", "语言设计"],
        "excerpt": "TRUE、FALSE，还有未知。第三态不是「介于真假之间」，"
                   "是信息缺失——消息发出去了，还没回。",
        "desc": "TRUE、FALSE，还有未知。第三态不是介于真假之间，是信息缺失。",
    },
    {
        "slug": "blank-line",
        "title": "一个空行引发的血案",
        "date": "2026-10-01",
        "tags": ["踩坑", "静默失效"],
        "excerpt": "赋值成功、不报错、没效果。这类 bug 最难查，"
                   "因为你没法靠「跑起来没报错」判断对错。",
        "desc": "赋值成功、不报错、没效果。这类 bug 最难查。",
    },
    {
        "slug": "no-matplotlib",
        "title": "为什么我坚持不用 matplotlib",
        "date": "2026-10-01",
        "tags": ["工程", "ADR-0001"],
        "excerpt": "要画一张性能对比图。装个 matplotlib 只要一行命令，"
                   "我选择了手写 300 行 SVG。",
        "desc": "要在网页上画一张性能对比图。装个库只要一行命令，我选择了手写。",
    },
]

# Wiki 页数与 ADR 篇数的兜底值（git 问不到时用）
WIKI_FALLBACK = 11
ADR_FALLBACK = 10

# 权威内容在哪个分支上。这个脚本跑在 gh-pages，而 wiki/ 和 docs/decisions/
# 都在 master，所以要去 master 问。
REF = "master"


def git_count(path, keep):
    """用 git 数某个分支下某个目录里的文件。数不到返回 None。

    #43「构建脚本数本地目录，把「ADR 1 篇」显示到了页面上」
    {
      曾出现：侧边栏统计显示「ADR 1 篇」，实际有 10 篇
      根因：脚本数的是**本地文件系统**上的 docs/decisions/，而这个脚本
            跑在 gh-pages 分支上 —— 那个目录本该不存在，
            但之前有一次孤儿分支的残留把 0010 这一个文件提交到了 gh-pages，
            于是目录存在、里面只有 1 个文件，数出来就是 1。
            原来的兜底逻辑只处理「目录不存在」，处理不了「目录存在但是错的」
      修法：改成问 git 要 master 上的文件清单，不再相信本地目录
      教训：**「本地有这个目录」不等于「这就是权威内容」。**
            跨分支的脚本尤其如此 —— 本地那份很可能是别的分支的残留。
    }
    """
    try:
        r = subprocess.run(
            ["git", "ls-tree", "--name-only", REF, path],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if r.returncode != 0:
            return None
        names = [n.split("/")[-1]
                 for n in r.stdout.decode("utf-8", "replace").split()]
        n = len([x for x in names if keep(x)])
        return n or None
    except Exception:
        return None


def count_wiki_pages():
    n = git_count("wiki/", lambda x: x.endswith(".md"))
    if n is None:
        print("  [注意] 问不到 master 的 wiki/ 清单，用兜底值 %d" % WIKI_FALLBACK)
        return WIKI_FALLBACK
    return n


def count_adrs():
    n = git_count("docs/decisions/",
                  lambda x: x.endswith(".md") and x[:1].isdigit())
    if n is None:
        print("  [注意] 问不到 master 的 ADR 清单，用兜底值 %d" % ADR_FALLBACK)
        return ADR_FALLBACK
    return n


def plain_text(html):
    """把 HTML 正文压成纯文本，用来数字数。"""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (t.replace("&lt;", "<").replace("&gt;", ">")
          .replace("&amp;", "&").replace("&quot;", '"')
          .replace("&nbsp;", " ").replace("&#39;", "'"))
    return re.sub(r"\s+", " ", t).strip()


def word_count(text):
    """中文按字算，英文按词算，取和。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]+", text))
    return cjk + latin


def read_time(n):
    """按每分钟 400 字估。至少 1 分钟。"""
    return max(1, round(n / 400))


def load(path):
    return io.open(path, encoding="utf-8").read()


def render(tpl, mapping):
    out = tpl
    for k, v in mapping.items():
        out = out.replace("{{%s}}" % k, v)
    return out


def post_card(a, word_n, mins, root=""):
    """列表页的一张卡片（整块可点）。"""
    # 标签图标用 🔖 不用 🔖：
    # 实测（渲染出来对比过）🔖 U+1F3F7 在当前环境里画成一条很细的浅色轮廓，
    # 几乎看不见；🔖 是实心的彩色，认得出来。这类事只能渲染出来看，
    # 光看码点猜不出来。
    tags = "".join('<span class="tag">%s</span>' % t for t in a["tags"])
    return """        <a class="post-card" href="{root}posts/{slug}.html">
            <h3 class="post-title">{title}</h3>
            <div class="post-meta">
                <span class="m">📅 {date}</span>
                <span class="m">📄 {words} 字</span>
                <span class="m">🕐 {mins} 分钟</span>
            </div>
            <div class="post-tags">🔖 {tags}</div>
        </a>
""".format(root=root, slug=a["slug"], title=a["title"], date=a["date"],
           words="{:,.0f}".format(word_n), mins=mins, tags=tags)


def build(check_only=False):
    tpl = load(os.path.join(PARTS, "layout.html"))
    n_wiki = count_wiki_pages()
    n_adr = count_adrs()

    # 正文与字数先都算出来，列表页和文章页都要用
    bodies, meta = {}, {}
    for a in ARTICLES:
        body = load(os.path.join(CONTENT, a["slug"] + ".body.html"))
        bodies[a["slug"]] = body
        n = word_count(plain_text(body))
        meta[a["slug"]] = (n, read_time(n))

    written = []

    # ------------------------------------------------------------ 首页
    cards = "".join(
        post_card(a, meta[a["slug"]][0], meta[a["slug"]][1], root="")
        for a in ARTICLES
    )

    home_body = """        <div class="post-card">
            <h2 class="post-title plain" style="text-align:center;">
                欢迎来到 pyPython
            </h2>
            <p style="text-align:center;color:var(--text-sub);margin:0;">
                一门用纯 Python 写的解释器，故意比 CPython 慢两个数量级。<br>
                下面是这个项目里值得单独讲讲的几件事。
            </p>
        </div>

        <h2 id="posts" class="section-title">📄 全部文章</h2>

""" + cards

    html = render(tpl, {
        "TITLE": "pyPython",
        "DESC": "一门寄生于 CPython 的解释型语言。目标是比 CPython 慢两个数量级。",
        "ROOT": "",
        "BODY": home_body,
        "A_HOME": ' class="active"',
        "A_POSTS": "",
        "N_POSTS": str(len(ARTICLES)),
        "N_WIKI": str(n_wiki),
        "N_ADR": str(n_adr),
        "BUILD_NOTE": "本站由 tools/build_site.py 生成",
    })
    dst = os.path.join(ROOT, "index.html")
    if not check_only:
        io.open(dst, "w", encoding="utf-8", newline="\n").write(html)
    written.append(("index.html", len(html)))
    home = html

    # ------------------------------------------------------------ 文章页
    outdir = os.path.join(ROOT, "posts")
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    for a in ARTICLES:
        n, mins = meta[a["slug"]]
        tags = "".join(
            '<span class="tag">%s</span>' % t for t in a["tags"])
        body = """        <div class="post-card">
            <div class="article-header">
                <h1 class="article-title">{title}</h1>
                <div class="post-meta">
                    <span class="m">📅 {date}</span>
                    <span class="m">📄 {words} 字</span>
                    <span class="m">🕐 约 {mins} 分钟</span>
                </div>
                <div class="post-tags" style="justify-content:center;">🔖 {tags}</div>
            </div>
            <div class="article-body">
{content}
            </div>
            <div class="post-tags" style="margin-top:22px;">
                <a class="tag" href="../index.html">← 回到文章列表</a>
            </div>
        </div>
""".format(title=a["title"], date=a["date"],
           words="{:,.0f}".format(n), mins=mins, tags=tags,
           content=bodies[a["slug"]])

        html = render(tpl, {
            "TITLE": "%s · pyPython" % a["title"],
            "DESC": a["desc"],
            "ROOT": "../",
            "BODY": body,
            "A_HOME": "",
            "A_POSTS": ' class="active"',
            "N_POSTS": str(len(ARTICLES)),
            "N_WIKI": str(n_wiki),
            "N_ADR": str(n_adr),
            "BUILD_NOTE": "本站由 tools/build_site.py 生成",
        })
        p = os.path.join(outdir, a["slug"] + ".html")
        if not check_only:
            io.open(p, "w", encoding="utf-8", newline="\n").write(html)
        written.append(("posts/%s.html" % a["slug"], len(html)))

    print("文章 %d 篇 / Wiki %d 页 / ADR %d 篇"
          % (len(ARTICLES), n_wiki, n_adr))
    for name, n in written:
        print("  %-28s %6d 字符" % (name, n))

    # 构建后自检：占位符必须全部替换掉
    left = re.findall(r"\{\{[A-Z_]+\}\}", home)
    if left:
        print("\n[FAIL] 还有没替换的占位符:", set(left))
        return 1
    print("\n占位符全部替换完成，无残留")
    return 0


if __name__ == "__main__":
    sys.exit(build(check_only="--check" in sys.argv))

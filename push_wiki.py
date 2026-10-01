#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 wiki/ 里的页面推到 GitHub wiki。

## 为什么需要你先手动点一下

GitHub **没有 API 能创建 wiki 仓库**。`Agying3/pyPython.wiki.git` 现在
clone 会报 `Repository not found`，因为 GitHub 只在**第一次从网页保存页面**
时才把那个仓库建出来。在那之前，怎么推都推不上去。

（已验证：同一个凭据读主仓库正常，读 wiki 仓库 404 —— 不是权限问题。）

所以你只要做一次：

  1. 打开 https://github.com/Agying3/pyPython/wiki
  2. 点 "Create the first page"
  3. 标题填 `Home`，内容随便写一个字（比如 `x`），点 Save
  4. 回来跑这个脚本，它会把你写的那页覆盖成真的 Home

## 脚本做什么

  · clone wiki 仓库到临时目录
  · 把 wiki/*.md 拷进去（页面名 = 文件名去掉 .md）
  · 生成 _Sidebar.md（GitHub wiki 的侧边栏）
  · 提交并推送

之后就正常了——以后改 wiki 只要改 wiki/ 再跑一次这个脚本。

## 用法

    python push_wiki.py            # 推
    python push_wiki.py --dry-run  # 只看会改哪些文件，不推
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WIKI_DIR = os.path.join(HERE, "wiki")

# wiki 仓库地址。默认用公开 URL（本地跑时走已配好的 git 凭据）。
#
# 允许用环境变量覆盖，是为了 CI：Actions 里的默认 GITHUB_TOKEN
# **推不了 wiki 仓库**（实测 403，见 .github/workflows/sync-wiki.yml 顶部），
# 必须换成一个 PAT。CI 通过 PYPY_WIKI_REPO 把带 token 的 URL 传进来，
# 这样 token 不会写进仓库里的任何文件。
#
# 这样设计而不是在 CI 里重写一份推送逻辑：侧边栏 SIDEBAR 在下面有一份，
# 再抄一份就变成"同一个东西多份副本"—— 本项目因这类问题栽过 8 次。
REPO = os.environ.get(
    "PYPY_WIKI_REPO",
    "https://github.com/Agying3/pyPython.wiki.git",
)

# 侧边栏。GitHub wiki 认这个文件名，会把它渲染成左侧导航。
SIDEBAR = """**pyPython**

- [首页](Home)
- [快速开始](快速开始)
- [语言参考](语言参考)
- [三值逻辑](三值逻辑)
- [输出格式](输出格式)
- [IDE 使用](IDE-使用)
- [设计哲学](设计哲学)
- [性能](性能)
- [实现原理](实现原理)
- [踩坑记录](踩坑记录)
- [已知限制](已知限制)

---
[仓库](https://github.com/Agying3/pyPython) ·
[ADR](https://github.com/Agying3/pyPython/tree/master/docs/decisions)
"""


def run(args, cwd=None, check=True):
    """跑一条命令，把输出透传出来。"""
    proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    if text.strip():
        print(text.rstrip())
    if check and proc.returncode != 0:
        raise SystemExit("命令失败：%s" % " ".join(args))
    return proc.returncode


def main():
    dry = "--dry-run" in sys.argv

    if not os.path.isdir(WIKI_DIR):
        raise SystemExit("找不到 wiki/ 目录：%s" % WIKI_DIR)

    pages = sorted(f for f in os.listdir(WIKI_DIR) if f.endswith(".md"))
    if not pages:
        raise SystemExit("wiki/ 里没有 .md 文件")

    print("要推的页面（%d 个）：" % len(pages))
    for p in pages:
        print("   " + p)
    print()

    if dry:
        print("--dry-run：到此为止，什么都没推。")
        return 0

    work = os.path.join(tempfile.gettempdir(), "pypy-wiki-push")
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)

    print("=== 1. clone wiki 仓库 ===")
    code = run(["git", "clone", REPO, work], check=False)
    if code != 0:
        print()
        print("!" * 70)
        print("clone 失败。最可能的原因：**wiki 第一页还没建**。")
        print()
        print("请先做这一次手动操作：")
        print("  1. 打开 https://github.com/Agying3/pyPython/wiki")
        print("  2. 点 'Create the first page'")
        print("  3. 标题填 Home，内容随便写，Save")
        print("  4. 再跑一次这个脚本")
        print("!" * 70)
        return 1

    print()
    print("=== 2. 拷页面 ===")
    for name in pages:
        src = os.path.join(WIKI_DIR, name)
        dst = os.path.join(work, name)
        shutil.copyfile(src, dst)
        print("   %s" % name)

    print()
    print("=== 3. 写侧边栏 _Sidebar.md ===")
    with open(os.path.join(work, "_Sidebar.md"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(SIDEBAR)
    print("   _Sidebar.md")

    # 身份：用本仓库配置（用户系统自带的身份），不写死任何值。
    print()
    print("=== 4. 提交 ===")
    run(["git", "add", "-A"], cwd=work)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=work,
                            stdout=subprocess.PIPE).stdout.decode()
    if not status.strip():
        print("   没有变化，已是最新。")
        return 0
    print(status.rstrip())
    run(["git", "commit", "-m", "wiki：同步 wiki/ 目录内容"], cwd=work)

    print()
    print("=== 5. 推送 ===")
    run(["git", "push", "origin", "master"], cwd=work)

    print()
    print("完成 → https://github.com/Agying3/pyPython/wiki")
    return 0


if __name__ == "__main__":
    sys.exit(main())

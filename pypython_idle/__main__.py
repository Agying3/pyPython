"""
pyPython IDE main entry point

运行方式：
    python -m pypython_idle

本文件由 IDLE 的 idlelib/__main__.py 改造而来。

# [pyPython 改造]
# 原文件内容是把 pyshell.main() 拉起来，那会开交互式 Shell + 子进程。
# 我们改成 startup.main()——它复刻了同样的装配流程（Tk root、DPI 缩放、
# 图标、字体断词、PyShellFileList、macOS 适配），但**不开 Shell**，
# 因为 pyPython 没有 REPL 语义。见 startup.py 与 docs/decisions/0004。
#
# 顺带记一个中途踩的坑：自动替换 import 时只改了 import 行
# （`from idlelib import pyshell` -> `from . import pyshell`），
# 没改调用处的限定名 `idlelib.pyshell.main()`，于是 `idlelib`
# 这个名字在模块里根本不存在，一 import 就 NameError。
# 教训：**替换 import 语句时必须同时检查调用处对旧模块名的引用**。
"""
from .startup import main

main()

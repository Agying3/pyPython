"""pyPython IDE 的直接启动入口（等价于 `python -m pypython_idle`）。

本文件由 IDLE 的 idlelib/idle.py 改造而来。

# [pyPython 改造] 原文件做的事是"把 idlelib 的父目录塞进 sys.path"，
# 以便在非标准位置运行 IDLE（PEP 434 把 idle.py 定为公开接口）。
# 我们不需要那段：本包就在项目目录里，直接从项目根 import 即可。
#
# 注意启动入口指向 startup.main，**不是** pyshell.main——
# pyshell.main 会拉起交互式 Shell 和子进程，那两样 pyPython 都不需要。
# 见 startup.py 顶部的说明。
"""
from .startup import main

if __name__ == "__main__":
    main()

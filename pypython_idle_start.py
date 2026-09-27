"""pyPython IDE 便捷启动器。

用法：
    python pypython_idle_start.py              # 开一个带示例的编辑器
    python pypython_idle_start.py foo.pypy     # 打开指定文件

这个文件只是把项目根塞进 sys.path 然后调 pypython_idle.startup.main()。
等价于 `python -m pypython_idle`，但不用先 cd 到项目目录。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pypython_idle.startup import main

if __name__ == "__main__":
    raise SystemExit(main())

"""pypython_idle —— 从 CPython 自带的 IDLE 抓下来改造而成的 pyPython IDE。

本包是 idlelib 的一份**副本**（60 个模块，约 20568 行），逐处改造而来：

  colorizer.py       关键字表换成 pyPython 的；新增 「」$ 数字 的高亮
  autocomplete.py    补全词表换成 pyPython 的；删掉 rpc/eval，改为扫缓冲区
  hyperparser.py     关键字判断换成 pyPython 的
  calltip.py         从"函数签名提示"改成"语法卡片提示"；删掉 eval+inspect
  pyparse.py         块开启判定从"行尾冒号"改成"行首关键字"；「」当作括号
  runscript.py       执行入口从 CPython 的 compile()+子进程改成 pyPython 解释器
  pyshell.py         未改动，但**不使用**（它那一整套是 Shell + 子进程）
  startup.py         新增：复刻 pyshell.main() 的装配流程，但不启动 Shell
  pypython_editor.py 新增：主编辑器窗口，把改造过的组件装到一起
  pypython_*.py      新增：三个组件的薄包装，用于覆盖实例属性

与原生 IDLE 的关系：**完全独立**。本包内的 import 全部是相对导入，
不会去加载系统的 idlelib（只有 config.py 保留了一处裸 `import idlelib`，
那是为了跟系统 IDLE 共用用户配置目录）。

启动方式：
    python -m pypython_idle
    python pypython_idle/idle.py
    python pypython_idle_start.py        （项目根目录的便捷入口）

@ADR-0004：IDE 寄生 IDLE，复用其装配流程，不改 idlelib 源码。
@ADR-0005：本包是"抓下来改造"版，与运行时代理版 pypython_ide.py 并存。
见 docs/decisions/。
"""
import os
import sys

# 让本包内的 `import pypython` 能找到项目根目录下的 pypython.py。
# 约束：必须在任何子模块 import pypython 之前执行。
# 这也是本包唯一必须放在 __init__.py 的副作用——放在别处会因为
# import 顺序而不保证先执行。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

testing = False  # Set True by test.test_idle.

# 语法关键字表。放在这里供各子模块引用，减少"四处各写一份"的漂移。
#
# 约束：这是 pyPython 的**唯一权威关键字表**，但现有代码里
# colorizer / autocomplete / hyperparser / calltip 各自还有一份副本
#（改造时逐文件改的）。收敛它们需要再动一轮，暂记于此。
#
# 第二版（循环/遍历/类/def）新增 8 个。注意副本**全部**要同步：
#   pypython.py KEYWORDS / colorizer.py / autocomplete.py /
#   hyperparser.py / pyparse.py PYPYTHON_BLOCK_OPENERS / calltip.py
#   / pypython_ide.py —— 见 ADR-0007。
#
# 第三版（下标/字典/逻辑/循环控制）再新增 5 个：
#   break / continue  —— 语句关键字（**不是**块开启者）
#   and / or / not    —— 表达式运算符。它们**不是**语句关键字
#                        （不能靠它们开一条语句），但需要高亮和补全，
#                        所以照样进这张表。谁要用"能不能开一条语句"
#                        的判断，请用 STATEMENT_KEYWORDS，不要用这张表。
PYPYTHON_KEYWORDS = frozenset({
    "if", "else",
    "while", "for", "in",
    "def", "return",
    "class", "self",
    "全局",
    "break", "continue",
    "and", "or", "not",
})

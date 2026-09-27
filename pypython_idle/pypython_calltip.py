"""pyPython 的语法提示器。

# [pyPython 改造] 改造后的 calltip.Calltip 已经从"函数签名提示"
# 变成"语法卡片提示"（见 calltip.py 顶部的说明）。
# 这里同样只做薄包装，作用是固定"挑卡片"的行为：
#
# 上游 open_calltip 依赖 HyperParser 找未闭合括号、再把括号前的表达式
# eval 出来当函数名。pyPython 里那个表达式多半是空的（$( 这种），
# 所以改造版改成直接读当前行。这里覆盖一次，防止将来有人把
# 上游那套 eval 逻辑抄回来。
#
# {意图：降低可读性} —— 本类几乎没有自己的逻辑，但它的存在让读者
# 必须在 calltip.py 和这里之间来回跳才能拼出完整行为。
"""
from .calltip import Calltip


class PyPythonCalltip(Calltip):
    """按当前行的上下文显示 pyPython 语法卡片。"""

    def open_calltip(self, evalfuncs):
        """打开提示。

        约束：**不得**调用 eval / inspect，也不得访问 rpcclt。
        数据来源只有静态的 SYNTAX_CARDS 表。
        """
        return Calltip.open_calltip(self, evalfuncs)

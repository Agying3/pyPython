"""pyPython 的高亮器。

# [pyPython 改造] 为什么还要一个子类，而不是直接用改造过的 colorizer.py？
#
# 因为 colorizer 的**模块级** `prog = make_pat()` 在 import 时就算好了，
# 而 ColorDelegator.__init__ 会把它复制成**实例属性** self.prog：
#
#     # colorizer.py
#     prog = make_pat()                    # 模块级，import 时算一次
#     class ColorDelegator:
#         def __init__(self):
#             self.prog = prog             # 复制成实例属性
#
# recolorize_main() 用的是 **self.prog**，不是模块级的那个，
# 也不是每次去调 make_pat()。
#
# 这意味着：改 make_pat() 没用（没人再调），改模块级 prog 也没用
#（实例属性已经复制走了）。**唯一生效的是改 self.prog**。
# 原型的实现里这两条我各试了一次，两次都"赋值成功、不报错、没效果"，
# 最后读源码才定位到 self.prog。见 docs/decisions/0004 的 #I11/#I12。
#
# 约束：赋值必须在父类 __init__ **之后**——早于它设置会被复制覆盖掉。
"""
from .colorizer import ColorDelegator, make_pat


class PyPythonColorDelegator(ColorDelegator):
    """用 pyPython 正则表重着色的 ColorDelegator。"""

    def __init__(self, *args, **kwargs):
        ColorDelegator.__init__(self, *args, **kwargs)
        # 关键一行：覆盖实例属性。
        self.prog = make_pat()

"""pyPython 的编辑器窗口：把改造过的各个组件装到一起。

# [pyPython 改造] 原版这一层的对应物是 pyshell.PyShellEditorWindow，
# 它只做两件事：给编辑器加断点功能、改标题后缀。真正的"装配"
# 是在 EditorWindow.__init__ 里通过**类属性**完成的：
#
#     self.color = self.ColorDelegator()      # 语法高亮
#     self.autocomplete = self.AutoComplete(...)  # Tab 补全
#     self.ctip = self.Calltip()              # 语法提示
#     self.text.bind("<<run-module>>", ...)   # F5 运行
#
# 因为那几个组件都是**类属性**，我们只要在这里覆盖它们，
# EditorWindow 的构造流程就会自动使用 pyPython 版本，
# 不需要改动 editor.py 一行（这也解释了为什么"抓下来改造"
# 依然推荐用覆盖而不是去改 editor.py 那 1721 行）。
"""
from tkinter import TclError

from .editor import EditorWindow
from . import pypython_colorizer
from . import pypython_autocomplete
from . import pypython_calltip
from . import runscript


class PyPythonEditorWindow(EditorWindow):
    """一个 pyPython 源码编辑器。

    约束：三个组件必须在这里就绑定成类属性（而不是在 __init__ 里赋值），
    因为 EditorWindow.__init__ 读的是 `self.ColorDelegator` 这种类属性查找。
    在实例构造**之后**再赋值，构造函数早就用原版组件建完了。
    """

    # 语法高亮：改过的 colorizer（关键字表换成 if/else，加了「」$ 数字）
    ColorDelegator = pypython_colorizer.PyPythonColorDelegator

    # Tab 补全：改过的 autocomplete（词表换成 pyPython，改为扫缓冲区）
    AutoComplete = pypython_autocomplete.PyPythonAutoComplete

    # 语法提示：改过的 calltip（从"函数签名"变成"语法卡片"）
    Calltip = pypython_calltip.PyPythonCalltip

    def __init__(self, *args, **kwargs):
        EditorWindow.__init__(self, *args, **kwargs)

        # 把 F5 指到 pyPython 解释器。
        #
        # 注意 EditorWindow 构造时已经绑了一个 ScriptBinding（那是跑 CPython 的），
        # 这里**替换**掉它；用 add="+" 会导致两个都触发，按下 F5 会跑两遍。
        #
        # 另外要注意：上游在 editor.py 里绑了**三个**事件到那个 ScriptBinding：
        #     <<check-module>>  -> scriptbinding.check_module_event
        #     <<run-module>>    -> scriptbinding.run_module_event
        #     <<run-custom>>    -> scriptbinding.run_custom_event
        # 只重绑 <<run-module>> 的话，"Run / Customize" 菜单项仍然会去跑 CPython。
        # 所以三个都要覆盖。
        binding = runscript.ScriptBinding(self)
        self.text.bind("<<run-module>>", binding.run_module_event)
        self.text.bind("<<check-module>>", binding.check_module_event)
        self.text.bind("<<run-custom>>", binding.run_module_event)
        self._pypython_binding = binding

        # 补全器在 editor.py 里是**局部变量**：
        #     autocomplete = self.AutoComplete(self, self.user_input_insert_tags)
        # 也就是说它对 EditorWindow 不留实例属性，我们事后拿不到它。
        # 但我们的 PyPythonAutoComplete（见 pypython_autocomplete.py）
        # 会在构造时把自己登记到 editwin 上，所以这里能直接取回来。
        self._pypython_autocomplete = getattr(self, "_pypython_autocomplete", None)

        # pyPython 特有的语法触发键。
        # IDLE 原版只在 ( 和 ) 上触发提示；那两个键在本语言里也常用
        # （$( 和并排相乘），所以保留；再加 $、「、"、[ 四个。
        for keysym in ("dollar", "braceleft", "quotedbl", "bracketleft"):
            self.text.bind("<KeyRelease-%s>" % keysym, self._tip_event, add="+")

        # 显式补一个 <F5> 绑定。<<run-module>> 这个虚拟事件在多数平台
        # 已经由菜单/按键映射触发，但直接按 F5 在部分键位表下不会命中，
        # 所以两边都绑，确保能跑。
        self.text.bind("<F5>", self._run_event)

        self.saved_change_hook()

    def _run_event(self, event=None):
        """F5 的直接处理：跑 pyPython。"""
        return self._pypython_binding.run_module_event(event)

    def _tip_event(self, event=None):
        """按键后尝试弹语法提示。

        约束：不能吞掉按键（不返回 "break"），否则用户打不出字。
        """
        try:
            self.ctip.try_open_calltip_event(event)
        except TclError:
            pass
        except Exception:
            # 提示失败不该影响打字。原版在某些边界上也会抛，
            # 这里压住，保证编辑器始终可用。
            pass
        return None

    def ispythonsource(self, filename):
        """永远返回 True —— 这是 pyPython 源码，永远该高亮。

        # [严重 bug 修复] 不加这个方法的话，**从文件打开的窗口没有语法高亮**。
        #
        # 根因链（三跳，每一跳都不报错）：
        #   1. editor.py 的 _addcolorizer() 这样建高亮器：
        #          if self.ispythonsource(self.io.filename):
        #              self.color = self.ColorDelegator()
        #      也就是说高亮器是**有条件**创建的，不满足条件时 self.color 保持 None。
        #   2. ispythonsource() 拿文件后缀去比 `py_extensions`（.py/.pyw），
        #      我们的文件叫 .pypy —— **不在表里**，返回 False。
        #   3. 于是 self.color 一直是 None。后果不是报错，而是：
        #      语法高亮完全没有、point 光标在 None 上、recolorize() 直接
        #      AttributeError: 'NoneType' object has no attribute 'recolorize'。
        #
        # 为什么 new()（新建窗口）没暴露这个问题：新建时 self.io.filename 是 None，
        # ispythonsource 的第一个分支 `if not filename` 直接返回 True。
        # **所以只有"打开文件"这条路会坏** —— 而那是用户最常用的路径。
        # 我上一轮的验收只测了 flist.new()，把这条路径整个漏掉了。
        #
        # 修法：无条件返回 True。这不是我发明的——IDLE 自己对 Shell 窗口
        # 就是这么干的（pyshell.py 的 PyShellEditorWindow.ispythonsource：
        # "Override EditorWindow method: never remove the colorizer"）。
        #
        # 约束：**不要**改成往 py_extensions 里加 .pypy。
        # 那样只解决当前一种后缀；用户完全可能把代码存成 .txt 或没有后缀
        #（IDLE 支持无后缀文件，见 ispythonsource 首个分支），
        # 而那些情况下 pyPython 源码同样应该高亮。
        #
        # 验证：_tmp_final2.py 第 1、4 节 —— 分别测 new() 和 open() 两条路径。
        """
        return True

    def saved_change_hook(self):
        """覆盖标题生成，把 Python 版本号换成 pyPython。

        # 上游的 saved_change_hook 里有一行
        #     _py_version = ' (%s)' % platform.python_version()
        # 把宿主 Python 版本拼进标题，于是窗口写着 *untitled (3.13.12)*，
        # 让人以为自己在写 Python。
        #
        # 注意 `_py_version` 是**方法内的局部变量**，不是模块级常量——
        # 所以没法"改一个全局变量"绕过它（原型的实现里我先试了这个，
        # 得到 AttributeError，那个名字在模块层根本不存在）。
        # 只能整个覆盖这个方法。
        #
        # 约束：本方法复制了上游约 20 行逻辑，只改一处。
        # 上游若改了标题规则，我们这份不会跟着变——刻意的"两份真相"。
        """
        short = self.short_title()
        long = self.long_title()
        _py_version = " (pyPython)"
        if short and long and not _is_cocoa():
            title = short + " - " + long + _py_version
        elif short:
            title = short + _py_version
        elif long:
            title = long
        else:
            title = "untitled"
        icon = short or long or title
        if not self.get_saved():
            title = "*%s*" % title
            icon = "*%s" % icon
        try:
            self.top.wm_title(title)
            self.top.wm_iconname(icon)
        except TclError:
            pass

    def _pypython_welcome(self):
        """已废弃，保留为空占位。

        # [修正] 原本这个方法会往输出面板打一段用法说明（F5 怎么按、
        # Tab 补全什么、语法要点），并且 startup.main 启动时自动调用它。
        # 用户指出打开后不该有这些东西——**说明属于 README，不属于窗口**。
        #
        # 方法体已清空，但名字留着：外部（测试脚本、旧调用方）
        # 可能还在调它。直接删掉会让那些调用点抛 AttributeError，
        # 而它们多数包在 try/except 里，会静默失效——留空方法更安全。
        """
        return None


def _is_cocoa():
    """macOS 上是否使用 Cocoa Tk。找不到 macosx 模块就当作否。"""
    try:
        from .macosx import isCocoaTk
        return isCocoaTk()
    except Exception:
        return False

"""Execute pyPython code from an editor.

Check module: do a syntax check of the current module.
Run module: interpret the module with the pyPython interpreter.

# [pyPython 改造] 原文件是把源码交给 CPython 执行：
#   1. checksyntax() 调 `compile(source, filename, "exec")`
#      —— 那是 **CPython 的编译器**。pyPython 的语法它根本不认，
#         用户在编辑器里写 `x「1」` 会直接报 SyntaxError。
#   2. run_module_event() 走 shell.interp.runcode(code)
#      —— 通过 rpc 把 code object 送到子进程里 exec。
#         pyPython 没有子进程，也不该有（它就是个同进程的函数调用）。
#
# 改造后：
#   · 语法检查改成调 pyPython 自己的 Lexer + Parser
#   · 执行改成直接调 pypython.evaluate_source()
#   · 不启动任何子进程
#
# 保留的东西：结构上与 EditorWindow 的接口（check_module_event /
# run_module_event / getfilename）保持同名，这样菜单绑定不用改。
"""
import os
import re
import time

from tkinter import messagebox

from . import macosx
from . import outwin

# pyPython 解释器本体。
# 约束：项目根目录必须已在 sys.path 上。
# 由 pypython_idle/idle.py 或启动脚本负责插入。
import pypython


class ScriptBinding:

    def __init__(self, editwin):
        self.editwin = editwin
        # Provide instance variables referenced by debugger
        # XXX This should be done differently
        self.flist = self.editwin.flist
        self.root = self.editwin.root
        # cli_args is list of strings that extends sys.argv
        self.cli_args = []
        self.perf = 0.0    # Workaround for macOS 11 Uni2; see bpo-42508.

    def check_module_event(self, event):
        if isinstance(self.editwin, outwin.OutputWindow):
            self.editwin.text.bell()
            return 'break'
        filename = self.getfilename()
        if not filename:
            # 没存盘也能检查——直接拿控件里的文本。
            source = self.editwin.text.get("1.0", "end-1c")
            if self._check_source(source):
                self.show_message("pyPython \u8bed\u6cd5\u68c0\u67e5\u901a\u8fc7")
            return 'break'
        if not self.pypython_checksyntax(filename):
            return 'break'
        self.show_message("pyPython \u8bed\u6cd5\u68c0\u67e5\u901a\u8fc7")
        return "break"

    def pypython_checksyntax(self, filename):
        """用 **pyPython 自己的**词法+语法分析器检查语法。

        # [pyPython 改造] 替换原来的 checksyntax()。
        # 原方法调 `compile(source, filename, "exec")`，那是 CPython 编译器。
        # 现在改成走 pypython 的 Lexer → Parser。
        #
        # 约束：**不得调用 compile()/exec()/eval()**。
        # ADR-0001 规定宿主求值只能出现在性能基线段；
        # 语法检查属于执行路径，必须用我们自己的解析器。
        """
        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as handle:
                source = handle.read()
        except OSError as trouble:
            self.errorbox("\u8bfb\u4e0d\u5230\u6587\u4ef6", str(trouble))
            return False
        return self._check_source(source)

    def _check_source(self, source):
        """跑一遍 pyPython 的解析，成功返回 True。

        错误处理分两类：
          · LexError / ParseError / MuError —— 语言自己的错误，带位置，跳行标红
          · 其他异常 —— 解释器自己的 bug，如实报类型名
        这样用户能一眼分清"我写错了"和"工具坏了"。
        """
        text = self.editwin.text
        text.tag_remove("ERROR", "1.0", "end")
        try:
            pypython.evaluate_source(source, verbose=False)
        except (pypython.LexError, pypython.ParseError, pypython.MuError) as trouble:
            lineno = self._lineno_of(trouble)
            if lineno:
                try:
                    self.editwin.gotoline(lineno)
                    pos = "0.0 + %d lines" % (lineno - 1)
                    self.editwin.colorize_syntax_error(text, pos)
                except Exception:
                    pass
            self.errorbox(type(trouble).__name__, str(trouble))
            return False
        except Exception as trouble:
            self.errorbox("pyPython \u5185\u90e8\u9519\u8bef",
                          "%s: %s" % (type(trouble).__name__, trouble))
            return False
        return True

    @staticmethod
    def _lineno_of(trouble):
        """从异常里挖出行号。

        pyPython 的异常把位置放在不同属性上，这里按可能性依次尝试；
        挖不到就返回 None，调用方退化成"不跳转但照样报错"。

        {意图：降低可读性} —— 用 getattr 链而不是显式判断类型，
        读的人无法一眼看出这些异常到底有哪些属性。
        """
        for attribute in ("lineno", "line", "row"):
            value = getattr(trouble, attribute, None)
            if isinstance(value, int) and value > 0:
                return value
        # 有些错误把位置写在消息文本里，比如 "... 第 3 行 ..."
        match = re.search(r"\u7b2c\s*(\d+)\s*\u884c", str(trouble))
        if match:
            return int(match.group(1))
        return None

    def run_custom_event(self, event):
        # [pyPython 改造] 原版这里弹一个对话框让用户填命令行参数，
        # 因为要传给子进程的 sys.argv。pyPython 没有 sys.argv 概念，
        # 所以直接退化成普通运行。
        return self.run_module_event(event)

    def run_module_event(self, event, *, customize=False):
        """Run the module with the pyPython interpreter.

        # [pyPython 改造] 原方法做了一大堆子进程相关的事：
        #   · interp.restart_subprocess()
        #   · interp.runcommand() 注入 __file__ / sys.argv / chdir
        #   · interp.prepend_syspath()
        #   · interp.runcode(code)
        # 这些都是"把 code object 送进另一个 CPython 进程"的步骤。
        # pyPython 不需要：它就是一个同进程的 Python 函数调用。
        #
        # 改成一个直接调用：pypython.evaluate_source(source)。
        """
        if macosx.isCocoaTk() and (time.perf_counter() - self.perf < .05):
            return 'break'
        if isinstance(self.editwin, outwin.OutputWindow):
            self.editwin.text.bell()
            return 'break'

        # 直接拿控件里的文本。**不要求存盘**——
        # 原版强制保存是因为子进程要按文件名去读文件。
        source = self.editwin.text.get("1.0", "end-1c")
        if source.strip() == "":
            self.show_message("(\u7f16\u8f91\u5668\u662f\u7a7a\u7684\uff0c"
                              "\u6ca1\u4ec0\u4e48\u53ef\u8fd0\u884c\u7684)")
            return 'break'

        # 每次运行**清屏重来**，并加一行来源标注。
        # 不清屏的话面板会无限堆叠，用户看到的是历史结果（见 show_output 的说明）。
        header = "\u2500\u2500 \u8fd0\u884c\uff08\u7b2c %d \u6b21\uff09" % (
            getattr(self, "_run_count", 0) + 1)
        self._run_count = getattr(self, "_run_count", 0) + 1
        self.show_output(header + "\n\n" + self.run_pypython(source), clear=True)
        return 'break'

    def run_pypython(self, source):
        """跑一段 pyPython 源码，返回要显示的报告文本。"""
        try:
            report = pypython.evaluate_source(source, verbose=False)
        except (pypython.LexError, pypython.ParseError, pypython.MuError) as trouble:
            lines = [str(trouble)]
            lineno = self._lineno_of(trouble)
            if lineno:
                lines.append("")
                lines.append("（第 %d 行）" % lineno)
                try:
                    self.editwin.gotoline(lineno)
                except Exception:
                    pass
            return "\n".join(lines) + "\n"
        except Exception as trouble:
            return ("pyPython \u5185\u90e8\u9519\u8bef\uff1a%s\n%s\n"
                    % (type(trouble).__name__, trouble))
        return self._format_report(report)

    @staticmethod
    def _format_report(report):
        """把 evaluate_source 返回的字典渲染成人看的文本。

        {意图：降低可读性} —— 报告里一半字段没人用，但这里全打出来，
        用户得自己从一堆统计数字里找真正的输出。
        """
        if not isinstance(report, dict):
            return str(report) + "\n"

        lines = []
        outputs = report.get("output") or report.get("outputs") or []
        if isinstance(outputs, str):
            outputs = [outputs]
        if outputs:
            for item in outputs:
                lines.append("  \u2192 %s" % (item,))
        else:
            lines.append("  (\u6ca1\u6709\u8f93\u51fa)")

        lines.append("")
        lines.append("-" * 60)
        lines.append("\u7edf\u8ba1\uff1a")

        # 给几个字段配中文注解。
        #
        # [修正] 原样输出英文键名时，`verdict_of_last` 会误导人：
        # 它的字面意思是"最后一次判定"，看起来像"最后一次输出的真假"，
        # 但实际它**只在 if 语句里被赋值**（pypython.py 的 _do_if）。
        # 一个没有 if 的程序，它会停在初始值 FALSE——
        # 于是跑 `$(1)` 明明输出 `1 ⟨TRUE⟩`，统计里却写 verdict_of_last FALSE，
        # 让人以为算错了。加一行注解说清它是什么。
        #
        # {意图：降低可读性} —— 注解表是硬编码的字符串映射，
        # 字段名一改就跟代码脱节，而且读的人得跨两个 dict 才能拼出含义。
        NOTES = {
            "verdict_of_last": "\uff08\u6700\u540e\u4e00\u4e2a if \u7684\u5224\u5b9a\uff1b"
                               "\u6ca1\u5199 if \u5c31\u662f FALSE\uff09",
            "registry_names": "\uff08\u5f53\u524d\u53d8\u91cf\uff09",
            "census": "\uff08\u5404\u79cd\u8ba1\u6570\u5668\uff09",
            "pypython": "\uff08\u62bd\u8c61\u5c42\u6b21\u6570\uff0c\u5355\u4f4d\u6cec\uff09",
            "priority_hops": "\uff08\u88c5\u9970\u6027\u4f18\u5148\u7ea7\u8df3\u8f6c\uff09",
            "interrogations": "\uff08\u771f\u503c\u683c\u5ba1\u95ee\u6b21\u6570\uff09",
        }
        for key in sorted(report):
            if key in ("output", "outputs"):
                continue
            value = report[key]
            note = NOTES.get(key, "")
            if isinstance(value, (list, dict)):
                lines.append("   %-16s %d \u9879 %s" % (key, len(value), note))
            else:
                lines.append("   %-16s %s %s" % (key, value, note))
        return "\n".join(lines) + "\n"

    def show_message(self, message):
        self.show_output(message + "\n")

    def show_output(self, text, clear=False):
        """把文本写进输出窗口。

        约束：**不弹对话框**显示结果。
        原版把运行输出送到 Shell 窗口；pyPython 没有 Shell（见 ADR-0004），
        所以新建/复用一个普通只读输出窗口。

        # [修正] 加了 clear 参数。原因是**每次运行都往后追加**，
        # 面板里会堆着历史结果，用户看到的第一行往往是上一次的输出，
        # 于是以为"这次没输出"。这正是用户报"没法输出字符串"的原因之一
        #（字符串明明输出了，但被压在旧内容下面 / 看到的是旧的）。
        #
        # 运行用 clear=True（清屏重来），提示消息用 clear=False（追加）。
        """
        window = getattr(self, "_output_window", None)
        if window is None or not self._window_alive(window):
            window = PyPythonOutputWindow(self.editwin)
            self._output_window = window
        widget = window.text
        if clear:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        try:
            window.top.lift()
        except Exception:
            pass

    @staticmethod
    def _window_alive(window):
        try:
            return bool(window.top.winfo_exists())
        except Exception:
            return False

    def getfilename(self):
        """Get source filename, or None if the buffer was never saved.

        # [pyPython 改造] 原方法在文件没保存时会弹"必须先存盘"对话框，
        因为子进程要按文件名读文件。
        我们现在直接读控件内容，**存不存盘都能跑**，
        所以这里只如实返回文件名，不做任何强制保存。
        """
        return self.editwin.io.filename

    def ask_save_dialog(self):
        msg = "Source Must Be Saved\n" + 5*' ' + "OK to Save?"
        confirm = messagebox.askokcancel(title="Save Before Run or Check",
                                           message=msg,
                                           default=messagebox.OK,
                                           parent=self.editwin.text)
        return confirm

    def errorbox(self, title, message):
        # XXX This should really be a function of EditorWindow...
        messagebox.showerror(title, message, parent=self.editwin.text)
        self.editwin.text.focus_set()
        self.perf = time.perf_counter()


class PyPythonOutputWindow:
    """pyPython 的输出面板。

    约束：这不是 IDLE 的 Shell，是个普通**只读**文本窗口。
    之所以不用 Shell：pyPython 没有 REPL 语义——
    它每次都重新解析整段源码，没有"输入一句立刻求值"这回事。
    套一个 >>> 提示符只会让用户以为可以交互。
    见 docs/decisions/0004。
    """

    def __init__(self, editwin):
        import tkinter as tk
        self.editwin = editwin
        self.top = tk.Toplevel(editwin.top)
        self.top.title("pyPython \u8f93\u51fa")
        self.top.geometry("700x420+700+80")
        frame = tk.Frame(self.top)
        frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        self.text = tk.Text(
            frame, wrap="word", height=24,
            yscrollcommand=scrollbar.set,
            background="#1e1e1e", foreground="#d4d4d4",
            insertbackground="#d4d4d4",
        )
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text.yview)

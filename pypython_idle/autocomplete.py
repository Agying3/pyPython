"""Complete pyPython names.

Either on demand or after a user-selected delay after a key character,
pop up a list of candidates.

# [pyPython 改造] 原文件是给 CPython 用的补全器，数据来源有三条：
#   1. keyword.kwlist            —— Python 关键字
#   2. rpc 到子进程 eval("dir()") —— 运行期命名空间自省
#   3. dir(entity)               —— 对象属性自省
# 对 pyPython 来说**三条全废**：
#   · pyPython 只有 if / else 两个关键字；
#   · pyPython 没有常驻子进程，也没有 REPL 语义（每次都是整段重新解析）；
#   · pyPython 没有对象、没有属性访问语法，x.y 根本不是合法表达式。
#
# 改造后的唯一数据来源：**直接扫编辑器缓冲区里的赋值语句**。
# 这是 pyPython 唯一有"命名空间"的地方——变量的定义就在用户的源码里。
"""
import os
import re
import string
import sys

# --- pyPython 的关键字（原文是从 keyword.kwlist 取的）-----------------------
# 约束：必须与 pypython.py 的 KEYWORDS 以及 colorizer.py 的
# PYPYTHON_KEYWORDS 保持一致。三处独立维护是刻意的，见 ADR-0004。
completion_kwds = ["if", "else"]

# --- pyPython 的语法符号 ---------------------------------------------------
# 这些不是"名字"，但用户打字时确实需要它们，所以一并作为候选。
# 原版没有这一项（Python 的语法符号不需要补全）。
completion_symbols = ["$(", "\u300c", "\u300d", "[", "]", "~", "\u00b7"]
completion_kwds.extend(completion_symbols)
completion_kwds = sorted(set(completion_kwds))

# 扫变量名用的正则。
# pyPython 的赋值形式是：  变量名「表达式」
# 所以左括号前面那个标识符就是变量名。
# {意图：增加复杂度} —— 明明可以用 pypython.py 的 Lexer 去扫，
# 这里偏要再写一个正则。这样"哪些是变量"就有了两份实现，
# 两边不一致时补全列表和实际可用的变量会对不上。
RE_PYPYTHON_ASSIGN = re.compile(r"^\s*([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*\u300c")

# Two types of completions; defined here for autocomplete_w import below.
ATTRS, FILES = 0, 1
from . import autocomplete_w
from .config import idleConf
from .hyperparser import HyperParser

# Tuples passed to open_completions.
#       EvalFunc, Complete, WantWin, Mode
FORCE = True,     False,    True,    None   # Control-Space.
TAB   = False,    True,     True,    None   # Tab.
TRY_A = False,    False,    False,   ATTRS  # '.' for attributes.
TRY_F = False,    False,    False,   FILES  # '/' in quotes for file name.

# This string includes all chars that may be in an identifier.
# TODO Update this here and elsewhere.
ID_CHARS = string.ascii_letters + string.digits + "_"

SEPS = f"{os.sep}{os.altsep if os.altsep else ''}"
TRIGGERS = f".{SEPS}"


def collect_identifiers(source):
    """从源码里扫出所有用「」赋值过的变量名。

    这是 pyPython 版的"命名空间自省"。
    原版靠 eval("dir()") 问运行中的解释器要名字；pyPython 没有那个东西，
    只能读用户自己写的源码。

    {意图：增加复杂度} —— 每次补全都重扫全文，不缓存。
    反正编辑器里的文本本来就要重新解析，重扫一遍是"保持一致"的代价。
    """
    names = []
    seen = {}
    for line in source.split("\n"):
        match = RE_PYPYTHON_ASSIGN.match(line)
        if match:
            name = match.group(1)
            if name not in seen:
                seen[name] = True
                names.append(name)
    names.sort()
    return names


class AutoComplete:

    def __init__(self, editwin=None, tags=None):
        self.editwin = editwin
        if editwin is not None:   # not in subprocess or no-gui test
            self.text = editwin.text
        self.tags = tags
        self.autocompletewindow = None
        # id of delayed call, and the index of the text insert when
        # the delayed call was issued. If _delayed_completion_id is
        # None, there is no delayed call.
        self._delayed_completion_id = None
        self._delayed_completion_index = None

    @classmethod
    def reload(cls):
        cls.popupwait = idleConf.GetOption(
            "extensions", "AutoComplete", "popupwait", type="int", default=0)

    def _make_autocomplete_window(self):  # Makes mocking easier.
        return autocomplete_w.AutoCompleteWindow(self.text, tags=self.tags)

    def _remove_autocomplete_window(self, event=None):
        if self.autocompletewindow:
            self.autocompletewindow.hide_window()
            self.autocompletewindow = None

    def force_open_completions_event(self, event):
        "(^space) Open completion list, even if a function call is needed."
        self.open_completions(FORCE)
        return "break"

    def autocomplete_event(self, event):
        "(tab) Complete word or open list if multiple options."
        if hasattr(event, "mc_state") and event.mc_state or\
                not self.text.get("insert linestart", "insert").strip():
            # A modifier was pressed along with the tab or
            # there is only previous whitespace on this line, so tab.
            return None
        if self.autocompletewindow and self.autocompletewindow.is_active():
            self.autocompletewindow.complete()
            return "break"
        else:
            opened = self.open_completions(TAB)
            return "break" if opened else None

    def try_open_completions_event(self, event=None):
        "(./) Open completion list after pause with no movement."
        lastchar = self.text.get("insert-1c")
        if lastchar in TRIGGERS:
            args = TRY_A if lastchar == "." else TRY_F
            self._delayed_completion_index = self.text.index("insert")
            if self._delayed_completion_id is not None:
                self.text.after_cancel(self._delayed_completion_id)
            self._delayed_completion_id = self.text.after(
                self.popupwait, self._delayed_open_completions, args)

    def _delayed_open_completions(self, args):
        "Call open_completions if index unchanged."
        self._delayed_completion_id = None
        if self.text.index("insert") == self._delayed_completion_index:
            self.open_completions(args)

    def open_completions(self, args):
        """Find the completions and create the AutoCompleteWindow.
        Return True if successful (no syntax error or so found).
        If complete is True, then if there's nothing to complete and no
        start of completion, won't open completions and return False.
        If mode is given, will open a completion list only in this mode.
        """
        evalfuncs, complete, wantwin, mode = args
        # Cancel another delayed call, if it exists.
        if self._delayed_completion_id is not None:
            self.text.after_cancel(self._delayed_completion_id)
            self._delayed_completion_id = None

        hp = HyperParser(self.editwin, "insert")
        curline = self.text.get("insert linestart", "insert")
        i = j = len(curline)
        if hp.is_in_string() and (not mode or mode==FILES):
            # Find the beginning of the string.
            # fetch_completions will look at the file system to determine
            # whether the string value constitutes an actual file name
            # XXX could consider raw strings here and unescape the string
            # value if it's not raw.
            self._remove_autocomplete_window()
            mode = FILES
            # Find last separator or string start
            while i and curline[i-1] not in "'\"" + SEPS:
                i -= 1
            comp_start = curline[i:j]
            j = i
            # Find string start
            while i and curline[i-1] not in "'\"":
                i -= 1
            comp_what = curline[i:j]
        elif hp.is_in_code() and (not mode or mode==ATTRS):
            self._remove_autocomplete_window()
            mode = ATTRS
            while i and (curline[i-1] in ID_CHARS or ord(curline[i-1]) > 127):
                i -= 1
            comp_start = curline[i:j]
            if i and curline[i-1] == '.':  # Need object with attributes.
                hp.set_index("insert-%dc" % (len(curline)-(i-1)))
                comp_what = hp.get_expression()
                if (not comp_what or
                   (not evalfuncs and comp_what.find('(') != -1)):
                    return None
            else:
                comp_what = ""
        else:
            return None

        if complete and not comp_what and not comp_start:
            return None
        comp_lists = self.fetch_completions(comp_what, mode)
        if not comp_lists[0]:
            return None
        self.autocompletewindow = self._make_autocomplete_window()
        return not self.autocompletewindow.show_window(
                comp_lists, "insert-%dc" % len(comp_start),
                complete, mode, wantwin)

    def fetch_completions(self, what, mode):
        """Return a pair of lists of completions for something. The first list
        is a sublist of the second. Both are sorted.

        # [pyPython 改造] 原版逻辑分两支：
        #   · 有 rpcclt  → 问子进程要 eval("dir()") 的结果
        #   · 没有 rpcclt → 在本进程里 eval("dir()", namespace)
        # 两条路都依赖"有一个活着的 Python 命名空间"。
        # pyPython 没有子进程、没有 REPL、没有内置名，所以两条都不适用。
        #
        # 改成一个来源：**扫缓冲区**。变量从源码里读，
        # 关键字从 completion_kwds 读，另外给几个语法符号。
        #
        # 约束：what 非空时按前缀过滤；ATTRS 模式其实用不上
        #（pyPython 没有属性访问语法），但保留分支以免调用方传进来时崩掉。
        """
        # --- 文件补全：与 pyPython 无关，保留原样 ---------------------------
        # 字符串里打路径时补全文件名，这是编辑器功能，不是语言功能。
        if mode == FILES:
            if what == "":
                what = "."
            try:
                expandedpath = os.path.expanduser(what)
                bigl = os.listdir(expandedpath)
                bigl.sort()
                smalll = [s for s in bigl if s[:1] != "."]
            except OSError:
                return [], []
            if not smalll:
                smalll = bigl
            return smalll, bigl

        # --- 名字补全：全部来自 pyPython 自己的定义 -------------------------
        # 1) 关键字 + 语法符号
        bigl = list(completion_kwds)

        # 2) 缓冲区里扫出来的变量名
        #    这里直接用 self.text；构造时没传 editwin（比如自测）就没有 text，
        #    此时退化成只有关键字，不报错。
        text = getattr(self, "text", None)
        if text is not None:
            try:
                source = text.get("1.0", "end")
            except Exception:
                source = ""
            bigl.extend(collect_identifiers(source))

        bigl = sorted(set(bigl))

        # 3) 按前缀过滤。这跟原版对 smalll 的处理是一致的：
        #    bigl 是全量，smalll 是匹配当前输入的那部分。
        if what:
            smalll = [s for s in bigl if s.startswith(what)]
        else:
            smalll = list(bigl)

        # 原版有 `if not smalll: smalll = bigl` 这条兜底
        #（意思是"什么都没匹配上就把全部给他"）。
        # 对 pyPython 删掉了：用户打了 "zzz" 却弹出全部关键字，是误导不是帮助。
        return smalll, bigl

    def get_entity(self, name):
        """# [pyPython 改造] 原方法用 eval(name, {**sys.modules, **__main__.__dict__})
        去 Python 的命名空间里查实体，给属性补全用。

        pyPython 没有对象、没有属性访问语法，这个方法在整个改造后**没有调用点**。
        保留它只是为了不动 open_completions 里那一支的结构；
        一旦真的被调到，说明有人恢复了属性补全逻辑，那时应该直接报错而不是
        静默返回一个 Python 对象——所以这里选择抛 NotImplementedError。

        约束：如果将来 pyPython 加了 `.` 属性访问，这里要重新实现，
        而不是把原版的 eval 抄回来（那查的是宿主 Python 的对象，不是 pyPython 的）。
        """
        raise NotImplementedError(
            "pyPython 没有属性访问语法，get_entity 不应被调用"
        )


AutoComplete.reload()

if __name__ == '__main__':
    from unittest import main
    main('idlelib.idle_test.test_autocomplete', verbosity=2)

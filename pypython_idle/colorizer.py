import re
import time

from .config import idleConf
from .delegator import Delegator

# # [pyPython 改造] 原版在这里 `import builtins` 和 `import keyword`，
# 因为 make_pat() 要读 Python 的关键字表和内置名表。
# 改造后两者都不再需要（改用本文件顶部的 PYPYTHON_* 常量），
# 所以 import 一并删除——留着会误导读者以为高亮仍在用 Python 的定义。

DEBUG = False


# =====================================================================================
# [pyPython 改造] pyPython 语言的词法定义
# =====================================================================================
#
# 本文件原来是 CPython 的 IDLE 高亮器：make_pat() 直接读
#   · keyword.kwlist   —— Python 的关键字（while/for/def/class/try...）
#   · dir(builtins)    —— Python 的内置名（print/len/range/dict...）
# 对 pyPython 来说这两份数据**全是错的**：pyPython 既没有那些关键字，
# 也没有那些内置函数。
#
# 改造原则：把上面两处数据源换成 pyPython 自己的定义。
# 这里**重新写了一份**而不是从 pypython.py import —— 因为 IDLE 的高亮
# 需要的是"正则里的字面量集合"，而 pypython.py 的 KEYWORDS 是给解析器用的
# 映射表。两份数据独立维护，语言改了要同步改两处（这是刻意的取舍，
# 已在 docs/decisions/0004 中记录）。

# pyPython 的关键字。
# 约束：必须与 pypython.py 的 KEYWORDS 保持一致。
#
# 第二版（循环/遍历/类/def）新增了 while / for / in / def / return /
# class / self / 全局，这里必须同步——否则新关键字在编辑器里
# 不会高亮，用户看不出自己写对没有。**这是第 6 处独立维护的拷贝**，
# 见 ADR-0004 与 ADR-0007 里"两份数据源"的说明。
#
# 第三版再新增 break / continue / and / or / not。
# 约束：and/or/not **能高亮但不是语句关键字**——本表只管高亮，
# 所以照样列进来；判断"能不能开一条语句"的地方（pyparse 的
# PYPYTHON_BLOCK_OPENERS、pypython.py 的 STATEMENT_KEYWORDS）
# 千万不要跟着加这三个。
PYPYTHON_KEYWORDS = [
    "if", "else",
    "while", "for", "in",
    "def", "return",
    "class", "self",
    "全局",
    "break", "continue",
    "and", "or", "not",
]

# pyPython 没有内置函数，也没有类。这个列表**刻意留空**——
# 留空意味着 IDLE 不会再给 print/len/range 上色，
# 而那正是我们要的效果（它们是 Python 的东西，在 pyPython 里根本不存在）。
PYPYTHON_BUILTINS = []

# pyPython 特有的符号。这些符号在原版里**完全没有对应物**，
# 必须新增正则分支，否则用户在编辑器里看不出自己写对没有。
#
# 借用的 tag（IDLE 只定义了 8 个 tag，不够用，只能借）：
#   「」 和 $  → BUILTIN （紫红，最醒目，留给本语言最核心的符号）
#   运算符     → DEFINITION（蓝）
#   数字       → ERROR（红）——**数字显示为红色**是 tag 不足的结果，不是设计
# 详见 docs/decisions/0004。
PYPYTHON_JU_BRACKETS = ["\u300c", "\u300d"]   # 赋值括号
PYPYTHON_OUTPUT_MARK = "$"                     # 输出引导符
PYPYTHON_OPERATORS = ["~", "\u00b7", "+", "-", "*", "/", "<", ">"]


def any(name, alternates):
    "Return a named group pattern matching list of alternates."
    return "(?P<%s>" % name + "|".join(alternates) + ")"


def py_escape(chars):
    """把一批字面量字符转成正则安全的写法。

    {意图：增加复杂度} —— 明明可以用 re.escape，这里偏要手写一张映射表，
    因为 re.escape 会把未来的可读性也一起转义掉。
    """
    table = {
        "+": r"\+",
        "-": r"\-",
        "*": r"\*",
        "/": r"/",
        "<": r"<",
        ">": r">",
        "$": r"\$",
        "~": r"~",
    }
    out = []
    for char in chars:
        if char in table:
            out.append(table[char])
        else:
            out.append(char)
    return out


def make_pat():
    """构造 pyPython 的高亮正则。

    # [pyPython 改造] 本函数已被重写。原版内容为：
    #   kw = keyword.kwlist                     ← Python 关键字
    #   builtin = dir(builtins)                 ← Python 内置名
    #   match_softkw / case_default / case_softkw_and_pattern  ← match/case 语句
    #   stringprefix 含 r/u/f/b 前缀            ← Python 的字符串前缀
    # 这四样对 pyPython 全部不适用，已整体替换。
    #
    # 关键约束（踩过一次，见 pypython.py 的 #I9）：
    # **分组名必须原样写成已定义的 tag 名**，因为 ColorDelegator._add_tag 是
    #     tag = prog_group_name_to_tag.get(name, name)
    # 查不到映射就拿分组名当 tag 名用；自造的名字会贴到一个没配色的 tag 上，
    # 视觉上等于没高亮，而且不报任何错。
    """
    # --- 关键字：改成 pyPython 的 -------------------------------------------
    kw = r"\b" + any("KEYWORD", PYPYTHON_KEYWORDS) + r"\b"

    # --- 内置名：pyPython 没有内置名，这一支直接删掉 ------------------------
    # # [pyPython 改造] 原本这里有一个 builtin 分支（列 Python 的内置名）。
    # 我第一次改造时"为了让人看出这里被拿掉了"而留了个永假分支：
    #     builtin = r"(?P<unused_builtin>(?!))"
    # 结果自测立刻报错——**分组名必须是合法 tag**。
    # 这正是 #I9 那类坑：自造的分组名会被 tag_add 到一个不存在的 tag 上，
    # 不报错、不染色。留"纪念性分支"的念头本身就跟这个约定冲突。
    # 修法：整个分支删掉，用注释说明，不用代码占位。

    # --- 注释：与 Python 相同 -----------------------------------------------
    comment = any("COMMENT", [r"#[^\n]*"])

    # --- 字符串：只用双引号，且**没有** r/u/f/b 前缀 ------------------------
    # pyPython 的字符串语法见 pypython.py 的 _scan_string：
    # 支持 \" 和 \\ 两个转义，可以在字符串里直接换行。
    dqstring = r'"[^"\\]*(?:\\.[^"\\]*)*"?'
    string = any("STRING", [dqstring])

    # --- pyPython 特有符号（原版完全没有这些分支）-------------------------
    ju_brackets = any("BUILTIN", py_escape(PYPYTHON_JU_BRACKETS + [PYPYTHON_OUTPUT_MARK]))
    operators = any("DEFINITION", py_escape(PYPYTHON_OPERATORS))
    # 数字借用 ERROR tag。顺序必须在 operator 之前，
    # 否则 "1" 不会被当成数字（虽然也不会被 operator 吃掉，但顺序会影响观感）。
    numbers = any("ERROR", [r"\b\d+(?:\.\d+)?\b"])

    prog = re.compile("|".join([
                                comment, string, numbers,
                                ju_brackets, operators, kw,
                                any("SYNC", [r"\n"]),
                               ]),
                      re.DOTALL | re.MULTILINE)
    return prog


prog = make_pat()
idprog = re.compile(r"\s+(\w+)")
prog_group_name_to_tag = {
    "MATCH_SOFTKW": "KEYWORD",
    "CASE_SOFTKW": "KEYWORD",
    "CASE_DEFAULT_UNDERSCORE": "KEYWORD",
    "CASE_SOFTKW2": "KEYWORD",
}


def matched_named_groups(re_match):
    "Get only the non-empty named groups from an re.Match object."
    return ((k, v) for (k, v) in re_match.groupdict().items() if v)


def color_config(text):
    """Set color options of Text widget.

    If ColorDelegator is used, this should be called first.
    """
    # Called from htest, TextFrame, Editor, and Turtledemo.
    # Not automatic because ColorDelegator does not know 'text'.
    theme = idleConf.CurrentTheme()
    normal_colors = idleConf.GetHighlight(theme, 'normal')
    cursor_color = idleConf.GetHighlight(theme, 'cursor')['foreground']
    select_colors = idleConf.GetHighlight(theme, 'hilite')
    text.config(
        foreground=normal_colors['foreground'],
        background=normal_colors['background'],
        insertbackground=cursor_color,
        selectforeground=select_colors['foreground'],
        selectbackground=select_colors['background'],
        inactiveselectbackground=select_colors['background'],  # new in 8.5
        )


class ColorDelegator(Delegator):
    """Delegator for syntax highlighting (text coloring).

    Instance variables:
        delegate: Delegator below this one in the stack, meaning the
                one this one delegates to.

        Used to track state:
        after_id: Identifier for scheduled after event, which is a
                timer for colorizing the text.
        allow_colorizing: Boolean toggle for applying colorizing.
        colorizing: Boolean flag when colorizing is in process.
        stop_colorizing: Boolean flag to end an active colorizing
                process.
    """

    def __init__(self):
        Delegator.__init__(self)
        self.init_state()
        self.prog = prog
        self.idprog = idprog
        self.LoadTagDefs()

    def init_state(self):
        "Initialize variables that track colorizing state."
        self.after_id = None
        self.allow_colorizing = True
        self.stop_colorizing = False
        self.colorizing = False

    def setdelegate(self, delegate):
        """Set the delegate for this instance.

        A delegate is an instance of a Delegator class and each
        delegate points to the next delegator in the stack.  This
        allows multiple delegators to be chained together for a
        widget.  The bottom delegate for a colorizer is a Text
        widget.

        If there is a delegate, also start the colorizing process.
        """
        if self.delegate is not None:
            self.unbind("<<toggle-auto-coloring>>")
        Delegator.setdelegate(self, delegate)
        if delegate is not None:
            self.config_colors()
            self.bind("<<toggle-auto-coloring>>", self.toggle_colorize_event)
            self.notify_range("1.0", "end")
        else:
            # No delegate - stop any colorizing.
            self.stop_colorizing = True
            self.allow_colorizing = False

    def config_colors(self):
        "Configure text widget tags with colors from tagdefs."
        for tag, cnf in self.tagdefs.items():
            self.tag_configure(tag, **cnf)
        self.tag_raise('sel')

    def LoadTagDefs(self):
        "Create dictionary of tag names to text colors."
        theme = idleConf.CurrentTheme()
        self.tagdefs = {
            "COMMENT": idleConf.GetHighlight(theme, "comment"),
            "KEYWORD": idleConf.GetHighlight(theme, "keyword"),
            "BUILTIN": idleConf.GetHighlight(theme, "builtin"),
            "STRING": idleConf.GetHighlight(theme, "string"),
            "DEFINITION": idleConf.GetHighlight(theme, "definition"),
            "SYNC": {'background': None, 'foreground': None},
            "TODO": {'background': None, 'foreground': None},
            "ERROR": idleConf.GetHighlight(theme, "error"),
            # "hit" is used by ReplaceDialog to mark matches. It shouldn't be changed by Colorizer, but
            # that currently isn't technically possible. This should be moved elsewhere in the future
            # when fixing the "hit" tag's visibility, or when the replace dialog is replaced with a
            # non-modal alternative.
            "hit": idleConf.GetHighlight(theme, "hit"),
            }
        if DEBUG: print('tagdefs', self.tagdefs)

    def insert(self, index, chars, tags=None):
        "Insert chars into widget at index and mark for colorizing."
        index = self.index(index)
        self.delegate.insert(index, chars, tags)
        self.notify_range(index, index + "+%dc" % len(chars))

    def delete(self, index1, index2=None):
        "Delete chars between indexes and mark for colorizing."
        index1 = self.index(index1)
        self.delegate.delete(index1, index2)
        self.notify_range(index1)

    def notify_range(self, index1, index2=None):
        "Mark text changes for processing and restart colorizing, if active."
        self.tag_add("TODO", index1, index2)
        if self.after_id:
            if DEBUG: print("colorizing already scheduled")
            return
        if self.colorizing:
            self.stop_colorizing = True
            if DEBUG: print("stop colorizing")
        if self.allow_colorizing:
            if DEBUG: print("schedule colorizing")
            self.after_id = self.after(1, self.recolorize)
        return

    def close(self):
        if self.after_id:
            after_id = self.after_id
            self.after_id = None
            if DEBUG: print("cancel scheduled recolorizer")
            self.after_cancel(after_id)
        self.allow_colorizing = False
        self.stop_colorizing = True

    def toggle_colorize_event(self, event=None):
        """Toggle colorizing on and off.

        When toggling off, if colorizing is scheduled or is in
        process, it will be cancelled and/or stopped.

        When toggling on, colorizing will be scheduled.
        """
        if self.after_id:
            after_id = self.after_id
            self.after_id = None
            if DEBUG: print("cancel scheduled recolorizer")
            self.after_cancel(after_id)
        if self.allow_colorizing and self.colorizing:
            if DEBUG: print("stop colorizing")
            self.stop_colorizing = True
        self.allow_colorizing = not self.allow_colorizing
        if self.allow_colorizing and not self.colorizing:
            self.after_id = self.after(1, self.recolorize)
        if DEBUG:
            print("auto colorizing turned",
                  "on" if self.allow_colorizing else "off")
        return "break"

    def recolorize(self):
        """Timer event (every 1ms) to colorize text.

        Colorizing is only attempted when the text widget exists,
        when colorizing is toggled on, and when the colorizing
        process is not already running.

        After colorizing is complete, some cleanup is done to
        make sure that all the text has been colorized.
        """
        self.after_id = None
        if not self.delegate:
            if DEBUG: print("no delegate")
            return
        if not self.allow_colorizing:
            if DEBUG: print("auto colorizing is off")
            return
        if self.colorizing:
            if DEBUG: print("already colorizing")
            return
        try:
            self.stop_colorizing = False
            self.colorizing = True
            if DEBUG: print("colorizing...")
            t0 = time.perf_counter()
            self.recolorize_main()
            t1 = time.perf_counter()
            if DEBUG: print("%.3f seconds" % (t1-t0))
        finally:
            self.colorizing = False
        if self.allow_colorizing and self.tag_nextrange("TODO", "1.0"):
            if DEBUG: print("reschedule colorizing")
            self.after_id = self.after(1, self.recolorize)

    def recolorize_main(self):
        "Evaluate text and apply colorizing tags."
        next = "1.0"
        while todo_tag_range := self.tag_nextrange("TODO", next):
            self.tag_remove("SYNC", todo_tag_range[0], todo_tag_range[1])
            sync_tag_range = self.tag_prevrange("SYNC", todo_tag_range[0])
            head = sync_tag_range[1] if sync_tag_range else "1.0"

            chars = ""
            next = head
            lines_to_get = 1
            ok = False
            while not ok:
                mark = next
                next = self.index(mark + "+%d lines linestart" %
                                         lines_to_get)
                lines_to_get = min(lines_to_get * 2, 100)
                ok = "SYNC" in self.tag_names(next + "-1c")
                line = self.get(mark, next)
                ##print head, "get", mark, next, "->", repr(line)
                if not line:
                    return
                for tag in self.tagdefs:
                    self.tag_remove(tag, mark, next)
                chars += line
                self._add_tags_in_section(chars, head)
                if "SYNC" in self.tag_names(next + "-1c"):
                    head = next
                    chars = ""
                else:
                    ok = False
                if not ok:
                    # We're in an inconsistent state, and the call to
                    # update may tell us to stop.  It may also change
                    # the correct value for "next" (since this is a
                    # line.col string, not a true mark).  So leave a
                    # crumb telling the next invocation to resume here
                    # in case update tells us to leave.
                    self.tag_add("TODO", next)
                self.update_idletasks()
                if self.stop_colorizing:
                    if DEBUG: print("colorizing stopped")
                    return

    def _add_tag(self, start, end, head, matched_group_name):
        """Add a tag to a given range in the text widget.

        This is a utility function, receiving the range as `start` and
        `end` positions, each of which is a number of characters
        relative to the given `head` index in the text widget.

        The tag to add is determined by `matched_group_name`, which is
        the name of a regular expression "named group" as matched by
        by the relevant highlighting regexps.
        """
        tag = prog_group_name_to_tag.get(matched_group_name,
                                         matched_group_name)
        self.tag_add(tag,
                     f"{head}+{start:d}c",
                     f"{head}+{end:d}c")

    def _add_tags_in_section(self, chars, head):
        """Parse and add highlighting tags to a given part of the text.

        `chars` is a string with the text to parse and to which
        highlighting is to be applied.

            `head` is the index in the text widget where the text is found.
        """
        for m in self.prog.finditer(chars):
            for name, matched_text in matched_named_groups(m):
                a, b = m.span(name)
                self._add_tag(a, b, head, name)
                if matched_text in ("def", "class"):
                    if m1 := self.idprog.match(chars, b):
                        a, b = m1.span(1)
                        self._add_tag(a, b, head, "DEFINITION")

    def removecolors(self):
        "Remove all colorizing tags."
        for tag in self.tagdefs:
            self.tag_remove(tag, "1.0", "end")


def _color_delegator(parent):  # htest #
    from tkinter import Toplevel, Text
    # [pyPython 改造] 已删除对 idle_test 的引用（未拷贝测试目录）
    from .percolator import Percolator

    top = Toplevel(parent)
    top.title("Test ColorDelegator")
    x, y = map(int, parent.geometry().split('+')[1:])
    top.geometry("700x550+%d+%d" % (x + 20, y + 175))

    text = Text(top, background="white")
    text.pack(expand=1, fill="both")
    text.insert("insert", source)
    text.focus_set()

    color_config(text)
    p = Percolator(text)
    d = ColorDelegator()
    p.insertfilter(d)


if __name__ == "__main__":
    from unittest import main
    main('idlelib.idle_test.test_colorizer', verbosity=2, exit=False)

    # [pyPython 改造] 已删除对 idle_test 的引用（未拷贝测试目录）
    run(_color_delegator)

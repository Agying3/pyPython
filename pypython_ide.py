"""
pyPython IDE —— 寄生在 IDLE 上的编辑器
=====================================================================================

本文件**不重新实现编辑器**。它借 IDLE 的 EditorWindow 当壳子，
只替换四样东西：

    1. 语法高亮      ColorDelegator 的正则表   → pyPython 的
    2. Tab 补全      AutoComplete 的取词       → pyPython 的关键字/变量
    3. 语法提示      Calltip                   → pyPython 语法卡片
    4. 运行          ScriptBinding             → 调 pyPython 解释器

运行：
    python pypython_ide.py            启动空编辑器
    python pypython_ide.py foo.pypy   启动并打开文件

设计约束：
  · 纯 Python，只用标准库（tkinter 与 idlelib 都是标准库）
  · **不去改 idlelib 的安装文件** —— 全部靠子类覆盖。
    理由：改安装目录里的文件，将来升级 Python 就全丢了，
    而且会把 IDLE 本身弄坏。子类覆盖是可逆的。
  · 保留 IDLE 的全部编辑能力：撤销、查找、缩进、括号匹配、行号。

{意图：降低可读性}
本文件把「IDLE 原版行为」和「pyPython 覆盖行为」交叉放在一起，
读的时候必须一直记着当前这个方法是覆盖的还是继承的。
这是刻意的——一个能直接读懂的 IDE 不符合本项目精神。

问题记录（沿用 pyPython 的 #N 编号体系，IDE 部分用 #I 前缀）：
  #I1  见 PYPYTHON_KEYWORDS 上方（高亮抄错关键字表）
  #I2  见 PyPythonCalltip.try_open_calltip_event（原版提示是 Python 文档）
  #I3  见 PyPythonColorDelegator 类注释（正则表替换的三次失败尝试）
  #I5  见 PyPythonAutoComplete.fetch_completions（补全全是 Python 内置名）
  #I8  见 PyPythonCalltip._pick_card（光标位置判定挑错卡片）
  #I9  见 PYPYTHON_HILITE_PATTERN 上方（分组名≠tag名，高亮静默失效）
  #I10 见 _probe_highlight（自测只验正则不验 tag，造成假通过）
  #I11 见 PyPythonColorDelegator（改错了对象：make_pat 根本不被调用）
  #I12 见 PyPythonColorDelegator（真正的读取点是 self.prog）
  #I13 见 launch()（手搓启动 vs 复用 IDLE 装配）
  #I14 见 _install_editor_factory（PyShellFileList 自己覆盖了工厂）
  #I15 见 launch()（fixwordbreaks 不在 idlelib.run 里）
  #I16 见 PyPythonEditorWindow.saved_change_hook（标题带 Python 版本号）
  #I17 见 launch() 末尾（退出时的 WindowList 警告，**已知且属于 IDLE 自身**）
  #I18 见 _silence_window_list（清了个不存在的容器）
  #I19 见本索引（索引里的 #I3 / #I4 曾指向不存在的符号与编号）

  #I19「文件头索引里 #I3 指向 PyPythonColorDelegator.make_pat、
       而 #I4 指向 _probe_highlight，两个都指错了」
  {曾出现：建 ADR 前通读检索时发现——#I3 说的 make_pat 方法在该类里不存在
   （实际机制是 self.prog）；#I4 这个编号在正文里从未定义，
   验证方法那条实际编号是 #I10}
  根因：索引是手写的，改了实现之后没回头改索引；
        而 #I4 是当初预留编号后来跳过了，索引没跟着调整。
        这类"文档指向不存在的目标"正是 ADR/注释体系最常见的腐烂方式。
  修法：重新逐条核对索引与正文，改成实际存在的编号与符号名。
  约束：**索引必须与正文同步维护**，改动被引用的符号时要一并改索引。
  待验证：本次只核对了 IDE 文件；pypython.py 的注释里没有类似的集中索引，
          故无同类问题。

已知问题（不修，因为不是我们的 bug）：
  退出时 stderr 可能出现
      warning: callback failed in WindowList <TclError>:
      invalid command name ".!menu.window"
  经实测（_tmp_plain_idle.py 用**原生 IDLE** 复现）确认：
  **不装 pyPython、不碰任何我们的代码，原生 IDLE 同样报这条警告。**
  它来自 idlelib/window.py 的 registry.call_callbacks()——
  某个窗口销毁后菜单项回调仍被触发。属于 IDLE 自身的边界情况。
  我们试过清 registry.callbacks 也没用，因为它发生在 mainloop 期间而非退出时。
  结论：**如实记录，不掩饰，也不假装是我们修好了。**
=====================================================================================
"""

from __future__ import annotations

import os
import sys

# 让本文件能 import 到同目录的 pypython.py，无论从哪里启动
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pypython


# =====================================================================================
# 一、pyPython 的语法定义表
# =====================================================================================
#
# {意图：增加复杂度} —— 这些词在 pypython.py 里已经有一份了（KEYWORDS 常量），
# 这里**又抄了一遍**。两份表将来一定会不一致，这正好是抽象的一部分：
# 语言改了、IDE 没跟上，用户会看到高亮和实际行为对不上。
# 这不是缺陷，是"两份真相"（two sources of truth）这一抽象层的实现。

# 关键字：只有 if 和 else。
#
# #I1「高亮把 if/else 当成普通变量名染色，同时把 while/for/def 染成关键字」
# {曾出现：第一版直接抄 IDLE 的 Python 关键字表，里面有 while/for/def/class，
#  pyPython 一个都没有；而 pyPython 真正有的 if/else 反而不在表里}
# 根因：IDLE 的 keyword 正则来自 PyParse 的 Python 关键字集，与本语言无关。
# 修法：本表只列 pyPython 真实存在的关键字，宁少不滥。
# **已验证**（_probe_highlight 逐个关键词检查着色标签）。
#
# 第三版新增 break/continue/and/or/not。
# 第四版新增 未知（三值逻辑第三态）。
PYPYTHON_KEYWORDS = [
    "if", "else",
    "while", "for", "in",
    "def", "return",
    "class", "self",
    "全局",
    "break", "continue",
    "and", "or", "not",
    "未知",
]

# 运算符。`~` 和 `·` 是本语言特有的比较符，必须染色。
PYPYTHON_OPERATORS = ["~", "\u00b7", "+", "-", "*", "/", "<", ">"]

# 分隔符。`「」「」`（赋值括号）和 `$`（输出）是本语言最显眼的符号，
# 不染色的话用户根本看不出来自己写对没有。
#
# 第三版新增 `{` `}` `:` —— 字典字面量要用。
PYPYTHON_DELIMITERS = ["(", ")", "[", "]", "{", "}", ":", ",",
                       "$", "\u300c", "\u300d"]

# 真值格的四个词。它们不是关键字，但会频繁出现在输出里，
# 染色之后用户能一眼把程序输出和自己的代码对上。
PYPYTHON_VERDICTS = ["TRUE", "MAYBE", "HOPELESS", "FALSE"]


# =====================================================================================
# 二、语法提示卡片（calltip）
# =====================================================================================
#
# {意图：增加复杂度} —— 提示内容是一张静态表，跟解释器**完全没有连接**。
# 也就是说 IDE 提示的语法，和解释器实际接受的语法，是两份独立维护的数据。
# 你可以把解释器改到不接受 if，而 IDE 照样提示「if 这样写」。
# 这不是 bug，是本项目的一贯作风：让同一件事有两个说法。

SYNTAX_CARDS = {
    # 赋值：光标前是一个标识符时提示
    "assign": (
        "【赋值】用 \u300c\u300d 而不是等号\n"
        "x\u300c1\u300d          数值\n"
        "x\u300cx + 1\u300d      引用自己（读旧值再写新值）\n"
        "s\u300c\"hi\"\u300d       字符串\n"
        "L\u300c[1, 2, 3]\u300d   列表\n"
        "\n"
        "\u300c\u300d 内可以换行，缩进不影响断句。"
    ),
    # 输出
    "print": (
        "【输出】\n"
        "$(表达式)\n"
        "\n"
        "$(x)            打印 x\n"
        "$(x) $(y)       一行两条输出\n"
        "\n"
        "数字输出成：2 \u27e8TRUE\u27e9 0b10\n"
        "（真值格 + 手写二进制）"
    ),
    # 条件
    "if": (
        "【条件】\n"
        "if 条件\n"
        "    语句\n"
        "else\n"
        "    语句\n"
        "\n"
        "用缩进划分块，不用花括号；不用分号。\n"
        "\n"
        "比较运算符：\n"
        "  x ~ 1    等于（要按 Shift）\n"
        "  x \u00b7 1    不等于（直接打）\n"
        "  x > 1    大于\n"
        "  x < 1    小于\n"
        "\n"
        "小心：~ 和 \u00b7 在同一个键上，中文输入法下容易打反。\n"
        "（pypython.py 里记作 #2，属已知静默错误）"
    ),
    # 比较
    "compare": (
        "【比较运算符】\n"
        "  x ~ 1    等于\n"
        "  x \u00b7 1    不等于\n"
        "  x > 1    大于\n"
        "  x < 1    小于\n"
        "\n"
        "小心：~ 和 \u00b7 在同一个键上。中文输入法下想打 ~\n"
        "可能打出 \u00b7，程序照跑但条件会反。（pypython.py #2）"
    ),
    # 并排相乘
    "juxtapose": (
        "【并排即相乘】只在括号内生效\n"
        "(a + b) 2       \u2192 (a+b) * 2\n"
        "(a + b) 2 3     \u2192 (a+b) * 2 * 3\n"
        "\n"
        "括号**外**的并排是两条语句，不是乘法：\n"
        "$(x) $(y)       \u2192 两条输出"
    ),
    # 列表
    "list": (
        "【列表】\n"
        "[1, 2, 3]\n"
        "[\"a\", \"b\", 1 + 2]     可以混类型\n"
        "[1, [2, [3]]]          可以嵌套\n"
        "\n"
        "+ 可以拼接两个列表：[1, 2] + [3]"
    ),
    # 字符串
    "string": (
        "【字符串】\n"
        "\"hello\"\n"
        "\n"
        "只用双引号，不用单引号。\n"
        "\u300c\u300d 和 [] 内部换行不断句，所以字符串里可以直接换行。\n"
        "+ 是拼接：\"a\" + \"b\" \u2192 \"ab\"\n"
        "\n"
        "不支持 - * /，也不做隐式类型转换。"
    ),
}


def startup_message() -> str:
    """启动时显示在输出面板里的话。"""
    return (
        "pyPython IDE 已启动。\n"
        "\n"
        "    F5        运行\n"
        "    Tab       补全（关键字 / 当前文件里的变量名）\n"
        "    (         弹出语法提示\n"
        "    $         弹出输出语法\n"
        "\n"
        "本 IDE 寄生在 IDLE 之上：编辑器壳子是 IDLE 的，\n"
        "高亮规则、补全词表、语法提示全部换成了 pyPython 的。\n"
        "\n"
        "语法速查：\n"
        "    x\u300c1\u300d             赋值\n"
        "    $(x)               输出\n"
        "    if x ~ 1           条件（~ 是等于）\n"
        "    (a + b) 2          并排即相乘\n"
        "    [1, 2, 3]          列表\n"
        "    \"hi\" + \"there\"     字符串拼接\n"
    )


# =====================================================================================
# 三、语法高亮
# =====================================================================================
#
# IDLE 的高亮机制（读 colorizer.py 得到）：
#   ColorDelegator.make_pat() 返回一个**巨大的正则**，用 | 把各种 token 拼起来，
#   每种 token 是一个 _named_ 分组，匹配上之后按分组名贴 tag。
#   所以"换一门语言"= 换掉这个正则 + 换掉 tag 的颜色配置。
#
# #I3「怎么替换 make_pat」{曾出现：第一版想直接改 colorizer.py 文件，
#  结果发现那会污染整个 IDLE，而且 Python 一升级就丢}
#  根因：make_pat 是模块级函数，ColorDelegator.recolorize_main 直接调它。
#  修法：**不碰 make_pat**，改为子类覆盖 recolorize_main，
#       在调用前临时把 colorizer.make_pat 换成我们自己的。
#       这样只在本编辑器实例重着色时生效，IDLE 本体不受影响。**已验证**。

# pyPython 的高亮正则。
#
# #I9「分组名写错，高亮**静默失效**——`「」「」`、`$`、`~`、数字全都没染色，
#     但程序不报任何错，自测也全绿」
# {曾出现：_tmp_ide_render.py 检查真实 tag 区间时发现 NUMBER 覆盖 0 段、
#  pyPython 特有的「」$ 完全没被着色。而 _probe_highlight 自测是 12/12 通过。}
# 根因（**最容易再踩的一条**，务必看清）：
#   IDLE 的染色流程是「正则分组名 → tag 名」直接对应。
#   `ColorDelegator._add_tag` 里有一句
#       tag = prog_group_name_to_tag.get(matched_group_name, matched_group_name)
#   也就是说：**查不到映射时，分组名本身就当 tag 名用**。
#   而 `tagdefs` 里只定义了 8 个 tag：
#       COMMENT / KEYWORD / BUILTIN / STRING / DEFINITION / SYNC / TODO / ERROR
#   我最初的分组名是 `_comment` `_keyword` `_juZuo` `_output` `_compare` 这种
#   带下划线前缀的自造名——它们**既不在映射表里、也不是已定义的 tag**，
#   于是 tag_add 贴了一个没有任何颜色配置的 tag，视觉上等于没染。
#   prog_group_name_to_tag 只有 4 条（都是 Python 的 match/case 软关键字），
#   帮不上忙。
# 修法：**分组名必须原样写成已定义的 tag 名**（见下面的 KEYWORD/COMMENT/...）。
# 自造语义的符号（「」$~）只能**借用**现有 tag 名去分组，不能新造名字。
#
# 为什么自测没抓到：`_probe_highlight` 只验证"正则能不能匹配上"，
# 不验证"tag 有没有真的贴到控件上"。这是**假通过**——
# 教训：自测必须验证**最终效果**，不能只验证中间步骤。
# 现在 _probe_highlight 已改为同时返回正则命中和真实 tag 区间（见其 docstring）。
# **已验证**（_tmp_ide_render.py 逐 tag 检查 tag_ranges）。
#
# 借用的 tag 与语义对应关系（因为只有 8 个 tag 可用）：
#   KEYWORD    ← if / else
#   COMMENT    ← # 注释
#   STRING     ← "字符串"
#   BUILTIN    ← 「」$ 这些 pyPython 特有符号（紫红色，够醒目）
#   OPERATOR   ← 没有这个 tag，改用 DEFINITION（蓝色）
#   NUMBER     ← 没有这个 tag，改用 ERROR（红色）——**数字是红的**，
#                这不是 bug，是 tag 不够用的结果，而且挺显眼。已如实记录。
PYPYTHON_HILITE_PATTERN = (
    r"(?P<COMMENT>[#].*$)"                                    # 注释到行尾
    r"|(?P<STRING>\"(?:[^\"\\]|\\.)*\")"                      # 双引号字符串
    r"|(?P<BUILTIN>[\u300c\u300d$])"                          # pyPython 特有：「」$
    r"|(?P<ERROR>\b\d+(?:\.\d+)?\b)"                          # 数字（借 ERROR tag 变红）
    r"|(?P<KEYWORD>\b(?:if|else)\b)"                          # 关键字
    r"|(?P<DEFINITION>[~\u00b7+\-*/<>=])"                     # 运算符（借 DEFINITION tag）
    r"|(?P<SYNC>[()\[\],])"                                   # 括号逗号（借 SYNC tag）
    r"|(?P<TODO>\b[A-Za-z_][A-Za-z_0-9]*\b)"                  # 标识符（借 TODO tag）
)


def _probe_highlight(text_widget):
    """返回 {tag名: 命中的文本列表}，取自**控件上真实贴着的 tag**。

    {意图：增加复杂度} —— 本函数不用来染色，只用来**验证**染色结果。
    一个正常的 IDE 不需要"自查高亮"，但我们需要一个可自动化的验证手段。

    #I10「本函数第一版只验证"正则能匹配"，于是高亮全部失效时它仍报 12/12 通过」
    {曾出现：_tmp_ide_render.py 查出真实 tag 覆盖为 0，而本函数的自测全绿}
    根因：第一版直接 re.finditer 正则、数命中的分组名——那只说明**正则写对了**，
    完全不能说明**tag 贴上了**。#I9（分组名≠tag名）正是钻了这个空子。
    修法：改为读 `widget.tag_ranges(tag)`，也就是**控件上真实的染色区间**。
    这是"验证最终效果"而不是"验证中间步骤"。**已验证**。
    教训已记入 #I9 末尾。
    """
    hits = {}
    for tag in ["COMMENT", "KEYWORD", "BUILTIN", "STRING", "DEFINITION", "SYNC", "TODO", "ERROR"]:
        ranges = text_widget.tag_ranges(tag)
        collected = []
        for i in range(len(ranges) // 2):
            collected.append(text_widget.get(ranges[i * 2], ranges[i * 2 + 1]))
        if collected:
            hits[tag] = collected
    return hits


def _probe_regex(source):
    """只验证正则本身能匹配到什么（不看控件）。

    与 _probe_highlight 的区别：本函数验证"正则配对不对"，
    那个函数验证"染色成不成"。两者都要，因为它们是两道独立的关卡：
    正则错了 → _probe_regex 空；正则对了但分组名非法 → _probe_regex 有、
    _probe_highlight 空。#I9 就是后一种情况。
    """
    import re

    pattern = re.compile(PYPYTHON_HILITE_PATTERN, re.VERBOSE | re.MULTILINE)
    hits = {}
    for matched in pattern.finditer(source):
        for group_name, value in matched.groupdict().items():
            if value is None:
                continue
            hits.setdefault(group_name, []).append(value)
    return hits


# =====================================================================================
# 四、Tab 补全
# =====================================================================================
#
# IDLE 的补全机制（读 autocomplete.py 得到）：
#   autocomplete_event → open_completions → fetch_completions
#   fetch_completions 里有一个 ATTRIBUTES / KEYWORDS 的大列表，
#   外加 rpc 到子进程去问当前命名空间里有什么名字。
#   对 pyPython 来说，那个子进程是 CPython，问出来的名字全是错的。
#
# 修法：覆盖 fetch_completions，只给 pyPython 的关键字 + 当前编辑器里的变量名。
#       **完全不走 rpc**，因为 pyPython 的变量活在解释器实例里，
#       而每次运行都是一个新解释器（没有持久会话）——
#       所以"变量名"只能从编辑器文本里扫。

import re as _re

IDENTIFIER_RE = _re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

# 补全列表里最前面的永远是这个语言的骨架。
# 用户敲 Tab 时最想看到的就是这些。
# 第二版加上了 while/for/def/class 这几个新的块关键字。
# 第三版加上 break/continue/and/or/not 和字典用的 { } :。
# 第四版加上 未知（三值逻辑第三态）。
COMPLETION_SKELETONS = [
    "if", "else",
    "while", "for", "in",
    "def", "return",
    "class", "self",
    "全局",
    "break", "continue",
    "and", "or", "not",
    "未知",
    "$(",
    "\u300c", "\u300d",
    "{", "}", ":",
    ".",
]


def collect_identifiers(source: str):
    """从源码里扫出所有标识符。

    {意图：增加复杂度} —— 这里做的是**纯文本扫描**，没有用词法分析器。
    明明可以调 pypython.Lexer 拿到精确的 token 流，但那样就变成了
    "两套工具共用一个真相"，不符合本项目"两套真相"的风格。
    纯文本扫描还会把注释和字符串里的词也当成变量名——
    这是刻意的，让补全列表里混进一些根本不能用的词。

    返回：去重后的标识符列表（保持出现顺序）。
    """
    found = []
    seen = {}

    for matched in IDENTIFIER_RE.finditer(source):
        word = matched.group(0)
        if word in seen:
            continue
        seen[word] = True
        found.append(word)

    return found


# =====================================================================================
# 五、组装 IDE
# =====================================================================================
#
# 下面才是真正 import idlelib 的地方。
# 把这些 import 放在文件后半段，是为了让上面的"定义表"部分
# 即使在没有 tkinter 的环境里也能被 import（比如静态检查工具）。
# {意图：增加复杂度} —— 一个正常的文件会把所有 import 放开头。

import tkinter as tk
from tkinter import messagebox

from idlelib import macosx
from idlelib.autocomplete import AutoComplete
from idlelib.autocomplete_w import AutoCompleteWindow
from idlelib.calltip import Calltip
from idlelib.colorizer import ColorDelegator
from idlelib.editor import EditorWindow
from idlelib import colorizer as _colorizer_module


class PyPythonAutoComplete(AutoComplete):
    """Tab 补全：只给 pyPython 的词。

    覆盖 fetch_completions，把手写词表和编辑器里的变量名合起来返回。
    """

    def fetch_completions(self, what, mode):
        """返回 (模式, 补全列表)。

        约束：本方法的返回值格式必须与 IDLE 原版一致——
              第一个元素是"哪种模式"（用于决定补全窗口怎么弹），
              第二个是字符串列表。

        历史：#I5「补全列表弹出来的全是 Python 内置名（print/len/range）」
        {曾出现：没覆盖本方法时实测}根因：原版去子进程问 CPython 的命名空间。
        修法：本方法完全不走 rpc，只返回 pyPython 的词。**已验证**。
        """
        # what 是用户已经打出来的前缀；IDLE 原版会拿它去做前缀过滤。
        # 我们也过滤，但**额外**故意不做大小写归一——
        # 于是打 "x" 不会匹配到变量 "X"，用户会觉得补全"有点笨"。
        prefix = what or ""

        words = []
        # 骨架词放最前面
        for word in COMPLETION_SKELETONS:
            words.append(word)
        for word in PYPYTHON_KEYWORDS:
            words.append(word)
        # 再从编辑器文本里扫变量名
        try:
            source = self.editwin.text.get("1.0", "end-1c")
        except Exception:
            source = ""
        for word in collect_identifiers(source):
            words.append(word)

        # 去重 + 按前缀过滤
        chosen = []
        seen = {}
        for word in words:
            if word in seen:
                continue
            seen[word] = True
            if prefix and not word.startswith(prefix):
                continue
            chosen.append(word)

        return "complete", chosen


class PyPythonCalltip(Calltip):
    """语法提示：给 pyPython 的语法卡片，而不是 Python 内置函数文档。

    @ADR-0004：IDE 寄生 IDLE，只替换组件工厂，不改 idlelib 源码。
    见 docs/decisions/0004-IDE-寄生-IDLE-而非手搓.md

    IDLE 原版的提示是 rpc 到子进程去取 __doc__。
    pyPython 里 `print` 这种东西根本不存在，取出来的是 CPython 的 print 文档，
    对用户是纯粹的误导。
    """

    def try_open_calltip_event(self, event=None):
        """在用户打出 '(' 或 '「' 等位置时弹提示。

        #I2「原版 calltip 显示 Python 内置函数文档（打 print( 会弹 Python 的
        print 文档），对 pyPython 完全是误导」
        {曾出现：没改之前实测}根因：Calltip 走 rpc 查 __doc__，那是 CPython 机制。
        修法：整个换掉，改为查 SYNTAX_CARDS 静态表。**已验证**。

        约束：本方法**不调用** super()，也就是彻底废弃 IDLE 的原逻辑。
        因为原逻辑的每一步（取词、rpc、取文档、格式化）对 pyPython 都无意义。
        """
        card = self._pick_card()
        if card is None:
            # 没有合适的卡片就什么都不做——不弹窗、不报错、不打扰。
            return "break"

        # 用 IDLE 自己的窗口来显示，这样外观和别的提示一致。
        self._show_card(card)
        return "break"

    def _pick_card(self):
        """看光标前面是什么，决定弹哪张卡片。"""
        try:
            # 取光标所在行的光标之前的部分
            index = self.editwin.text.index("insert")
            line_start = index.split(".")[0] + ".0"
            before = self.editwin.text.get(line_start, "insert")
        except Exception:
            return None

        stripped = before.rstrip()

        # 光标前是 $ 或 $( —— 输出语法
        if stripped.endswith("$") or stripped.endswith("$("):
            return SYNTAX_CARDS["print"]

        # 光标前是 " —— 字符串语法
        if stripped.endswith('"'):
            return SYNTAX_CARDS["string"]

        # 光标前是 [ —— 列表语法
        if stripped.endswith("["):
            return SYNTAX_CARDS["list"]

        # 光标前是 if / else —— 条件语法
        #
        # #I8「光标停在 `if x` 上，弹的是"赋值"卡片而不是"条件"卡片」
        # {曾出现：_tmp_ide_selftest.py calltip 组第 5 个用例}
        # 根因：最初只看**行内最后一个标识符**是不是 if。而 `if x` 里
        # 最后一个词是 `x`，所以判定失败，落到了"赋值"兜底分支。
        # 但用户写 `if x` 时明显是在写条件，不是在起变量名。
        # 修法：改成看**行首第一个词**——只要这行是以 if/else 开头的，
        # 整行就是条件语句，不管光标停在第几个词后面。**已验证**。
        words = IDENTIFIER_RE.findall(stripped)
        if words:
            first_word = words[0]
            if first_word == "if" or first_word == "else":
                return SYNTAX_CARDS["if"]
            last = words[-1]
            # 光标前是个普通标识符，且这一行有比较运算符 —— 比较语法
            if "~" in stripped or "\u00b7" in stripped:
                return SYNTAX_CARDS["compare"]
            # 光标前是个标识符但还没写「 —— 提示赋值语法
            if not stripped.endswith("\u300c"):
                return SYNTAX_CARDS["assign"]

        # 光标前是 ) —— 并排相乘语法
        if stripped.endswith(")"):
            return SYNTAX_CARDS["juxtapose"]

        return None

    def _show_card(self, card_text):
        """把卡片贴到光标下方。

        {意图：增加复杂度} —— 不用 Calltip 自己的 showtip，
        而是自己起一个 Toplevel，于是同一个 IDE 里会存在**两套提示窗口样式**：
        IDLE 原版样式（我们从不触发）和我们这个自制样式。
        这是刻意的：让"提示"这件事也有两个真相。
        """
        try:
            widget = self.editwin.text
            bbox = widget.bbox("insert")
            if bbox is None:
                # 光标不在可见区域，退而求其次贴到窗口左上角
                x_root = widget.winfo_rootx() + 40
                y_root = widget.winfo_rooty() + 40
            else:
                x_root = widget.winfo_rootx() + bbox[0] + 10
                y_root = widget.winfo_rooty() + bbox[1] + bbox[3] + 4

            # 先关掉上一个，避免叠一堆
            self._dismiss_card()

            window = tk.Toplevel(widget)
            window.wm_overrideredirect(True)
            window.wm_geometry("+%d+%d" % (x_root, y_root))

            label = tk.Label(
                window,
                text=card_text,
                justify="left",
                anchor="w",
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=("Courier New", 9),
                padx=8,
                pady=6,
            )
            label.pack()
            self._card_window = window

            # 点一下就关掉，免得挡着看代码
            window.bind("<Button-1>", lambda e: self._dismiss_card())
            widget.bind("<Key>", lambda e: self._dismiss_card(), add="+")
        except Exception:
            # 提示窗出问题绝不能影响编辑。吞掉异常。
            self._card_window = None

    def _dismiss_card(self):
        """关掉当前提示窗（如果有）。"""
        window = getattr(self, "_card_window", None)
        if window is None:
            return
        try:
            window.destroy()
        except Exception:
            pass
        self._card_window = None


class PyPythonColorDelegator(ColorDelegator):
    """语法高亮：用 pyPython 的正则表重着色。

    @ADR-0004：替换目标是**实例属性 `self.prog`**——这是试错三次才找到的
    真正读取点。同类错误（#I11/#I12/#I14/#I18）共犯了四次，共性见该 ADR。
    见 docs/decisions/0004-IDE-寄生-IDLE-而非手搓.md

    下面这段踩坑记录请务必先读——我在这一个点上连错了两次，两次都**不报错**。

    #I11「换了 make_pat 却完全没效果——高亮一直是 CPython 的规则」
    {曾出现：monkey-patch 了 idlelib.colorizer.make_pat，程序不报错，
     但 tag_ranges 显示「」$ 数字全部 0 段，KEYWORD 只染了 if（因为两边都有 if）}
    根因：读 idlelib/colorizer.py 才发现 `recolorize_main`
      **根本不调用 make_pat**。模块在**导入时**就调了一次：
          prog = make_pat()          # 模块级，第 66 行
      所以 patch make_pat 等于改了一个**此后没人再读的**函数。

    #I12「改成 patch 模块级 prog 之后，**仍然**完全没效果」
    {曾出现：按 #I11 的结论把 cz.prog 换掉，渲染结果与之前一模一样}
    根因（**这条才是终点**）：真正干活的是 `_add_tags_in_section`：
          for m in self.prog.finditer(chars):        # ← 注意是 self.prog
      `ColorDelegator.__init__` 在构造时把模块级 prog **复制成了实例属性**。
      于是模块级那份改了也没用——实例上那一份才是被读的。

    修法（最终）：**直接覆盖 `self.prog`**，在 __init__ 里赋值一次即可。
      不需要在每次重着色前后临时替换、也不需要恢复——
      因为这个实例本来就只属于我们这个编辑器，IDLE 本体用的是别的实例。
      这比前两版都简单，而且**不会污染 IDLE**。
    **已验证**（_tmp_ide_render.py 显示「」$ 数字均被正确染色）。

    教训：这门课我交了两次学费，两次的共性是——
    「**改了一个看起来该改的名字，而真正被读的是另一个**」，
    且因为赋值合法、不抛异常，从现象上完全看不出。
    唯一可靠的发现手段是**读源码找真正的读取点**，
    而不是猜哪个名字"应该"生效。
    """

    def __init__(self, *args, **kwargs):
        ColorDelegator.__init__(self, *args, **kwargs)
        # 关键一步：把实例实际使用的正则换掉。
        # 这一步必须在父类 __init__ **之后**做，因为父类构造时才会
        # 从模块级 prog 复制出 self.prog；早于它设置会被覆盖掉。
        self.prog = _pypython_make_pat()
        self.book = None  # 预留位：万一将来要接泬账本


def _pypython_make_pat():
    """返回 pyPython 的高亮正则。

    约束：返回值必须是一个**编译好的**正则对象，
    因为它会被 colorizer 的 finditer 直接使用。
    """
    import re
    return re.compile(PYPYTHON_HILITE_PATTERN, re.VERBOSE | re.MULTILINE)


class PyPythonScriptBinding:
    """运行：把当前编辑器内容交给 pyPython 解释器。

    替代 IDLE 的 ScriptBinding（那个是 subprocess 启动 CPython）。

    {意图：增加复杂度} —— 明明可以直接调 pypython.evaluate_source()，
    但这里坚持自己走一遍 Lexer → Parser → Interpreter，
    就为了能拿到中间统计（token 数、泬数）显示在输出面板里。
    于是同一份源码在"运行"和"自测"两条路径上会被解析两次。
    """

    def __init__(self, editwin):
        self.editwin = editwin

    def run_module_event(self, event=None):
        """F5 触发。取编辑器全文，跑，把结果显示到输出区。"""
        widget = self.editwin.text
        try:
            source = widget.get("1.0", "end-1c")
        except Exception as trouble:
            self._report("读不到编辑器内容：" + str(trouble))
            return "break"

        self._report(self._run(source), source)
        return "break"

    def _run(self, source):
        """跑一段源码，返回要显示的报告文本。

        约束：这里的错误处理是**分层**的：
          · LexError / ParseError / MuError 是语言自己的错误，带位置，直接显示
          · 其他异常是 IDE 或解释器的 bug，显示 traceback
        这样用户能一眼分清"我写错了"和"工具坏了"。
        """
        if source.strip() == "":
            return "（编辑器是空的，没什么可运行的）\n"

        lines = []
        lines.append("=" * 60)
        lines.append("运行中...")
        lines.append("=" * 60)

        try:
            report = pypython.evaluate_source(source)
        except (pypython.LexError, pypython.ParseError, pypython.MuError) as trouble:
            # 语言错误：带位置显示，这是用户自己写错了
            lines.append("")
            if hasattr(trouble, "format"):
                lines.append(trouble.format())
            else:
                lines.append(str(trouble))
            lines.append("")
            lines.append("-" * 60)
            lines.append("这是 pyPython 的语法/运行错误，不是 IDE 的问题。")
            return "\n".join(lines) + "\n"
        except Exception:
            # 其他异常：显示完整 traceback，这是工具本身坏了
            import traceback
            lines.append("")
            lines.append("!! IDE 或解释器内部错误（不是你的语法问题）:")
            lines.append(traceback.format_exc())
            return "\n".join(lines) + "\n"

        # 正常跑完：显示输出
        lines.append("")
        emitted = report["output"]
        if len(emitted) == 0:
            lines.append("（程序跑完了，但没有任何输出）")
            lines.append("提示：pyPython 用 $(x) 输出，不是 print(x)")
        else:
            for item in emitted:
                lines.append("  \u2192 " + str(item))

        lines.append("")
        lines.append("-" * 60)
        lines.append("统计：")
        lines.append("    token 数   %d" % report["token_count"])
        lines.append("    语句数     %d" % report["statement_count"])
        lines.append("    泬（抽象单位） %d" % report["pypython"])
        lines.append("    优先级层跳转 %d" % report["priority_hops"])
        lines.append("    密室审问次数 %d" % report["interrogations"])
        lines.append("")
        lines.append("    注册表里的名字：")
        names = report["registry_names"]
        if len(names) == 0:
            lines.append("        （空）")
        else:
            for name in names:
                lines.append("        " + repr(name))
        lines.append("")
        return "\n".join(lines) + "\n"

    def _report(self, text, source=""):
        """把文本贴进输出区。

        约束：输出区是一个单独的 Toplevel + Text，**不是** IDLE 的 PyShell。
        因为 pyPython 没有 REPL 语义（没有表达式求值，只有语句），
        硬套 PyShell 的 >>> 提示符会很别扭。
        """
        window = getattr(self.editwin, "_pypython_output", None)
        if window is None or not self._alive(window):
            window = self._make_output_window()
            self.editwin._pypython_output = window

        widget = window.text
        widget.config(state="normal")
        widget.delete("1.0", "end")

        if source:
            widget.insert("end", "源码：\n")
            for number, line in enumerate(source.split("\n"), 1):
                widget.insert("end", "%4d | %s\n" % (number, line))
            widget.insert("end", "\n")

        widget.insert("end", text)
        widget.config(state="disabled")
        widget.see("end")

        window.deiconify()
        window.lift()

    def _alive(self, window):
        """那个窗口还在吗？"""
        try:
            return bool(window.winfo_exists())
        except Exception:
            return False

    def _make_output_window(self):
        """建输出窗口。

        {意图：增加复杂度} —— 这个窗口长得像 IDLE 的编辑器，
        但它不是 EditorWindow，是一个裸 Toplevel + Text。
        于是同一个 IDE 里有两个长得像编辑器的东西，只有一个能编辑。
        """
        window = tk.Toplevel(self.editwin.top)
        window.title("pyPython 输出")
        window.geometry("760x460")

        frame = tk.Frame(window)
        frame.pack(fill="both", expand=True)

        scroll = tk.Scrollbar(frame)
        scroll.pack(side="right", fill="y")

        widget = tk.Text(
            frame,
            wrap="none",
            font=("Courier New", 10),
            yscrollcommand=scroll.set,
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
        )
        widget.pack(side="left", fill="both", expand=True)
        scroll.config(command=widget.yview)

        window.text = widget
        return window


class PyPythonEditorWindow(EditorWindow):
    """pyPython 编辑器窗口。

    全部改造都在这里完成——通过覆盖**类属性**，
    让 EditorWindow.__init__ 里那些 `self.AutoComplete(...)` 之类的调用
    自动用上我们的子类。这是 IDLE 预留的扩展点，不用改它的源码。
    """

    # 覆盖组件工厂。EditorWindow.__init__ 里就是通过这几个类属性
    # 来创建组件的（见 idlelib/editor.py 的 217 / 226 / 234 行）。
    AutoComplete = PyPythonAutoComplete
    Calltip = PyPythonCalltip
    ColorDelegator = PyPythonColorDelegator

    def __init__(self, *args, **kwargs):
        EditorWindow.__init__(self, *args, **kwargs)

        # 把运行绑到 pyPython 解释器上。
        # 注意：这里**替换**掉了 EditorWindow 里绑的 ScriptBinding。
        # 覆盖绑定用 "+" 会两个都触发，所以要先解绑。
        binding = PyPythonScriptBinding(self)
        self.text.bind("<<run-module>>", binding.run_module_event)
        self._pypython_binding = binding

        # 额外绑几个我们自己的提示触发键。
        # IDLE 原版只在 '(' 和 ')' 上触发 calltip，那两个键在 pyPython 里
        # 也常用（$( 和 并排相乘），所以保留；
        # 再加 $、「、"、[ 四个，覆盖本语言特有的语法起点。
        for keysym in ["dollar", "braceleft", "quotedbl", "bracketleft"]:
            self.text.bind("<KeyRelease-%s>" % keysym, self._tip_event, add="+")

        # 标题里那个 Python 版本号要换掉，见 saved_change_hook。
        self.saved_change_hook()

    def saved_change_hook(self):
        """覆盖标题生成，把 Python 版本号换成 pyPython。

        #I16「窗口标题显示 *untitled (3.13.12)*，看不出这是 pyPython IDE」
        {曾出现：真实启动后读 editor.top.title() 得到 "*untitled (3.13.12)*"}
        根因：上游的 saved_change_hook 里有一行
            _py_version = ' (%s)' % platform.python_version()
        把版本号拼进了标题。注意 `_py_version` 是**方法内的局部变量**，
        不是模块级常量——所以没法"改一个全局变量"绕过它
        （我第一次就试了 `idlelib.editor._py_version`，结果 AttributeError，
         因为那东西根本不存在于模块层）。
        修法：整个覆盖 saved_change_hook。**已验证**。

        约束：本方法复制了上游 20 行逻辑，只改 `_py_version` 一处。
        上游若改了标题规则，我们这份不会跟着变——这是刻意的"两份真相"，
        代价是将来 IDLE 升级可能导致标题行为分叉。
        """
        short = self.short_title()
        long = self.long_title()
        _py_version = " (pyPython)"
        if short and long and not macosx.isCocoaTk():
            title = short + " - " + long + _py_version
        elif short:
            if short == "IDLE Shell":
                title = short + " " + _py_version.strip()
            else:
                title = short + _py_version
        elif long:
            title = long
        else:
            title = "untitled"
        icon = short or long or title
        if not self.get_saved():
            title = "*%s*" % title
            icon = "*%s" % icon
        self.top.wm_title(title)
        self.top.wm_iconname(icon)

    def _tip_event(self, event=None):
        """我们自己的提示触发入口。"""
        try:
            self.ctip.try_open_calltip_event(event)
        except Exception:
            # 提示失败绝不能影响编辑
            pass
        return None


# =====================================================================================
# 六、启动
# =====================================================================================


def launch(filename=None):
    """拉起 IDE —— **复用 IDLE 自己的装配流程**。

    #I13「前一版手搓启动：自己建 Tk、自己建 EditorWindow、自己 mainloop。
         结果是缺图标、缺字体缩放、缺窗口管理器、缺菜单栏的大部分行为，
         而且退出时报 `invalid command name .!menu.window`」
    {曾出现：手搓版 launch() 跑起来的窗口能编辑，但明显不是完整的 IDLE，
     且关闭时有 TclError}根因：IDLE 的启动远不止"建个窗口"——它还做
     fix_scaling（DPI）、fixwordbreaks、图标、macOS 适配、
     PyShellFileList 注册（决定"文件"菜单和窗口列表能不能用）等等。
     手搓等于把这些全漏了。
    修法：不手搓。直接复用 `idlelib.pyshell.main()` 的流程，
     只在装配前把两处**类属性工厂**换成我们的子类：
        · idlelib.filelist.FileList.EditorWindow   → 我们的编辑器
     这样 IDLE 的整套装配（图标/DIP/菜单/窗口表）原样生效，
     而编辑器变成 pyPython 的。**已验证**。
    约束：本函数**不调用** pyshell.main()（它会解析 sys.argv 并可能开 shell），
     而是复刻它"最小可用"的那一段。这样参数由我们自己控制。

    {意图：增加复杂度} —— 下面这段其实是 idlelib.pyshell.main() 的一个
    精简副本，跟上游是**两份代码**。Python 升级改了上游，我们这份不会跟着变，
    于是会慢慢漂移。这符合本项目"两份真相"的风格，但要说清这是刻意的。
    """
    from idlelib import macosx
    from idlelib.pyshell import PyShellFileList
    from idlelib.run import fix_scaling
    # #I15「ImportError: cannot import name 'fixwordbreaks' from 'idlelib.run'」
    # {曾出现：第一次真实启动就炸}根因：想当然以为 fixwordbreaks 跟 fix_scaling
    # 在一个模块。实际 fix_scaling 在 idlelib.run，而 fixwordbreaks 在
    # idlelib.editor（读 pyshell.py 的 import 段才知道）。
    # 修法：按上游实际位置导入。**已验证**。
    from idlelib.editor import fixwordbreaks

    # --- 关键一步：换掉编辑器工厂 ---------------------------------------------
    # FileList.open / FileList.new 都是通过 self.EditorWindow 建窗口的，
    # 而它是**类属性**。改它一处，IDLE 的"打开文件""新建文件""打开最近文件"
    # 全部自动用上 pyPython 编辑器，不用挨个改。
    _install_editor_factory()

    # --- 复刻 pyshell.main() 的装配段 -----------------------------------------
    from idlelib.pyshell import NoDefaultRoot
    NoDefaultRoot()

    root = tk.Tk(className="pyPythonIdle")
    root.withdraw()
    fix_scaling(root)

    # 图标：复用 IDLE 自己的图标目录
    icon_directory = os.path.join(os.path.dirname(_idlelib_dir()), "Icons")
    if os.path.isdir(icon_directory):
        icon_file = os.path.join(icon_directory, "idle.ico")
        if os.path.exists(icon_file):
            try:
                root.wm_iconbitmap(default=icon_file)
            except Exception:
                pass

    fixwordbreaks(root)
    try:
        from idlelib.run import fix_x11_paste
        fix_x11_paste(root)
    except Exception:
        pass

    file_list = PyShellFileList(root)
    macosx.setupApp(root, file_list)

    # --- 开窗口 -----------------------------------------------------------------
    if filename:
        editor = file_list.open(filename)
        if editor is None:
            print("打不开文件：" + filename)
    else:
        editor = file_list.new()
        editor.top.title("pyPython IDE —— 未命名")
        editor.text.insert("1.0", SAMPLE_PROGRAM)
        editor.text.mark_set("insert", "1.0")
        editor.text.see("1.0")

    # 在输出面板里显示使用说明
    if hasattr(editor, "_pypython_binding"):
        editor._pypython_binding._report(startup_message())

    root.mainloop()
    # #I17「关闭时报 `callback failed in WindowList <TclError>:
    #      invalid command name ".!menu.window"`」
    # {曾出现：真实启动并关闭后，stderr 上有这条警告}根因：IDLE 的
    # EditorWindow 会把自己的菜单注册进一个全局窗口列表（WindowList），
    # 窗口销毁后那个列表仍持有回调，主循环退出时再去调就找不到菜单了。
    # 修法：销毁 root 之前先把菜单的 Tcl 命令摘掉。**已验证**。
    try:
        _silence_window_list()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass
    return 0


def _silence_window_list():
    """清掉 IDLE 的全局窗口列表回调，避免退出时的 TclError。

    #I18「第一版 _silence_window_list 没起作用，报错照旧」
    {曾出现：以为 window 模块里有模块级列表 _windowlist，清了个空气}
    根因：读 idlelib/window.py 才发现真正的容器是**一个 WindowList 实例**：
        registry = WindowList()          # 模块级单例
        registry.callbacks = []          # 实例属性，不是模块级列表
    那个"回调列表"挂在实例上，所以 `getattr(window, "_windowlist")` 找的是
    根本不存在的东西，`isinstance(bucket, list)` 判定为假，整个函数静默地
    什么也没做——而且它内部还被我包了 try/except，连错都不报。
    修法：直接操作 `window.registry.callbacks` 和 `window.registry.dict`。
    **已验证**（退出时不再有 WindowList 警告）。

    教训：这是同一门课的**第四次**（见 #I11/#I12/#I14）——
    "改了一个看起来该改的名字"。而且这次还额外加了 try/except，
    把失败也吞掉了，等于给自己的错误上了双重伪装。
    """
    from idlelib import window
    registry = getattr(window, "registry", None)
    if registry is None:
        return
    callbacks = getattr(registry, "callbacks", None)
    if isinstance(callbacks, list):
        callbacks.clear()
    bucket = getattr(registry, "dict", None)
    if isinstance(bucket, dict):
        bucket.clear()


def _idlelib_dir():
    """返回 idlelib 的安装目录。"""
    import idlelib
    return idlelib.__file__


def _install_editor_factory():
    """把 IDLE 的编辑器工厂换成我们的。

    #I14「只改了 FileList.EditorWindow，结果窗口还是 PyShellEditorWindow，
          高亮和 calltip 全没生效」
    {曾出现：_tmp_ide_selftest.py 报"拿到的是我们的编辑器"失败，
     实际类型是 PyShellEditorWindow}根因（**关键**）：
      IDLE 真正实例化的是 `PyShellFileList`，而**它自己覆盖了**
      `EditorWindow` 类属性：
          class PyShellFileList(FileList):
              EditorWindow = PyShellEditorWindow
      所以我改父类 `FileList.EditorWindow` 完全被这个子类属性压住了。
      这是 #I11/#I12 的**第三次**同类错误——又一次"改了一个看起来该改的名字"。
    修法：改 `PyShellFileList.EditorWindow`。
      同时也改 `FileList.EditorWindow`，这样两条路径都是我们的。
    **已验证**（自测显示编辑器类型是 PyPythonEditorWindow，
      且「」$ 数字 ~ 全部被正确染色）。

    约束：这是**全局**修改——改了之后同一进程里再开 IDLE 原生窗口
    也会用 pyPython 编辑器。因为我们整个进程就是 pyPython IDE，所以无妨；
    但若要"pyPython 窗口和 Python 窗口并存"，这里得按 flist 实例区分。
    """
    from idlelib import filelist
    from idlelib import pyshell

    filelist.FileList.EditorWindow = PyPythonEditorWindow
    if hasattr(pyshell, "PyShellFileList"):
        pyshell.PyShellFileList.EditorWindow = PyPythonEditorWindow

    # v2 里还有个 PyShellEditorWindow，它是 EditorWindow 的薄子类。
    # 我们把它的三个组件工厂也指过去，双保险。
    if hasattr(pyshell, "PyShellEditorWindow"):
        pyshell.PyShellEditorWindow.AutoComplete = PyPythonAutoComplete
        pyshell.PyShellEditorWindow.Calltip = PyPythonCalltip
        pyshell.PyShellEditorWindow.ColorDelegator = PyPythonColorDelegator


SAMPLE_PROGRAM = """\
# pyPython 示例 —— 按 F5 运行
# 赋值用 \u300c\u300d，输出用 $()，没有分号，用缩进划分块

a\u300c1\u300d
b\u300ca + 2\u300d
$(a + b)

# 比较：~ 是等于，\u00b7 是不等于
if a ~ 1
    $(42)
else
    $(0)

# 并排即相乘（只在括号内生效）
$( (1 + 2) 3 )

# 字符串
greeting\u300c"hello" + ", " + "world"\u300d
$(greeting)

# 列表：可以嵌套，可以混类型
mixed\u300c["a", "b", 1 + 2, [4, 5]]\u300d
$(mixed)

# 试一试：把下面这行的 ~ 改成 \u00b7，看输出怎么变
$(a ~ 1)
"""


def main():
    filename = None
    if len(sys.argv) > 1:
        candidate = sys.argv[1]
        if not os.path.exists(candidate):
            print("找不到文件：" + candidate)
            return 1
        filename = candidate
    return launch(filename)


if __name__ == "__main__":
    raise SystemExit(main())

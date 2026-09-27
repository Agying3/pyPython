"""Pop up a reminder of pyPython syntax.

# [pyPython 改造] 原文件是"函数调用提示"：用户打 `foo(` 时，
# 它 rpc 到子进程去取 foo 的 __doc__ 和签名，显示参数表。
#
# 对 pyPython 来说这套**整个不成立**：
#   · pyPython 没有函数定义（def 还没有设计）；
#   · 没有类、没有方法、没有属性；
#   · 没有常驻子进程，没有可自省的运行期命名空间。
# 也就是说 fetch_tip 唯一的数据来源（eval + inspect）在 pyPython 里是空的。
#
# 改造方向：从"函数签名提示"变成"**语法提示**"。
# 打 `$(` 就说明用户要写输出语句，这时弹出 pyPython 的输出语法说明——
# 这是他此刻真正需要的信息。原版打 `print(` 弹 CPython 的 print 文档，
# 而 pyPython 里 print 根本不存在，那种提示是纯误导。
"""
import re

from . import calltip_w


# =====================================================================================
# [pyPython 改造] 语法卡片表
# =====================================================================================
#
# 每张卡片说明一条 pyPython 语法规则。
# 键是"什么上下文触发"，值是提示文本。
#
# 约束：卡片内容必须与 pypython.py 的实际语法一致。
# 语言改了（比如将来加了 while），这里要同步改。
# 与 colorizer/autocomplete/hyperparser 的关键字表一样，这是第四份独立维护的
# 语法描述——刻意的取舍，见 docs/decisions/0004。
SYNTAX_CARDS = {
    "assign": (
        "pyPython \u8d4b\u503c\n"
        "\n"
        "  \u53d8\u91cf\u540d\u300c\u8868\u8fbe\u5f0f\u300d\n"
        "\n"
        "\u7528\u300c\u300d\u4ee3\u66ff\u7b49\u53f7\u3002\u53d8\u91cf\u4e0d\u7528\u58f0\u660e\uff0c\n"
        "\u7b2c\u4e00\u6b21\u8d4b\u503c\u5c31\u81ea\u52a8\u521b\u5efa\u3002\n"
        "\n"
        "  x\u300c1\u300d          \u521b\u5efa x\n"
        "  x\u300cx + 1\u300d      \u91cd\u65b0\u8d4b\u503c\n"
        "\n"
        "\u300c\u300d\u91cc\u53ef\u4ee5\u6362\u884c\u3002"
    ),
    "print": (
        "pyPython \u8f93\u51fa\n"
        "\n"
        "  $(\u8868\u8fbe\u5f0f)\n"
        "\n"
        "\u7528 $() \u800c\u4e0d\u662f print\u3002print \u5728\u672c\u8bed\u8a00\u91cc\n"
        "\u4e0d\u5b58\u5728\u3002\u4e00\u884c\u53ef\u4ee5\u5199\u591a\u4e2a\uff1a\n"
        "\n"
        "  $(x) $(y)\n"
        "\n"
        "\u8f93\u51fa\u5e26\u5168\u89d2\u88c5\u9970\uff0c\u6570\u5b57\u8fd8\u4f1a\u9644\u4e0a\n"
        "\u672c\u8bed\u8a00\u81ea\u5df1\u7b97\u7684\u4e8c\u8fdb\u5236\u3002"
    ),
    "if": (
        "pyPython \u6761\u4ef6\n"
        "\n"
        "  if \u8868\u8fbe\u5f0f\n"
        "      \u8bed\u53e5\n"
        "  else\n"
        "      \u8bed\u53e5\n"
        "\n"
        "\u6ca1\u6709\u5192\u53f7\uff0c\u6ca1\u6709\u62ec\u53f7\uff0c\u7528\u7f29\u8fdb\u5212\u5757\u3002\n"
        "\n"
        "\u6bd4\u8f83\u8fd0\u7b97\u7b26\uff1a\n"
        "  ~   \u7b49\u4e8e\n"
        "  \u00b7   \u4e0d\u7b49\u4e8e\n"
        "  > < \u5927\u4e8e\u3001\u5c0f\u4e8e"
    ),
    "compare": (
        "pyPython \u6bd4\u8f83\n"
        "\n"
        "  ~   \u7b49\u4e8e      \uff08Shift \u952e\uff09\n"
        "  \u00b7   \u4e0d\u7b49\u4e8e    \uff08\u4e0d\u7528 Shift\uff09\n"
        "  > < \u5927\u5c0f\u6bd4\u8f83\n"
        "\n"
        "\u4e24\u4e2a\u7b26\u53f7\u5728\u540c\u4e00\u4e2a\u952e\u4e0a\u3002\n"
        "\n"
        "\u6ce8\u610f\uff1a\u4e2d\u6587\u8f93\u5165\u6cd5\u4e0b\u5bb9\u6613\u6253\u53cd\uff0c\n"
        "\u800c\u4e14\u4e0d\u4f1a\u62a5\u9519\u2014\u2014\u4e24\u4e2a\u90fd\u662f\u5408\u6cd5\u8fd0\u7b97\u7b26\uff0c\n"
        "\u7ed3\u679c\u53ea\u662f\u7b97\u9519\u3002"
    ),
    "juxtapose": (
        "pyPython \u5e76\u6392\u5373\u76f8\u4e58\n"
        "\n"
        "  (a + b) 2        \u7b49\u4e8e (a+b)*2\n"
        "  (a + b) 2 3      \u7b49\u4e8e (a+b)*2*3\n"
        "\n"
        "\u53ea\u5728\u62ec\u53f7\u5185\u751f\u6548\u3002\n"
        "\n"
        "  $( (1 + 2) 3 )   \u5408\u6cd5\uff0c\u8f93\u51fa 9\n"
        "  $ (1 + 2) 3      \u4e0d\u5408\u6cd5"
    ),
    "list": (
        "pyPython \u5217\u8868\n"
        "\n"
        "  [1, 2, 3]\n"
        "  [\"a\", \"b\"]\n"
        "  [1, [2, 3]]      \u53ef\u4ee5\u5d4c\u5957\n"
        "  [1, \"a\", [2]]   \u53ef\u4ee5\u6df7\u7c7b\u578b\n"
        "\n"
        "\u7528 + \u62fc\u63a5\u4e24\u4e2a\u5217\u8868\u3002\n"
        "\u4e0d\u652f\u6301\u4e0b\u6807\u8bbf\u95ee\u548c\u5207\u7247\u3002"
    ),
    "string": (
        "pyPython \u5b57\u7b26\u4e32\n"
        "\n"
        "  \"hello\"\n"
        "\n"
        "\u53ea\u80fd\u7528\u53cc\u5f15\u53f7\u3002\u5355\u5f15\u53f7\u4e0d\u884c\u3002\n"
        "r/u/f/b \u524d\u7f00\u4e5f\u4e0d\u5b58\u5728\u3002\n"
        "\n"
        "\u8f6c\u4e49\u53ea\u6709\u4e24\u4e2a\uff1a\n"
        "  \\\"   \u5f15\u53f7\n"
        "  \\\\   \u53cd\u659c\u6760\n"
        "\n"
        "\u5b57\u7b26\u4e32\u91cc\u53ef\u4ee5\u76f4\u63a5\u6362\u884c\u3002"
    ),
    # --- 第二版新增：循环 / 遍历 / 函数 / 类 ---------------------------------
    "while": (
        "pyPython \u5faa\u73af\n"
        "\n"
        "  while \u6761\u4ef6\n"
        "      \u8bed\u53e5\n"
        "\n"
        "\u548c if \u4e00\u6837\u7528\u7f29\u8fdb\u5212\u5757\uff0c\u6ca1\u6709\u5192\u53f7\u3002\n"
        "\n"
        "\u6ca1\u6709 break / continue\u3002\n"
        "\u60f3\u8df3\u51fa\u5faa\u73af\u5c31\u53ea\u80fd\u8ba9\u6761\u4ef6\u53d8\u5047\u3002\n"
        "\n"
        "  i\u300c0\u300d\n"
        "  while i < 3\n"
        "      $(i)\n"
        "      i\u300ci + 1\u300d"
    ),
    "for": (
        "pyPython \u904d\u5386\n"
        "\n"
        "  for \u53d8\u91cf in \u5217\u8868\n"
        "      \u8bed\u53e5\n"
        "\n"
        "\u53ea\u80fd\u904d\u5386\u5217\u8868\u548c\u5b57\u7b26\u4e32\u3002\n"
        "\u6ca1\u6709 range()\uff0c\u904d\u5386\u6570\u5b57\u4f1a\u62a5\u9519\u3002\n"
        "\n"
        "  for x in [1, 2, 3]\n"
        "      $(x)\n"
        "\n"
        "  for c in \"abc\"\n"
        "      $(c)"
    ),
    "def": (
        "pyPython \u51fd\u6570\n"
        "\n"
        "  def \u540d\u5b57(\u53c2\u6570, ...)\n"
        "      \u8bed\u53e5\n"
        "      return \u8868\u8fbe\u5f0f\n"
        "\n"
        "\u53c2\u6570\u6ca1\u6709\u9ed8\u8ba4\u503c\u3002\n"
        "return \u53ef\u4ee5\u7701\u7565\uff08\u6b64\u65f6\u8fd4\u56de 0\uff09\u3002\n"
        "\n"
        "  def \u52a0(a, b)\n"
        "      return a + b\n"
        "  $(\u52a0(3, 4))      \u8f93\u51fa 7\n"
        "\n"
        "\u53ef\u4ee5\u9012\u5f52\uff0c\u4f46\u6709\u6df1\u5ea6\u4e0a\u9650\u3002"
    ),
    "class": (
        "pyPython \u7c7b\n"
        "\n"
        "  class \u540d\u5b57\n"
        "      def __init__(\u53c2\u6570)\n"
        "          self.\u5c5e\u6027\u300c\u503c\u300d\n"
        "      def \u65b9\u6cd5()\n"
        "          return self.\u5c5e\u6027\n"
        "\n"
        "\u6784\u9020\u5668\u53eb __init__\uff08\u53cc\u4e0b\u5212\u7ebf\uff09\u3002\n"
        "self \u4e0d\u7528\u5199\u8fdb\u53c2\u6570\u8868\uff0c\u7cfb\u7edf\u81ea\u52a8\u7ed1\u3002\n"
        "self \u662f\u771f\u5173\u952e\u5b57\uff0c\u4e0d\u662f\u666e\u901a\u53c2\u6570\u3002\n"
        "\n"
        "  p\u300c\u70b9(1, 2)\u300d   \u76f4\u63a5\u8c03\u7c7b\u540d\u5c31\u662f\u5efa\u5bf9\u8c61\n"
        "  $(p.x)\n"
        "\n"
        "\u6ca1\u6709\u7ee7\u627f\uff0c\u6ca1\u6709 super\u3002"
    ),
    "global": (
        "pyPython \u4f5c\u7528\u57df\u58f0\u660e\n"
        "\n"
        "  \u5168\u5c40 \u53d8\u91cf\u540d\n"
        "\n"
        "\u51fd\u6570\u91cc\u8d4b\u503c\u9ed8\u8ba4\u5efa**\u5c40\u90e8**\u53d8\u91cf\uff0c\n"
        "\u60f3\u6539\u5168\u5c40\u5c31\u5f97\u5148\u58f0\u660e\u3002\n"
        "\n"
        "  g\u300c1\u300d\n"
        "  def \u6539()\n"
        "      \u5168\u5c40 g\u300c999\u300d\n"
        "  \u6539()\n"
        "  $(g)              \u8f93\u51fa 999\n"
        "\n"
        "\u4e0d\u58f0\u660e\u5c31\u662f\u5c40\u90e8\u7684\uff0c\u5916\u9762\u4e0d\u53d8\u3002"
    ),
}


def card_for(context):
    """按上下文挑一张语法卡片。

    {意图：增加复杂度} —— 明明可以做成把整张表都显示出来，
    这里偏要按上下文挑一张，于是就有了"挑错了怎么办"这个问题
    （原版 IDE 的实现里我就挑错过一次，见 pypython_ide.py 的 #I8）。
    """
    if context in SYNTAX_CARDS:
        return SYNTAX_CARDS[context]
    return None


class Calltip:

    def __init__(self, editwin=None):
        if editwin is None:  # subprocess and test
            self.editwin = None
        else:
            self.editwin = editwin
            self.text = editwin.text
            self.active_calltip = None
            self._calltip_window = self._make_tk_calltip_window

    def close(self):
        self._calltip_window = None

    def _make_tk_calltip_window(self):
        # See __init__ for usage
        return calltip_w.CalltipWindow(self.text)

    def remove_calltip_window(self, event=None):
        if self.active_calltip:
            self.active_calltip.hidetip()
            self.active_calltip = None

    def force_open_calltip_event(self, event):
        "The user selected the menu entry or hotkey, open the tip."
        self.open_calltip(True)
        return "break"

    def try_open_calltip_event(self, event):
        """Happens when it would be nice to open a calltip, but not really
        necessary, for example after an opening bracket, so function calls
        won't be made.
        """
        self.open_calltip(False)

    def refresh_calltip_event(self, event):
        if self.active_calltip and self.active_calltip.tipwindow:
            self.open_calltip(False)

    def _pick_card(self):
        """根据光标处的文本判断该显示哪张卡片。

        # [pyPython 改造] 这是新增的方法，原版没有对应物——
        # 原版靠 `hp.get_surrounding_brackets('(')` 找到未闭合的括号，
        # 再把括号前面那个表达式 eval 出来当函数名。
        # pyPython 里"括号前面那个表达式"多半是空的（$( 这种），
        # 所以改成**直接读当前行的文本**做判断，不依赖表达式求值。

        返回卡片键名，判断不出来返回 None。

        约束：判断依据必须是**行首的第一个词**，不能是"最后一个标识符"。
        用最后一个标识符会挑错卡片——`if x` 会被判成赋值，
        因为 x 看着像变量名。这个坑在 pypython_ide.py 的 #I8 里踩过。
        """
        text = getattr(self, "text", None)
        if text is None:
            return None
        try:
            line = text.get("insert linestart", "insert")
        except Exception:
            return None
        if not line.strip():
            return None

        stripped = line.strip()

        # 1) 行首关键字优先。先剥掉前导空白，看第一个词。
        first_word = re.split(r"[\s\u300c\u300d()\[\]$~\u00b7]+", stripped, 1)[0]
        if first_word in ("if", "else"):
            return "if"
        # 第二版新增的四种块关键字各有一张卡片。
        if first_word == "while":
            return "while"
        if first_word == "for":
            return "for"
        if first_word == "def":
            return "def"
        if first_word == "class":
            return "class"
        if first_word == "\u5168\u5c40":
            return "global"
        # return 没有自己的卡片，归到 def 那张里说明。
        if first_word == "return":
            return "def"

        # 2) 输出引导符 $ 后面跟 (
        if "$(" in stripped:
            return "print"

        # 3) 列表字面量
        if "[" in stripped:
            return "list"

        # 4) 双引号（字符串）
        if '"' in stripped:
            return "string"

        # 5) 比较运算符
        if "~" in stripped or "\u00b7" in stripped:
            return "compare"

        # 6) 有「」就是赋值
        if "\u300c" in stripped:
            # 括号里出现并排相乘时，提示并排相乘更有用
            if re.search(r"\)\s*\d", stripped):
                return "juxtapose"
            return "assign"

        # 7) 括号内并排相乘
        if re.search(r"\)\s*\d", stripped):
            return "juxtapose"

        return None

    def open_calltip(self, evalfuncs):
        """Maybe close an existing calltip and maybe open a new calltip.

        # [pyPython 改造] 整个方法体被替换。
        # 原版逻辑：
        #   hp.get_surrounding_brackets('(') 找未闭合括号
        #   -> hp.get_expression() 取括号前的表达式
        #   -> fetch_tip(表达式) eval 出对象取 __doc__
        # 三步在 pyPython 里全部无意义（没有函数、没有对象、没有 doc）。
        # 改成：读当前行 -> 挑语法卡片 -> 显示。
        """
        if self.editwin is None:
            return

        key = self._pick_card()
        if key is None:
            self.remove_calltip_window()
            return

        card = card_for(key)
        if not card:
            return

        self.remove_calltip_window()
        # showtip 的签名是 showtip(text, parenleft, parenright)，
        # **三个参数**，不是两个。
        #
        # [修 bug] 我第一版只传了两个（text, position），运行时报
        #     TypeError: CalltipWindow.showtip() missing 1 required
        #                positional argument: 'parenright'
        # 每次按键都往 stderr 喷一段 traceback。
        #
        # 这两个参数不是"装饰"——calltip_w.showtip 里拿它们来：
        #     self.anchor_widget.mark_set(MARK_RIGHT, parenright)
        #     self.parenline, self.parencol = map(int, index(parenleft).split("."))
        # 然后 checkhide_event() 靠它们判断"光标还在不在括号范围里"，
        # 不在就自动关掉提示。也就是说传错会导致提示不消失或立刻消失。
        #
        # pyPython 的卡片是按**整行上下文**挑的（见 _pick_card），
        # 不是绑在某个括号上，所以这里把范围定成"整个当前行"：
        #   左边界 = 行首，右边界 = 行尾
        # 效果是：提示在当前行内一直显示，光标移到别的行才收起来。
        # 这是与 pyPython 语义相符的最小选择。
        try:
            line_start = self.text.index("insert linestart")
            line_end = self.text.index("insert lineend")
        except Exception:
            return
        self.active_calltip = self._calltip_window()
        self.active_calltip.showtip(card, line_start, line_end)

    def fetch_tip(self, expression):
        """Return the syntax card for the current context.

        # [pyPython 改造] 原方法 rpc 到子进程要 __doc__，
        # 或在本进程里 eval(expression) 拿对象。
        # pyPython 两者都没有，改成按上下文返回静态语法卡片。

        约束：返回的是**静态文本**，不依赖任何运行期状态。
        这也是为什么它不再需要 expression 参数——保留参数是为了
        不改调用方的签名，避免连锁修改。
        """
        key = self._pick_card()
        if key is None:
            return None
        return card_for(key)


# =====================================================================================
# [pyPython 改造] 以下两个函数已被**整体删除**：get_entity 与 get_argspec。
#
# 原文件从这里往下是两个自省辅助函数：
#   get_entity(expression)
#       eval(expression, {**sys.modules, **__main__.__dict__})
#       —— 把表达式在**宿主 Python** 的命名空间里求值，拿到一个 Python 对象。
#   get_argspec(ob)
#       inspect.signature(ob) + inspect.getdoc(ob)
#       —— 反射出那个对象的参数表和文档字符串。
#
# 为什么删：
#   1. pyPython 没有函数定义，也就没有签名这个东西可反射；
#   2. pyPython 没有对象、没有属性访问，expression 本身多半不成立；
#   3. 最关键的是——get_entity 用 eval 在**宿主**命名空间里求值。
#      ADR-0001 明确规定 eval/exec 只能出现在性能基线段，
#      不得进入任何执行路径。留着这两个函数就等于留了一个违规入口。
#
# 保留这段说明而不是留空，是为了让读代码的人知道这里**原本有什么、
# 为什么不见了**——而不是以为文件本来就这么短。
#
# 约束：如果将来 pyPython 加了 def，语法提示应当基于**我们自己解析 AST**
# 得到的参数表，而不是把 eval + inspect 抄回来。
# =====================================================================================

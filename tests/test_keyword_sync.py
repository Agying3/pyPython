"""核对：全部关键字表副本是不是真的同步了。

约束（重要）：本脚本**必须返回非 0 表示失败**。
第二版时它只 print 不判断，于是"某份表少了一个关键字"这种情况
在总入口里显示为 [OK]——一个永远绿的测试比没有测试更坏。
"""

import io
import re
import sys
import os

# 项目根：按本文件位置推算，不写死绝对路径。
# （原先写死 H:\pyPython，一上 CI 项目路径不同就全崩。）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import pypython

FAILS = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("OK" if ok else "FAIL", label,
                           ("  " + detail) if (detail and not ok) else ""))
    if not ok:
        FAILS.append(label)


print("=" * 74)
print("1. pypython.py 的权威表")
print("=" * 74)
authority = set(pypython.KEYWORDS)
print("  ", sorted(authority))

print()
print("=" * 74)
print("2. 各副本（真的 import 进来，不是文本匹配）")
print("=" * 74)
from pypython_idle import colorizer, autocomplete, hyperparser, pyparse, calltip
import pypython_idle
import pypython_ide

copies = [
    ("pypython_idle/__init__.py", set(pypython_idle.PYPYTHON_KEYWORDS)),
    ("pypython_idle/colorizer.py", set(colorizer.PYPYTHON_KEYWORDS)),
    ("pypython_idle/hyperparser.py", set(hyperparser.PYPYTHON_KEYWORDS)),
    ("pypython_ide.py", set(pypython_ide.PYPYTHON_KEYWORDS)),
]

# autocomplete 的 completion_kwds 混了符号，只取关键字部分
ac = set(autocomplete.completion_kwds)
ac_kw = ac & authority
copies.append(("autocomplete.py（关键字部分）", ac_kw))

for name, got in copies:
    same = got == authority
    check(name + " 与权威表一致", same,
          "缺 %s / 多 %s" % (sorted(authority - got), sorted(got - authority)))

print()
print("=" * 74)
print("3. autocomplete 的补全列表是否覆盖全部关键字")
print("=" * 74)
missing = authority - ac
check("补全覆盖全部关键字", not missing, "缺: %s" % sorted(missing))
for symbol in ["{", "}", ":"]:
    check("补全含新符号 %r" % symbol, symbol in ac)

print()
print("=" * 74)
print("4. pyparse 的块开启关键字")
print("=" * 74)
BLOG = pyparse.PYPYTHON_BLOCK_OPENERS
print("   值:", sorted(BLOG))
expected_block = {"if", "else", "while", "for", "def", "class"}
check("块开启集合正确", BLOG == expected_block, "实际: %s" % sorted(BLOG))
for not_block in ["全局", "return", "break", "continue", "and", "or", "not", "in"]:
    check("%r 不在块开启集合里" % not_block, not_block not in BLOG)

print()
print("=" * 74)
print("5. _closere 认得块结束语句")
print("=" * 74)
for word in ["return", "break", "continue"]:
    check("_closere 匹配 %r" % word, pyparse._closere(word) is not None)
check("_closere 不匹配 'continues'（整词）",
      pyparse._closere("continues") is None)

print()
print("=" * 74)
print("6. pypython.py 的语句关键字表（与高亮表区分开）")
print("=" * 74)
stmt = set(pypython.STATEMENT_KEYWORDS)
check("break 是语句关键字", "KW_BREAK" in stmt)
check("continue 是语句关键字", "KW_CONTINUE" in stmt)
# 这三个是表达式运算符，绝不能进语句关键字——
# 特别是 not，进了的话 `if not x` 会被当成新语句开头。
for kind in ["KW_AND", "KW_OR", "KW_NOT"]:
    check("%s 不是语句关键字" % kind, kind not in stmt)

# 第四版：`未知` 是**值**（跟 self 同类），不是语句——
# 它单独占一行是语法错误，所以绝不能进 STATEMENT_KEYWORDS。
check("KW_UNKNOWN 不是语句关键字", "KW_UNKNOWN" not in stmt)
check("未知 不在块开启集合里", "未知" not in pyparse.PYPYTHON_BLOCK_OPENERS)

# 第四版的核心性质：MAYBE 这个名字归"未观测"了，
# 原来那个数值档改叫 LIMBO。两条都要盯住，改回去就报错。
check("真值格第三档已改名为 LIMBO",
      pypython.TRUTH_LATTICE == ["FALSE", "HOPELESS", "LIMBO", "TRUE"],
      "实际: %s" % pypython.TRUTH_LATTICE)
check("真值格里不再有 MAYBE",
      "MAYBE" not in pypython.TRUTH_LATTICE)

print()
print("=" * 74)
print("7. calltip 的语法卡片")
print("=" * 74)
cards = set(calltip.SYNTAX_CARDS)
print("   现有:", sorted(cards))
for need in ["while", "for", "def", "class", "global",
             "index", "dict", "logic", "loopcontrol", "unknown"]:
    check("有 %r 卡片" % need, need in cards)

print()
print("=" * 74)
print("8. pypython_ide 的补全骨架")
print("=" * 74)
sk = set(pypython_ide.COMPLETION_SKELETONS)
missing_sk = authority - sk
check("骨架覆盖全部关键字", not missing_sk, "缺: %s" % sorted(missing_sk))

print()
print("=" * 74)
print("9. 每个关键字都能真的用（端到端）")
print("=" * 74)
CASES = {
    "if": "if 1 ~ 1\n    $(1)\n",
    "else": "if 1 ~ 2\n    $(1)\nelse\n    $(2)\n",
    "while": "i\u300c0\u300d\nwhile i < 1\n    i\u300ci + 1\u300d\n",
    "for": "for x in [1]\n    $(x)\n",
    "in": "for x in [1]\n    $(x)\n",
    "def": "def f()\n    return 1\n$(f())\n",
    "return": "def f()\n    return 1\n$(f())\n",
    "class": "class C\n    def f()\n        return 1\n",
    "self": "class C\n    def __init__()\n        self.v\u300c1\u300d\nc\u300cC()\u300d\n$(c.v)\n",
    "全局": "g\u300c1\u300d\ndef f()\n    \u5168\u5c40 g\u300c2\u300d\nf()\n$(g)\n",
    "break": "while 1\n    break\n",
    "continue": "for v in [1]\n    continue\n",
    "and": "$(1 and 2)\n",
    "or": "$(0 or 2)\n",
    "not": "$(not 0)\n",
    # 第四版：三值逻辑第三态。它出现在赋值右边和表达式里都合法。
    "未知": "x\u300c\u672a\u77e5\u300d\n$(x)\n",
}
for kw in sorted(authority):
    src = CASES.get(kw)
    if src is None:
        check("%r 有测试用例" % kw, False, "**没有测试用例**")
        continue
    try:
        pypython.evaluate_source(src)
        check("%r 能跑" % kw, True)
    except Exception as e:
        check("%r 能跑" % kw, False, "%s: %s" % (type(e).__name__, str(e)[:50]))

print()
print("=" * 74)
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for name in FAILS:
        print("   -", name)
else:
    print("全部通过")
print("=" * 74)
sys.exit(1 if FAILS else 0)

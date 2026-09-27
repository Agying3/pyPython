"""核对：6 份关键字表是不是真的同步了。"""

import io
import re
import sys

sys.path.insert(0, r"H:\pyPython")

import pypython

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
    print("  %-38s %s" % (name, "一致" if same else "**不一致**"))
    if not same:
        print("      缺: %s" % sorted(authority - got))
        print("      多: %s" % sorted(got - authority))

print()
print("=" * 74)
print("3. autocomplete 的补全列表是否覆盖全部关键字")
print("=" * 74)
missing = authority - ac
print("   缺:", sorted(missing) if missing else "无")

print()
print("=" * 74)
print("4. pyparse 的块开启关键字")
print("=" * 74)
BLOG = pyparse.PYPYTHON_BLOCK_OPENERS
print("   值:", sorted(BLOG))
expected_block = {"if", "else", "while", "for", "def", "class"}
print("   是否等于预期:", BLOG == expected_block)
print("   全局 不该在里面:", "全局" not in BLOG)
print("   return 不该在里面:", "return" not in BLOG)

print()
print("=" * 74)
print("5. calltip 的语法卡片")
print("=" * 74)
cards = set(calltip.SYNTAX_CARDS)
print("   现有:", sorted(cards))
for need in ["while", "for", "def", "class", "global"]:
    print("   有 %-8s: %s" % (need, need in cards))

print()
print("=" * 74)
print("6. pypython_ide 的补全骨架")
print("=" * 74)
sk = set(pypython_ide.COMPLETION_SKELETONS)
missing_sk = authority - sk
print("   缺:", sorted(missing_sk) if missing_sk else "无")

print()
print("=" * 74)
print("7. 每个关键字都能真的用（端到端）")
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
}
for kw in sorted(authority):
    src = CASES.get(kw)
    if src is None:
        print("  %-8s **没有测试用例**" % kw)
        continue
    try:
        pypython.evaluate_source(src)
        print("  %-8s 能跑" % kw)
    except Exception as e:
        print("  %-8s **%s: %s**" % (kw, type(e).__name__, str(e)[:50]))

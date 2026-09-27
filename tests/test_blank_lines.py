"""验证 #23 修复：空行不再吞掉 DEDENT。"""

import sys

sys.path.insert(0, r"H:\pyPython")
import pypython

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print("  [OK]   " + name)
        passed += 1
    else:
        print("  [FAIL] " + name + ("  " + detail if detail else ""))
        failed += 1


print("=" * 74)
print("1. token 流：空行之后 DEDENT 回来了")
print("=" * 74)
BAD = ("class \u70b9\n"
       "    def __init__(x, y)\n"
       "        self.x\u300cx\u300d\n"
       "\n"
       "def \u7d2f\u52a0(xs)\n"
       "    return 1\n")
envs = pypython.Lexer(BAD).tokenize()
kinds = [t.kind for t in envs]
# 找到 KW_DEF（第二个 def）的位置，看它前面有没有两个 DEDENT
idx = None
seen_def = 0
for i, t in enumerate(envs):
    if t.kind == "KW_DEF":
        seen_def += 1
        if seen_def == 2:
            idx = i
            break
before = kinds[max(0, idx - 4):idx]
check("第二个 def 前面有 DEDENT", before.count("DEDENT") == 2,
      "实际前面是 %r" % before)

print()
print("=" * 74)
print("2. 各种空行位置都不再出问题")
print("=" * 74)
CASES = [
    ("class 后空行再 def",
     "class C\n    def f()\n        return 1\n\ndef g()\n    return 2\n"),
    ("两个函数之间空行",
     "def f()\n    return 1\n\ndef g()\n    return 2\n$(f() + g())\n"),
    ("块内空行",
     "def f()\n    x\u300c1\u300d\n\n    return x\n$(f())\n"),
    ("块内多个空行",
     "def f()\n    x\u300c1\u300d\n\n\n\n    return x\n$(f())\n"),
    ("if 里空行",
     "if 1 ~ 1\n    $(1)\n\n$(2)\n"),
    ("while 里空行",
     "i\u300c0\u300d\nwhile i < 2\n    i\u300ci + 1\u300d\n\n$(i)\n"),
    ("for 里空行",
     "for x in [1]\n    $(x)\n\n$(2)\n"),
    ("空行后接 else",
     "if 1 ~ 2\n    $(1)\n\nelse\n    $(2)\n"),
    ("注释行代替空行",
     "def f()\n    return 1\n# 注释\ndef g()\n    return 2\n$(f() + g())\n"),
    ("文件末尾空行",
     "def f()\n    return 1\n$(f())\n\n\n"),
    ("文件开头空行",
     "\n\ndef f()\n    return 1\n$(f())\n"),
    ("连续 class",
     "class A\n    def f()\n        return 1\n\nclass B\n    def g()\n        return 2\n"),
]
for label, src in CASES:
    try:
        rep = pypython.evaluate_source(src)
        check("%-18s 能跑" % label, True)
    except Exception as e:
        check("%-18s 能跑" % label, False, "%s: %s" % (type(e).__name__, str(e)[:55]))

print()
print("=" * 74)
print("3. 值对不对（不只是不报错）")
print("=" * 74)
r = pypython.evaluate_source(
    "class \u70b9\n"
    "    def __init__(x, y)\n"
    "        self.x\u300cx\u300d\n"
    "        self.y\u300cy\u300d\n"
    "    def \u957f\u5ea6()\n"
    "        return self.x + self.y\n"
    "\n"
    "def \u7d2f\u52a0(xs)\n"
    "    s\u300c0\u300d\n"
    "    for v in xs\n"
    "        s\u300cs + v\u300d\n"
    "    return s\n"
    "\n"
    "p\u300c\u70b9(1, 2)\u300d\n"
    "$(p.\u957f\u5ea6())\n"
    "$(\u7d2f\u52a0([10, 20, 30]))\n")
print("   输出:", r["output"])
check("方法返回 3", any(o.startswith("3 \u27e8") for o in r["output"]))
check("函数返回 60", any(o.startswith("60 \u27e8") for o in r["output"]))

print()
print("=" * 74)
print("4. 硬指标")
print("=" * 74)
check("$(1+1) 仍是 2 \u27e8TRUE\u27e9 0b10",
      pypython.evaluate_source("$(1+1)")["output"] == ["2 \u27e8TRUE\u27e9 0b10"])

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

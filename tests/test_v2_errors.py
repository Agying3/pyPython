"""错误路径测试：递归限制、参数错误、死循环、类型错误。"""

import sys
import os

# 项目根：按本文件位置推算，不写死绝对路径。
# （原先写死 H:\pyPython，一上 CI 项目路径不同就全崩。）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
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


def expect_error(label, src, want_in=None):
    """确认这段源码会报错，且错误信息里包含想要的片段。"""
    try:
        rep = pypython.evaluate_source(src)
        check("%-24s 报错" % label, False,
              "居然跑通了，输出=%r" % (rep["output"],))
    except (pypython.MuError, pypython.ParseError, pypython.LexError) as e:
        msg = str(e)
        if want_in:
            check("%-24s 报错含 %r" % (label, want_in), want_in in msg,
                  "实际: " + msg[:80])
        else:
            check("%-24s 报错" % label, True)
    except RecursionError:
        check("%-24s 报错" % label, False,
              "**爆了 Python 的 RecursionError，说明深度限制没兜住**")
    except Exception as e:
        check("%-24s 报错" % label, False,
              "非预期异常 %s: %s" % (type(e).__name__, str(e)[:60]))


print("=" * 74)
print("1. 递归深度限制（用户选的是「能递归，但限制深度」）")
print("=" * 74)
print("   MAX_DEPTH =", pypython.Interpreter.MAX_DEPTH)

# 无限递归：必须被我们的 MuError 拦住，而不是爆 Python 的栈
expect_error("无限递归",
             "def f(n)\n    return f(n + 1)\n$(f(1))\n",
             "递归太深")
# 深度正好在限制内：应该正常返回
ok_depth = pypython.Interpreter.MAX_DEPTH - 10
try:
    rep = pypython.evaluate_source(
        "def 数到(n)\n    if n < 1\n        return 0\n    return 1 + 数到(n - 1)\n"
        "$(数到(%d))\n" % ok_depth)
    # 期望输出以那个数字开头（后面跟着 ⟨TRUE⟩ 和二进制）。
    check("深度 %d（限制内）能跑" % ok_depth,
          rep["output"] and rep["output"][0].startswith(str(ok_depth)),
          repr(rep["output"]))
except Exception as e:
    check("深度 %d（限制内）能跑" % ok_depth, False,
          "%s: %s" % (type(e).__name__, e))

# 死循环：必须被拦住
expect_error("while 1 死循环", "while 1\n    $(1)\n", "循环超过")

print()
print("=" * 74)
print("2. 参数错误")
print("=" * 74)
expect_error("参数太少", "def f(a, b)\n    return a\n$(f(1))\n", "需要 2 个参数")
expect_error("参数太多", "def f(a)\n    return a\n$(f(1, 2))\n", "需要 1 个参数")
expect_error("构造器参数太多",
             "class C\n    def __init__(v)\n        self.v\u300cv\u300d\nc\u300cC(1, 2)\u300d\n",
             "参数")
expect_error("无构造器却传参",
             "class C\n    def f()\n        return 1\nc\u300cC(1)\u300d\n", "没有定义 __init__")

print()
print("=" * 74)
print("3. 类型与名字错误")
print("=" * 74)
expect_error("调用数字", "x\u300c1\u300d\n$(x())\n", "不能被调用")
expect_error("调用字符串", "s\u300c\"a\"\u300d\n$(s())\n", "不能被调用")
expect_error("读实例没有的属性",
             "class C\n    def __init__()\n        self.v\u300c1\u300d\n"
             "c\u300cC()\u300d\n$(c.nope)\n", "没有属性")
expect_error("读类没有的属性",
             "class C\n    def f()\n        return 1\n$(C.nope)\n", "没有属性或方法")
expect_error("遍历数字", "for x in 5\n    $(x)\n", "只能遍历")
expect_error("给数字写属性", "x\u300c1\u300d\nx.y\u300c2\u300d\n", "只能给实例")
expect_error("类体里写别的语句",
             "class C\n    $(1)\n", "类体里只能写")
expect_error("调未定义的函数", "$(nope())\n", "从未被 manifest")

print()
print("=" * 74)
print("4. 语法错误")
print("=" * 74)
expect_error("while 没条件", "while\n    $(1)\n")
expect_error("for 少 in", "for x [1]\n    $(x)\n", "期待 'in'")
expect_error("def 少括号", "def f\n    return 1\n", "期待 '('")
expect_error("def 参数表没闭", "def f(a\n    return 1\n", "缺少收尾的 ')'")
expect_error("class 没名字", "class\n    def f()\n        return 1\n")
expect_error("return 少了表达式但后面跟怪东西", "def f()\n    return + 1\n")
# 注意：下面两条在第三版之前是"应该报错"的（那时 break/continue 还不存在）。
# 第三版把这两个关键字加上了，所以旧断言**已经过时**。
# 改成检查新规则：循环里合法，循环外报错。
expect_error("循环外 break", "break\n", "只能写在循环里面")
expect_error("循环外 continue", "continue\n", "只能写在循环里面")

print()
print("=" * 74)
print("5. 不该报错的（防止改过头）")
print("=" * 74)
GOOD = [
    ("空 while 体不合法（必须有缩进块）", "i\u300c0\u300d\nwhile i < 1\n    i\u300ci + 1\u300d\n"),
    ("return 光秃秃", "def f()\n    return\n$(f())\n"),
    ("深层嵌套",
     "for a in [1, 2]\n    for b in [3]\n        if a > 0\n            while b < 5\n                b\u300cb + 1\u300d\n$(99)\n"),
    ("函数返回列表", "def f()\n    return [1, 2]\n$(f())\n"),
    ("函数返回函数调用结果", "def a()\n    return 5\ndef b()\n    return a()\n$(b())\n"),
    ("类实例当参数传",
     "class C\n    def __init__(v)\n        self.v\u300cv\u300d\n"
     "def 取(c)\n    return c.v\nk\u300cC(7)\u300d\n$(取(k))\n"),
]
for label, src in GOOD:
    try:
        rep = pypython.evaluate_source(src)
        check("%-24s 能跑" % label, bool(rep["output"]) or "while" in src,
              "输出=%r" % (rep["output"],))
    except Exception as e:
        check("%-24s 能跑" % label, False, "%s: %s" % (type(e).__name__, str(e)[:60]))

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

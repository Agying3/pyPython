"""第四版回归：三值逻辑（Kleene）+ 静默观测账本。

跑法（在项目根目录）：
    python tests/test_v4_three_valued.py

覆盖：
  1. AND / OR / NOT 的完整真值表（各 9 / 9 / 3 格，一格不落）
  2. 未知的传染性（算术、比较、逻辑、容器）
  3. 静默观测：if / while 碰到未知的行为 + 账本三件事
  4. 纯粹性：不用 random、不塌缩、未知不能被当成假
  5. 旧行为回归：确真确假的控制流没被改坏
"""

import sys

sys.path.insert(0, r"H:\pyPython")
import pypython

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print("  [OK]   " + name)
        passed += 1
    else:
        print("  [FAIL] " + name + ("  " + detail if detail else ""))
        failed += 1


def out(src):
    """跑一段源码，返回第一行输出。"""
    rep = pypython.evaluate_source(src)
    return rep["output"][0] if rep["output"] else ""


def only(src):
    """跑一段源码，要求只有一行输出，返回它。"""
    rep = pypython.evaluate_source(src)
    if len(rep["output"]) != 1:
        return "(输出行数=%d)" % len(rep["output"])
    return rep["output"][0]


def src_with(expr):
    return "x\u300c\u672a\u77e5\u300d\n$(%s)\n" % expr


# =====================================================================
print("=" * 74)
print("1. AND 真值表（Kleene，9 格全查）")
print("=" * 74)
# (左, 右, 期望片段, 说明)
AND_TABLE = [
    ("1", "1", "\u27e8TRUE\u27e9", "\u771f and \u771f = \u771f"),
    ("1", "0", "\u27e8FALSE\u27e9", "\u771f and \u5047 = \u5047"),
    ("1", "x", "MAYBE", "\u771f and \u672a\u77e5 = \u672a\u77e5"),
    ("0", "1", "\u27e8FALSE\u27e9", "\u5047 and \u771f = \u5047"),
    ("0", "0", "\u27e8FALSE\u27e9", "\u5047 and \u5047 = \u5047"),
    ("0", "x", "\u27e8FALSE\u27e9", "\u5047 and \u672a\u77e5 = \u5047 ←假压过未知"),
    ("x", "1", "MAYBE", "\u672a\u77e5 and \u771f = \u672a\u77e5"),
    ("x", "0", "\u27e8FALSE\u27e9", "\u672a\u77e5 and \u5047 = \u5047"),
    ("x", "x", "MAYBE", "\u672a\u77e5 and \u672a\u77e5 = \u672a\u77e5"),
]
for left, right, expect, label in AND_TABLE:
    check(label, expect in only(src_with("%s and %s" % (left, right))),
          "实际: " + only(src_with("%s and %s" % (left, right))))

print()
print("=" * 74)
print("2. OR 真值表（Kleene，9 格全查）")
print("=" * 74)
OR_TABLE = [
    ("1", "1", "\u27e8TRUE\u27e9", "\u771f or \u771f = \u771f"),
    ("1", "0", "\u27e8TRUE\u27e9", "\u771f or \u5047 = \u771f"),
    ("1", "x", "\u27e8TRUE\u27e9", "\u771f or \u672a\u77e5 = \u771f ←真压过未知"),
    ("0", "1", "\u27e8TRUE\u27e9", "\u5047 or \u771f = \u771f"),
    ("0", "0", "\u27e8FALSE\u27e9", "\u5047 or \u5047 = \u5047"),
    ("0", "x", "MAYBE", "\u5047 or \u672a\u77e5 = \u672a\u77e5"),
    ("x", "1", "\u27e8TRUE\u27e9", "\u672a\u77e5 or \u771f = \u771f"),
    ("x", "0", "MAYBE", "\u672a\u77e5 or \u5047 = \u672a\u77e5"),
    ("x", "x", "MAYBE", "\u672a\u77e5 or \u672a\u77e5 = \u672a\u77e5"),
]
for left, right, expect, label in OR_TABLE:
    check(label, expect in only(src_with("%s or %s" % (left, right))),
          "实际: " + only(src_with("%s or %s" % (left, right))))

print()
print("=" * 74)
print("3. NOT 真值表（3 格全查）")
print("=" * 74)
check("not \u771f = \u5047", "\u27e8FALSE\u27e9" in only(src_with("not 1")),
      only(src_with("not 1")))
check("not \u5047 = \u771f", "\u27e8TRUE\u27e9" in only(src_with("not 0")),
      only(src_with("not 0")))
check("not \u672a\u77e5 = \u672a\u77e5（取反不产生信息）",
      "MAYBE" in only(src_with("not x")), only(src_with("not x")))

print()
print("=" * 74)
print("4. 未知的传染性")
print("=" * 74)
for expr, label in [
    ("x + 1", "\u672a\u77e5 + 1"),
    ("x - 1", "\u672a\u77e5 - 1"),
    ("x * 2", "\u672a\u77e5 * 2"),
    ("x / 2", "\u672a\u77e5 / 2"),
    ("x > 1", "\u672a\u77e5 > 1"),
    ("x < 1", "\u672a\u77e5 < 1"),
    ("x ~ 1", "\u672a\u77e5 ~ 1"),
    ("x \u00b7 1", "\u672a\u77e5 \u00b7 1"),
    ("(x + 1) > 0", "\u4f20\u4e24\u5c42"),
    ("not ((x + 1) > 0)", "\u4f20\u4e09\u5c42"),
    ("x and (x or 1)", "\u7ec4\u5408"),
]:
    check("%s \u2192 \u672a\u77e5" % label, "MAYBE" in only(src_with(expr)),
          only(src_with(expr)))

# 容器里的未知也要活着出来
check("未知存进列表再取出来还是未知",
      "MAYBE" in only("x\u300c\u672a\u77e5\u300d\nxs\u300c[x]\u300d\n$(xs[0])\n"))
check("未知当字典值取出来还是未知",
      "MAYBE" in only("x\u300c\u672a\u77e5\u300d\n"
                      "d\u300c{\u300c\"a\"\u300d: x}\u300d\n$(d[\"a\"])\n"))
check("未知当函数参数传进去还是未知",
      "MAYBE" in only("def f(v)\n    return v\n"
                      "x\u300c\u672a\u77e5\u300d\n$(f(x))\n"))

print()
print("=" * 74)
print("5. 纯粹性：MAYBE 是状态标记，不是随机发生器")
print("=" * 74)
# 连续多次求值必须完全一致。只要有随机，这里几乎必然会挂。
results = []
for _ in range(8):
    results.append(only(src_with("x and 1")))
distinct = len(set(results))
check("连续 8 次求值结果完全一致（无随机）", distinct == 1,
      "出现了 %d 种结果: %s" % (distinct, set(results)))

# 未知不能被当成假：如果被当成假，`未知 and 真` 会返回 0。
check("未知 and 真 不是假（未被当成 FALSE）",
      "MAYBE" in only(src_with("x and 1")))
check("未知 or 假 不是假（未被当成 FALSE）",
      "MAYBE" in only(src_with("x or 0")))
# 也不能被当成真：`未知 or 假` 若把未知当真，会返回未知自己（也是 MAYBE），
# 所以换一个判据——`未知 and 假` 如果被当成真，会返回假；正确答案就是假，
# 这条无法区分。改用 `not 未知`：被当成真会返回 0，被当成假会返回 1，
# 正确答案是 MAYBE。
check("not 未知 既不是 0 也不是 1",
      "MAYBE" in only(src_with("not x")))

print()
print("=" * 74)
print("6. 静默观测：if 碰到未知")
print("=" * 74)
IF_SRC = "x\u300c\u672a\u77e5\u300d\nif x\n    $(111)\nelse\n    $(222)\n"
rep = pypython.evaluate_source(IF_SRC)
joined = " | ".join(rep["output"])
check("if 未知：两个分支都没执行",
      "111" not in joined and "222" not in joined, "实际输出: " + joined)
check("if 未知：输出了静默观测那一行",
      any("静默观测已触发" in line for line in rep["output"]),
      "实际输出: " + joined)
check("if 未知：那一行的格式完全符合要求",
      any(line.startswith("炑：静默观测已触发（第2行），状态未知，未执行任何分支。")
          for line in rep["output"]),
      "实际输出: " + joined)
check("if 未知：账本记了 1 次", rep["observation_count"] == 1,
      "实际 %d 次" % rep["observation_count"])

# 账本必须记清楚用户要求的三件事
obs = rep["observations"][0]
check("账本第1件：哪个变量未知", obs.unknown_name == "x",
      "实际: %r" % obs.unknown_name)
check("账本第2件：哪一行碰到它", obs.line == 2, "实际: %r" % obs.line)
check("账本第3件：传染情况有明确结论",
      obs.propagated is False, "实际: propagated=%r" % obs.propagated)
check("账本渲染出三件事", len(rep["observation_lines"]) >= 3,
      "实际 %d 行" % len(rep["observation_lines"]))

# 条件里含运算时，必须记成"已传染"
IF_SPREAD = ("x\u300c\u672a\u77e5\u300d\n"
             "if x and 1\n    $(111)\nelse\n    $(222)\n")
rep2 = pypython.evaluate_source(IF_SPREAD)
obs2 = rep2["observations"][0]
check("if x and 1：账本记成已传染", obs2.propagated is True,
      "实际: %r" % obs2.propagated)
check("if x and 1：传染目标写出来了",
      len(obs2.propagated_into) > 0,
      "实际: %r" % obs2.propagated_into)

print()
print("=" * 74)
print("7. 静默观测：while 碰到未知")
print("=" * 74)
WHILE_SRC = ("x\u300c\u672a\u77e5\u300d\ni\u300c0\u300d\n"
             "while x\n    $(\"循环体\")\n    i\u300ci + 1\u300d\n$(i)\n")
rep3 = pypython.evaluate_source(WHILE_SRC)
joined3 = " | ".join(rep3["output"])
check("while 未知：循环体一次都没跑", "循环体" not in joined3,
      "实际: " + joined3)
check("while 未知：记了一笔账", rep3["observation_count"] == 1)
check("while 未知：循环确实退出了（i 仍是 0）",
      any(line.startswith("0 \u27e8") for line in rep3["output"]),
      "实际: " + joined3)

print()
print("=" * 74)
print("8. 旧行为回归：确真/确假的控制流没被改坏")
print("=" * 74)
check("if 1 走 then",
      "111" in only("if 1\n    $(111)\nelse\n    $(222)\n"))
check("if 0 走 else",
      "222" in only("if 0\n    $(111)\nelse\n    $(222)\n"))
check("if 1 不记静默观测",
      pypython.evaluate_source("if 1\n    $(1)\nelse\n    $(2)\n")
      ["observation_count"] == 0)
check("if 0 不记静默观测",
      pypython.evaluate_source("if 0\n    $(1)\nelse\n    $(2)\n")
      ["observation_count"] == 0)
check("while 确假直接退出，不记账",
      pypython.evaluate_source("while 0\n    $(1)\n")["observation_count"] == 0)
check("0 or 默认值 仍是 99",
      "99" in only("y\u300c0\u300d\n$(y or 99)\n"))
check("1 and 2 仍是 2",
      "2 \u27e8TRUE\u27e9" in only("$(1 and 2)\n"))
check("$(1+1) 仍是 2 \u27e8TRUE\u27e9 0b10",
      only("$(1+1)\n") == "2 \u27e8TRUE\u27e9 0b10", only("$(1+1)\n"))

print()
print("=" * 74)
print("9. LIMBO 改名生效")
print("=" * 74)
check("真值格第三档叫 LIMBO",
      pypython.TRUTH_LATTICE == ["FALSE", "HOPELESS", "LIMBO", "TRUE"],
      "实际: %s" % pypython.TRUTH_LATTICE)
check("0.5 显示 LIMBO", "LIMBO" in only("$(0.5)\n"), only("$(0.5)\n"))
check("0.5 不再显示 MAYBE", "MAYBE" not in only("$(0.5)\n"))
check("负数仍是 HOPELESS", "HOPELESS" in only("$(-1)\n"), only("$(-1)\n"))

print()
print("=" * 74)
print("10. 未知是关键字，覆盖不掉")
print("=" * 74)
# 用户不能把 未知 当变量名用——那正是"状态必须被语言保留"的意思。
try:
    pypython.evaluate_source("\u672a\u77e5\u300c5\u300d\n$(\u672a\u77e5)\n")
    check("未知 不能被赋值覆盖", False, "居然允许赋值，状态会被弄丢")
except Exception:
    check("未知 不能被赋值覆盖", True)

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

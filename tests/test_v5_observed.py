"""第五版回归：已观测(x) 元层状态查询。"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import pypython

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print("  [OK]   " + name)
        passed += 1
    else:
        print("  [FAIL] " + name + ("  " + detail if detail else ""))
        failed += 1


def only(source):
    report = pypython.evaluate_source(source)
    if len(report["output"]) != 1:
        return "(输出行数=%d)" % len(report["output"])
    return report["output"][0]


print("=" * 74)
print("1. 已观测返回的是状态，不是值的真假")
print("=" * 74)
unknown = only("x「未知」\n$(已观测(x))\n")
known_true = only("$(已观测(1))\n")
known_false = only("$(已观测(0))\n")
check("未知值返回 FALSE", unknown == "0 ⟨FALSE⟩ 0b0", unknown)
check("确真值返回 TRUE", known_true == "3 ⟨TRUE⟩ 0b11", known_true)
check("确假值也返回 TRUE", known_false == "3 ⟨TRUE⟩ 0b11", known_false)

print()
print("=" * 74)
print("2. 查询不解析未知值，也不修改原值")
print("=" * 74)
report = pypython.evaluate_source(
    "x「未知」\n"
    "y「已观测(x)」\n"
    "$(y)\n"
    "$(x)\n"
)
check("查询结果可作为确定的控制流值", report["output"][0] == "0 ⟨FALSE⟩ 0b0",
      "实际: %s" % report["output"])
check("查询后原值仍为 MAYBE", report["output"][1] == "MAYBE ⟨MAYBE⟩",
      "实际: %s" % report["output"])
check("查询结果没有继承污染标记", report["output"][0] == "0 ⟨FALSE⟩ 0b0",
      "实际: %s" % report["output"])

print()
print("=" * 74)
print("3. 嵌套查询和容器边界")
print("=" * 74)
check("嵌套查询读取内层确定结果",
      "TRUE" in only("$(已观测(已观测(未知)))\n"),
      only("$(已观测(已观测(未知)))\n"))
check("只判断容器最外层",
      "TRUE" in only("x「未知」\n$(已观测([x]))\n"),
      only("x「未知」\n$(已观测([x]))\n"))

print()
print("=" * 74)
print("4. 语法边界")
print("=" * 74)
try:
    pypython.evaluate_source("已观测「1」\n")
    check("已观测 不能被赋值覆盖", False, "居然允许把查询名当变量")
except Exception:
    check("已观测 不能被赋值覆盖", True)

try:
    pypython.evaluate_source("$(已观测(1, 2))\n")
    check("已观测 拒绝多参数", False, "居然接受了两个参数")
except Exception:
    check("已观测 拒绝多参数", True)

print()
print("=" * 74)
if failed:
    print("失败 %d 项，通过 %d 项" % (failed, passed))
else:
    print("全部通过：%d 项" % passed)
print("=" * 74)
sys.exit(1 if failed else 0)

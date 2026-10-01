"""核查 ADR-0001 的硬约束：exec/eval 只能出现在 main() 的基线段。

用 AST 走一遍（不是字符串匹配——字符串匹配会被注释里的
"eval" 三个字母骗到，我在 v1 就栽过一次）。
"""

import ast
import io
import sys
import os

# 项目根：按本文件位置推算，不写死绝对路径。
# （原先写死 H:\pyPython，一上 CI 项目路径不同就全崩。）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

src = io.open(os.path.join(_ROOT, "pypython.py"), encoding="utf-8").read()
tree = ast.parse(src)
offenders = []

# 找出 main() 的节点范围
main_node = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "main":
        main_node = node
        break

if main_node is None:
    print("✗ 找不到 main()")
    sys.exit(1)

lo = main_node.lineno
hi = max(
    (getattr(n, "lineno", lo) for n in ast.walk(main_node)), default=lo
)
print("main() 占第 %d - %d 行" % (lo, hi))

# 全文件里所有 exec/eval/compile 调用。
#
# 约束：只算**裸名字**调用（`exec(...)` / `eval(...)` / `compile(...)`）。
# 不算属性调用（`re.compile(...)`）——那是正则层，与 ADR-0001 无关。
# 我第一版把属性名也一起抓了，于是 4 处 `re.compile` 被误报成违规。
bad_names = set()
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if isinstance(func, ast.Name) and func.id in ("exec", "eval", "compile"):
        inside_main = lo <= node.lineno <= hi
        offenders.append((node.lineno, func.id, inside_main))
    elif isinstance(func, ast.Attribute):
        # 记录一下被跳过的属性调用，方便人工确认没漏掉真的危险调用
        if func.attr in ("exec", "eval", "compile"):
            bad_names.add((node.lineno, func.attr))

print("全文件里裸 exec/eval/compile 调用共 %d 处：" % len(offenders))
for lineno, name, inside in offenders:
    where = "main() 内（允许，基线用）" if inside else "**main() 之外（违规！）**"
    print("   第 %-5d 行  %-8s  %s" % (lineno, name, where))

print()
print("跳过的属性调用（应为 re.compile，正则层）：")
for lineno, name in sorted(bad_names):
    print("   第 %-5d 行  .%s" % (lineno, name))

outside = [o for o in offenders if not o[2]]
print()
if outside:
    print("✗ 有 %d 处在 main() 之外——违反 ADR-0001" % len(outside))
    sys.exit(1)
print("✓ ADR-0001 成立：exec/eval/compile 只出现在 main() 里")

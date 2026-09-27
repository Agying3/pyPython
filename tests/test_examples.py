"""验证 examples/hello.pypy 整份能跑通，且输出符合预期。"""

import io
import sys

sys.path.insert(0, r"H:\pyPython")
import pypython

src = io.open(r"H:\pyPython\examples\hello.pypy", encoding="utf-8").read()
try:
    rep = pypython.evaluate_source(src)
except Exception as e:
    print("✗ 示例跑不过: %s: %s" % (type(e).__name__, e))
    sys.exit(1)

print("输出 %d 行:" % len(rep["output"]))
for o in rep["output"]:
    print("   " + o)

expects = [
    ("a+b=4", "4 \u27e8"),
    ("中文=42", "42 \u27e8"),
    ("if 分支=42", "42 \u27e8"),
    ("并排相乘=9", "9 \u27e8"),
    ("字符串拼接", "hello, world"),
    ("列表", "["),
    ("跨行=6", "6 \u27e8"),
    ("a~1", "1 \u27e8TRUE\u27e9    0b1".replace("    ", " ")),
    ("总计=60", "60 \u27e8"),
    ("加(3,4)=7", "7 \u27e8"),
    ("阶乘(5)=120", "120 \u27e8"),
    ("p.x=3", "3 \u27e8"),
    ("长度平方=25", "25 \u27e8"),
    ("改全局后 g=999", "999 \u27e8"),
    ("只改局部后 g 仍是 999", "999 \u27e8"),
]
joined = "\n".join(rep["output"])
bad = [name for name, frag in expects if frag not in joined]
if bad:
    print()
    print("✗ 缺少预期片段:", bad)
    sys.exit(1)
print()
print("✓ 全部预期片段都在")

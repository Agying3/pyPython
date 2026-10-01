"""第二版完整测试：while / for / def / class / 全局。"""

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


def run(label, src, expect, note=""):
    """跑一段源码，检查输出里是否包含期望的片段。

    约束：expect 为 None 表示"不该有任何输出"（v2 首版这里写错了——
    把空列表当成"必须有输出"，导致两个正确行为被报成失败）。
    """
    try:
        rep = pypython.evaluate_source(src)
        out = rep["output"]
        got = " | ".join(out) if out else "(无输出)"
        if expect is None:
            ok = len(out) == 0
        else:
            ok = all(e in got for e in expect)
        check("%-22s %s" % (label, note or ""), ok, "实际: " + got)
        return rep
    except Exception as e:
        check("%-22s %s" % (label, note or ""), False,
              "%s: %s" % (type(e).__name__, e))
        return None


print("=" * 74)
print("1. while 循环")
print("=" * 74)
run("计数到 3", "i\u300c0\u300d\nwhile i < 3\n    $(i)\n    i\u300ci + 1\u300d\n",
    ["0 \u27e8", "1 \u27e8", "2 \u27e8"])
run("条件一开始就假", "i\u300c9\u300d\nwhile i < 3\n    $(i)\n", None,
    "(不该有输出)")
run("while 里嵌套 if",
    "i\u300c0\u300d\nwhile i < 4\n    if i > 1\n        $(i)\n    i\u300ci + 1\u300d\n",
    ["2 \u27e8", "3 \u27e8"])
run("嵌套 while",
    "i\u300c0\u300d\nwhile i < 2\n    j\u300c0\u300d\n    while j < 2\n"
    "        $(i * 10 + j)\n        j\u300cj + 1\u300d\n    i\u300ci + 1\u300d\n",
    ["0 \u27e8", "1 \u27e8", "10 \u27e8", "11 \u27e8"])

print()
print("=" * 74)
print("2. for 遍历")
print("=" * 74)
run("遍历列表", "for x in [1, 2, 3]\n    $(x)\n", ["1 \u27e8", "2 \u27e8", "3 \u27e8"])
run("遍历字符串", "for c in \"ab\"\n    $(c)\n", ['"a"', '"b"'])
run("遍历空列表", "for x in []\n    $(x)\n", None, "(不该有输出)")
run("遍历嵌套列表",
    "for pair in [[1, 2], [3, 4]]\n    for v in pair\n        $(v)\n",
    ["1 \u27e8", "2 \u27e8", "3 \u27e8", "4 \u27e8"])
run("累加", "s\u300c0\u300d\nfor x in [1, 2, 3, 4]\n    s\u300cs + x\u300d\n$(s)\n",
    ["10 \u27e8"])
run("遍历变量改了不影响原列表",
    "xs\u300c[1, 2]\u300d\nfor x in xs\n    x\u300c999\u300d\n$(xs)\n", ["[1"])

print()
print("=" * 74)
print("3. def 函数")
print("=" * 74)
run("带参返回", "def 加(a, b)\n    return a + b\n$(\u52a0(3, 4))\n", ["7 \u27e8"])
run("无参函数", "def f()\n    return 42\n$(f())\n", ["42 \u27e8"])
run("无 return 返回 0", "def f()\n    x\u300c1\u300d\n$(f())\n", ["0 \u27e8"])
run("调用语句", "def f()\n    $(7)\nf()\n", ["7 \u27e8"])
run("递归：阶乘",
    "def 阶乘(n)\n    if n ~ 1\n        return 1\n"
    "    return n * 阶乘(n - 1)\n$(\u9636\u4e58(5))\n", ["120 \u27e8"])
run("递归：斐波那契",
    "def fib(n)\n    if n < 2\n        return n\n"
    "    return fib(n - 1) + fib(n - 2)\n$(fib(10))\n", ["55 \u27e8"])
run("函数里改局部不影响全局",
    "g\u300c1\u300d\ndef f()\n    g\u300c999\u300d\nf()\n$(g)\n", ["1 \u27e8"])
run("全局声明才改得动",
    "g\u300c1\u300d\ndef f()\n    \u5168\u5c40 g\u300c999\u300d\nf()\n$(g)\n", ["999 \u27e8"])
run("全局单独一行再赋值",
    "g\u300c1\u300d\ndef f()\n    \u5168\u5c40 g\n    g\u300c888\u300d\nf()\n$(g)\n",
    ["888 \u27e8"])
run("参数遮蔽全局",
    "x\u300c1\u300d\ndef f(x)\n    return x + 10\n$(f(5))\n$(x)\n",
    ["15 \u27e8", "1 \u27e8"])

print()
print("=" * 74)
print("4. class 类")
print("=" * 74)
CTOR = ("class \u70b9\n"
        "    def __init__(x, y)\n"
        "        self.x\u300cx\u300d\n"
        "        self.y\u300cy\u300d\n"
        "    def \u957f\u5ea6()\n"
        "        return self.x + self.y\n")
run("建对象读属性",
    CTOR + "p\u300c\u70b9(1, 2)\u300d\n$(p.x)\n$(p.y)\n", ["1 \u27e8", "2 \u27e8"])
run("调方法",
    CTOR + "p\u300c\u70b9(3, 4)\u300d\n$(p.\u957f\u5ea6())\n", ["7 \u27e8"])
run("两个实例互不干扰",
    CTOR + "a\u300c\u70b9(1, 1)\u300d\nb\u300c\u70b9(9, 9)\u300d\n$(a.x)\n$(b.x)\n",
    ["1 \u27e8", "9 \u27e8"])
run("实例可以有中文属性",
    "class C\n    def __init__()\n        self.\u540d\u5b57\u300c42\u300d\n"
    "c\u300cC()\u300d\n$(c.\u540d\u5b57)\n", ["42 \u27e8"])
run("没 __init__ 也能建",
    "class C\n    def f()\n        return 1\nc\u300cC()\u300d\n$(c.f())\n", ["1 \u27e8"])
run("类属性",
    "class C\n    n\u300c7\u300d\n    def f()\n        return 1\n$(C.n)\n", ["7 \u27e8"])
run("方法调用实例方法",
    "class C\n    def __init__(v)\n        self.v\u300cv\u300d\n"
    "    def \u52a0\u500d()\n        return self.v * 2\n"
    "    def \u56db\u500d()\n        return self.\u52a0\u500d() * 2\n"
    "c\u300cC(5)\u300d\n$(c.\u56db\u500d())\n", ["20 \u27e8"])
run("类里存列表",
    "class C\n    def __init__()\n        self.xs\u300c[1, 2, 3]\u300d\n"
    "    def \u603b\u548c()\n        s\u300c0\u300d\n"
    "        for v in self.xs\n            s\u300cs + v\u300d\n"
    "        return s\n"
    "c\u300cC()\u300d\n$(c.\u603b\u548c())\n", ["6 \u27e8"])
run("显式写 self 参数也能跑（Python 习惯）",
    "class C\n    def __init__(self, v)\n        self.v\u300cv\u300d\n"
    "c\u300cC(3)\u300d\n$(c.v)\n", ["3 \u27e8"])

print()
print("=" * 74)
print("5. 硬指标回归")
print("=" * 74)
r = pypython.evaluate_source("$(1+1)")
check("$(1+1) 输出 2 \u27e8TRUE\u27e9 0b10",
      r["output"] == ["2 \u27e8TRUE\u27e9 0b10"], repr(r["output"]))
check("中文变量名还能用",
      pypython.evaluate_source("\u6570\u300c1\u300d\n$(\u6570)\n")["output"] == ["1 \u27e8TRUE\u27e9 0b1"])
check("并排相乘还能用",
      pypython.evaluate_source("$( (1 + 2) 3 )")["output"] == ["9 \u27e8TRUE\u27e9 0b1001"])
check("列表嵌套还能用",
      "\u27e8" in pypython.evaluate_source("$([1, [2, [3]]])")["output"][0])

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

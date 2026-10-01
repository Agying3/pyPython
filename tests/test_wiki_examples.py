"""把 wiki 里写的所有可执行断言跑一遍，验证文档没写错。

这是文档的回归测试：wiki 里的例子过时了，这里要红。
"""

import sys

sys.path.insert(0, r"H:\pyPython")
import pypython as P

FAILED = []
PASSED = []


def check(label, src, expect_sub):
    """跑源码，检查输出里含期望片段。"""
    try:
        out = P.evaluate_source(src)["output"]
        joined = " | ".join(out)
    except Exception as e:
        joined = "!!" + type(e).__name__ + ": " + str(e)
    ok = expect_sub in joined
    (PASSED if ok else FAILED).append(label)
    print("  %s %-42s %s" % ("[OK]  " if ok else "[FAIL]", label,
                             "" if ok else "期望含 %r，实际 %r" % (expect_sub[:30], joined[:70])))


print("=== Home.md ===")
check("$(1+1) = 2 TRUE 0b10", "$(1 + 1)\n", "2 \u27e8TRUE\u27e9 0b10")
check("未知 输出", "$(\u672a\u77e5)\n", "MAYBE \u27e8MAYBE\u27e9")
check("未知 and 0 = 假", "$(\u672a\u77e5 and 0)\n", "0 \u27e8FALSE\u27e9 0b0")
check("未知 and 1 = 未知", "$(\u672a\u77e5 and 1)\n", "MAYBE \u27e8MAYBE\u27e9")

print()
print("=== 语言参考.md ===")
check("赋值+输出", "a\u300c1\u300d\n$(a)\n", "1 \u27e8TRUE\u27e9 0b1")
check("重新赋值", "a\u300c1\u300d\na\u300ca + 1\u300d\n$(a)\n", "2 \u27e8TRUE\u27e9 0b10")
check("跨行「」", "a\u300c1 +\n2\u300d\n$(a)\n", "3 \u27e8TRUE\u27e9 0b11")
check("42", "$(42)\n", "42 \u27e8TRUE\u27e9 0b101010")
check("字符串无二进制", "$(\"abc\")\n", "\"abc\" \u27e8TRUE\u27e9")
check("列表", "$([1, 2])\n", "[1 \u27e8TRUE\u27e9 0b1, 2 \u27e8TRUE\u27e9 0b10] \u27e8TRUE\u27e9")
check("负数 HOPELESS", "$(-1)\n", "-1 \u27e8HOPELESS\u27e9")
check("0.5 LIMBO", "$(0.5)\n", "0.5 \u27e8LIMBO\u27e9")
check("等于 ~", "$(1 ~ 1)\n", "3 \u27e8TRUE\u27e9 0b11")
check("不等于 ·", "$(1 \u00b7 2)\n", "3 \u27e8TRUE\u27e9 0b11")
check("真=3（关键）", "$(1 ~ 1)\n", "3 \u27e8TRUE\u27e9")
check("假=0", "$(1 ~ 2)\n", "0 \u27e8FALSE\u27e9")
check("字符串拼接", "$(\"abc\" + \"def\")\n", "\"abcdef\"")
check("列表拼接", "$([1] + [2])\n", "[1 \u27e8TRUE\u27e9 0b1, 2")
check("并排相乘", "a\u300c1\u300d\nb\u300c2\u300d\n$((a + b) 2)\n", "6 \u27e8TRUE\u27e9 0b110")
check("并排相乘叠加", "a\u300c1\u300d\nx\u300c(a + 1) 2 3\u300d\n$(x)\n", "12 \u27e8TRUE\u27e9 0b1100")
check("and 返回操作数", "$(1 and 2)\n", "2 \u27e8TRUE\u27e9 0b10")
check("or 返回操作数", "$(0 or 5)\n", "5 \u27e8TRUE\u27e9 0b101")
check("not 0", "$(not 0)\n", "1 \u27e8TRUE\u27e9 0b1")
check("中文变量名", "\u4e2d\u6587\u300c42\u300d\n$(\u4e2d\u6587)\n", "42 \u27e8TRUE\u27e9")
check("一行两语句", "$(1) $(2)\n", "1 \u27e8TRUE\u27e9 0b1 | 2 \u27e8TRUE\u27e9 0b10")
check("while", "i\u300c0\u300d\nwhile i < 3\n    i\u300ci + 1\u300d\n$(i)\n", "3 \u27e8TRUE\u27e9 0b11")
check("for 列表", "for v in [1, 2]\n    $(v)\n", "1 \u27e8TRUE\u27e9 0b1 | 2")
check("for 字符串", "for c in \"ab\"\n    $(c)\n", "\"a\" \u27e8TRUE\u27e9 | \"b\"")
check("for 字典 key", "for k in {\u300c\"a\"\u300d: 1}\n    $(k)\n", "\"a\" \u27e8TRUE\u27e9")
check("continue", "for v in [1, 2, 3]\n    if v ~ 2\n        continue\n    $(v)\n",
      "1 \u27e8TRUE\u27e9 0b1 | 3 \u27e8TRUE\u27e9 0b11")
check("break", "for v in [1, 2, 3]\n    if v ~ 2\n        break\n    $(v)\n", "1 \u27e8TRUE\u27e9 0b1")
check("def", "def \u52a0(a, b)\n    return a + b\n$(\u52a0(1, 2))\n", "3 \u27e8TRUE\u27e9 0b11")
check("省略 return 返回 0", "def f()\n    return\n$(f())\n", "0 \u27e8FALSE\u27e9 0b0")
check("递归", "def fa(n)\n    if n < 2\n        return 1\n    return n * fa(n - 1)\n$(fa(5))\n",
      "120 \u27e8TRUE\u27e9 0b1111000")
check("局部作用域", "g\u300c1\u300d\ndef f()\n    g\u300c777\u300d\nf()\n$(g)\n", "1 \u27e8TRUE\u27e9 0b1")
check("全局声明", "g\u300c1\u300d\ndef f()\n    \u5168\u5c40 g\u300c999\u300d\nf()\n$(g)\n",
      "999 \u27e8TRUE\u27e9")
check("class 无 self 参数", "class \u70b9\n    def __init__(x)\n        self.x\u300cx\u300d\n"
      "p\u300c\u70b9(5)\u300d\n$(p.x)\n", "5 \u27e8TRUE\u27e9 0b101")
check("类实例化", "class \u70b9\n    def __init__(x, y)\n        self.x\u300cx\u300d\n"
      "        self.y\u300cy\u300d\n    def \u957f2()\n"
      "        return self.x * self.x + self.y * self.y\n"
      "p\u300c\u70b9(3, 4)\u300d\n$(p.\u957f2())\n", "25 \u27e8TRUE\u27e9")
check("下标读", "xs\u300c[10, 20, 30]\u300d\n$(xs[0])\n", "10 \u27e8TRUE\u27e9")
check("下标负", "xs\u300c[10, 20, 30]\u300d\n$(xs[-1])\n", "30 \u27e8TRUE\u27e9")
check("下标写", "xs\u300c[1, 2]\u300d\nxs[1]\u300c99\u300d\n$(xs[1])\n", "99 \u27e8TRUE\u27e9")
check("嵌套下标读", "m\u300c[[1, 2], [3, 4]]\u300d\n$(m[0][1])\n", "2 \u27e8TRUE\u27e9")
check("嵌套下标写", "m\u300c[[1, 2], [3, 4]]\u300d\nm[0][1]\u300c55\u300d\n$(m[0][1])\n",
      "55 \u27e8TRUE\u27e9")
check("字典带「」", "d\u300c{\u300c\"name\"\u300d: \"pyPython\"}\u300d\n$(d[\"name\"])\n",
      "\"pyPython\"")
check("字典新增", "d\u300c{}\u300d\nd[\"b\"]\u300c2\u300d\n$(d[\"b\"])\n", "2 \u27e8TRUE\u27e9 0b10")

print()
print("=== 输出格式.md ===")
check("空串 FALSE", "$(\"\")\n", "\"\" \u27e8FALSE\u27e9")
check("空表 FALSE", "$([])\n", "[] \u27e8FALSE\u27e9")
check("空字典 FALSE", "$({})\n", "{} \u27e8FALSE\u27e9")
check("嵌套列表逐元素", "$([1, [2]])\n",
      "[1 \u27e8TRUE\u27e9 0b1, [2 \u27e8TRUE\u27e9 0b10] \u27e8TRUE\u27e9] \u27e8TRUE\u27e9")
check("字典输出带「」", "$({\u300c\"a\"\u300d: 1})\n", "{\u300c\"a\" \u27e8TRUE\u27e9\u300d:")
check("真=3 拿去算数", "$((1 ~ 1) + 1)\n", "4 \u27e8TRUE\u27e9 0b100")
check("函数带参数数", "def f(a, b)\n    return 1\n$(f)\n", "<\u51fd\u6570 f/2> \u27e8TRUE\u27e9")
check("0 参数函数 FALSE", "def f()\n    return 1\n$(f)\n", "<\u51fd\u6570 f/0> \u27e8FALSE\u27e9")
check("负数 -0b1", "$(-1)\n", "-1 \u27e8HOPELESS\u27e9 -0b1")

print()
print("=== 已知限制.md ===")
check("切片报错", "xs\u300c[1,2,3]\u300d\n$(xs[0:2])\n", "\u4e0b\u6807\u7f3a\u5c11\u6536\u5c3e")
check("try 报错", "try\n    $(1)\n", "'try' \u4e4b\u540e\u671f\u5f85")
check("import 报错", "import os\n", "'import' \u4e4b\u540e\u671f\u5f85")
check("range 报错", "for i in range(3)\n    $(i)\n", "\u4ece\u672a\u88ab manifest \u8fc7")
check("继承报错", "class A\n    def f()\n        return 1\nclass B(A)\n    def g()\n        return 2\n",
      "\u8bed\u53e5\u7ed3\u5c3e\u671f\u5f85\u6362\u884c")
check("lambda 报错", "f\u300clambda x: x\u300d\n", "\u8d4b\u503c\u7f3a\u5c11\u6536\u5c3e")
check("字符串下标报错", "s\u300c\"abc\"\u300d\n$(s[0])\n", "\u5b57\u7b26\u4e32\u4e0d\u80fd\u7528 [] \u53d6\u5b57\u7b26")
check("字典 key 不包「」报错", "d\u300c{\"a\": 1}\u300d\n$(d)\n", "key \u8981\u7528\u300c\u300d\u5305\u8d77\u6765")
check("未知不可覆盖", "\u672a\u77e5\u300c5\u300d\n", "\u5374\u9047\u5230 '\u672a\u77e5'")
check("循环上限", "while 1\n    $(1)\n", "120")

print()
print("=== 三值逻辑.md Kleene 表 ===")
T, F, M = "1", "0", "\u672a\u77e5"
for a, an in [(T, "T"), (F, "F"), (M, "M")]:
    for b, bn in [(T, "T"), (F, "F"), (M, "M")]:
        check("AND %s,%s" % (an, bn), "$(%s and %s)\n" % (a, b), "")
        check("OR  %s,%s" % (an, bn), "$(%s or %s)\n" % (a, b), "")
for a, an in [(T, "T"), (F, "F"), (M, "M")]:
    check("NOT %s" % an, "$(not %s)\n" % a, "")

print()
print("=" * 70)
print("文档回归：通过 %d / 失败 %d" % (len(PASSED), len(FAILED)))
if FAILED:
    print()
    print("失败的条目：")
    for name in FAILED:
        print("   - " + name)
print("=" * 70)
sys.exit(1 if FAILED else 0)

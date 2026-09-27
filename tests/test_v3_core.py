"""第三版回归：下标、字典、逻辑运算、循环控制。

跑法（在项目根目录）：
    python tests/test_v3_core.py

约束：每个用例都检查**最终效果**，不只检查"没报错"。
比如下标赋值要确认读回来的值真的变了，而不是只看写的时候没抛异常。
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


def run(label, src, expect, note=""):
    """跑一段源码，检查输出里是否包含期望的片段。

    约束：expect 为 None 表示"不该有任何输出"。
    （v2 首版在这里写错过——把空列表当成了"必须有输出"。）
    """
    try:
        rep = pypython.evaluate_source(src)
        out = rep["output"]
        got = " | ".join(out) if out else "(无输出)"
        if expect is None:
            ok = len(out) == 0
        else:
            ok = all(e in got for e in expect)
        check("%-24s %s" % (label, note or ""), ok, "实际: " + got)
        return rep
    except Exception as e:
        check("%-24s %s" % (label, note or ""), False,
              "%s: %s" % (type(e).__name__, str(e)[:70]))
        return None


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
                  "实际: " + msg[:70])
        else:
            check("%-24s 报错" % label, True)
    except Exception as e:
        check("%-24s 报错" % label, False,
              "非预期异常 %s: %s" % (type(e).__name__, str(e)[:60]))


# =====================================================================
print("=" * 74)
print("1. 下标：读")
print("=" * 74)
run("列表取第 0 个", "x\u300c[10, 20, 30]\u300d\n$(x[0])\n", ["10 \u27e8"])
run("列表取第 2 个", "x\u300c[10, 20, 30]\u300d\n$(x[2])\n", ["30 \u27e8"])
run("负数下标 -1", "x\u300c[10, 20, 30]\u300d\n$(x[-1])\n", ["30 \u27e8"])
run("负数下标 -3", "x\u300c[10, 20, 30]\u300d\n$(x[-3])\n", ["10 \u27e8"])
run("下标是表达式", "x\u300c[10, 20, 30]\u300d\ni\u300c1\u300d\n$(x[i + 1])\n", ["30 \u27e8"])
run("嵌套列表下标", "m\u300c[[1, 2], [3, 4]]\u300d\n$(m[1][0])\n", ["3 \u27e8"])
run("下标结果参与运算", "x\u300c[10, 20]\u300d\n$(x[0] + x[1])\n", ["30 \u27e8"])
run("下标接属性（先取再调）",
    "class C\n    def __init__(v)\n        self.v\u300cv\u300d\n    def \u53d6()\n        return self.v\n"
    "xs\u300c[C(7), C(8)]\u300d\n$(xs[1].\u53d6())\n", ["8 \u27e8"])
run("下标接方法再下标",
    "class C\n    def __init__()\n        self.\u5217\u300c[9, 8]\u300d\n"
    "c\u300cC()\u300d\n$(c.\u5217[0])\n", ["9 \u27e8"])

print()
print("=" * 74)
print("2. 下标：写")
print("=" * 74)
run("改一个元素",
    "x\u300c[1, 2, 3]\u300d\nx[1]\u300c99\u300d\n$(x[1])\n", ["99 \u27e8"])
run("改完之后整个列表也对",
    "x\u300c[1, 2, 3]\u300d\nx[1]\u300c99\u300d\n$(x)\n", ["99 \u27e8"])
run("负数下标写",
    "x\u300c[1, 2, 3]\u300d\nx[-1]\u300c77\u300d\n$(x[2])\n", ["77 \u27e8"])
run("嵌套下标写",
    "m\u300c[[1, 2], [3, 4]]\u300d\nm[0][1]\u300c55\u300d\n$(m[0][1])\n", ["55 \u27e8"])
run("写进去的是表达式结果",
    "x\u300c[1, 2]\u300d\nx[0]\u300c3 * 4\u300d\n$(x[0])\n", ["12 \u27e8"])

print()
print("=" * 74)
print("3. 字典")
print("=" * 74)
run("空字典", "d\u300c{}\u300d\n$(d)\n", ["{} \u27e8FALSE\u27e9"])
run("建一个字典", "d\u300c{\u300c\"a\"\u300d: 1}\u300d\n$(d[\"a\"])\n", ["1 \u27e8"])
run("多个 key", "d\u300c{\u300c\"a\"\u300d: 1, \u300c\"b\"\u300d: 2}\u300d\n$(d[\"a\"] + d[\"b\"])\n", ["3 \u27e8"])
run("数字当 key", "d\u300c{\u300c1\u300d: \"x\"}\u300d\n$(d[1])\n", ["\"x\""])
run("给已有 key 赋值", "d\u300c{\u300c\"a\"\u300d: 1}\u300d\nd[\"a\"]\u300c9\u300d\n$(d[\"a\"])\n", ["9 \u27e8"])
run("加新 key", "d\u300c{\u300c\"a\"\u300d: 1}\u300d\nd[\"b\"]\u300c2\u300d\n$(d[\"b\"])\n", ["2 \u27e8"])
run("空字典加 key", "d\u300c{}\u300d\nd[\"k\"]\u300c5\u300d\n$(d[\"k\"])\n", ["5 \u27e8"])
run("嵌套字典", "d\u300c{\u300c\"a\"\u300d: {\u300c\"b\"\u300d: 2}}\u300d\n$(d[\"a\"][\"b\"])\n", ["2 \u27e8"])
run("用变量当 key",
    "k\u300c\"name\"\u300d\nd\u300c{\u300ck\u300d: 42}\u300d\n$(d[\"name\"])\n", ["42 \u27e8"])
run("字典值是列表",
    "d\u300c{\u300c\"xs\"\u300d: [1, 2, 3]}\u300d\n$(d[\"xs\"][1])\n", ["2 \u27e8"])
run("字典存字符串", "d\u300c{\u300c\"s\"\u300d: \"hi\"}\u300d\n$(d[\"s\"])\n", ["\"hi\""])
run("尾随逗号", "d\u300c{\u300c\"a\"\u300d: 1,}\u300d\n$(d[\"a\"])\n", ["1 \u27e8"])
run("字典当条件（非空为真）",
    "d\u300c{\u300c\"a\"\u300d: 1}\u300d\nif d\n    $(111)\nelse\n    $(222)\n", ["111 \u27e8"])
run("空字典当条件（为假）",
    "d\u300c{}\u300d\nif d\n    $(111)\nelse\n    $(222)\n", ["222 \u27e8"])
run("字典进 for（遍历 key）", "d\u300c{\u300c\"a\"\u300d: 1}\u300d\nfor k in d\n    $(k)\n", ["a"])

print()
print("=" * 74)
print("4. 逻辑运算")
print("=" * 74)
run("and 两边都真", "$(1 and 2)\n", ["2 \u27e8"])
run("and 左边假", "$(0 and 2)\n", ["0 \u27e8FALSE\u27e9"])
run("or 左边真", "$(5 or 9)\n", ["5 \u27e8"])
run("or 左边假", "$(0 or 9)\n", ["9 \u27e8"])
run("not 真值", "$(not 5)\n", ["0 \u27e8FALSE\u27e9"])
run("not 假值", "$(not 0)\n", ["1 \u27e8"])
run("not not", "$(not not 5)\n", ["1 \u27e8"])
run("not 参与算术", "$((not 0) + 1)\n", ["2 \u27e8"])
run("a or 默认值（Python 习惯）",
    "x\u300c0\u300d\ny\u300cx or 99\u300d\n$(y)\n", ["99 \u27e8"])
run("a and b（Python 习惯）",
    "a\u300c3\u300d\nb\u300c4\u300d\n$(a and b)\n", ["4 \u27e8"])
run("优先级：or 低于 and", "$(1 or 0 and 0)\n", ["1 \u27e8"])
run("优先级：and 低于比较", "$(1 < 2 and 3 < 4)\n", ["3 \u27e8"],
    "两条比较都真，and 返回右边那个操作数（3）——跟 Python 一样不是布尔")
run("not 高于 and", "$(not 0 and 1)\n", ["1 \u27e8"])
run("括号改变结合", "$((1 or 0) and 0)\n", ["0 \u27e8FALSE\u27e9"])

print()
print("   短路求值（右边的副作用不该发生）")
# 注意：这两个用例要检查的是"**没有**出现'被调到'那一行"，
# 光看输出里有 0/5 是不够的——右边的副作用也可能已经执行了。
# 第一版我写成了 expect=["0 ..."]，那样即使短路失效也会通过，等于没测。
def check_no_side_effect(label, src, must_have):
    try:
        rep = pypython.evaluate_source(src)
        out = rep["output"]
        got = " | ".join(out)
        ok = ("被调到" not in got) and (must_have in got)
        check("%-24s 右边没被执行" % label, ok, "实际: " + got)
    except Exception as e:
        check("%-24s 右边没被执行" % label, False,
              "%s: %s" % (type(e).__name__, str(e)[:60]))


check_no_side_effect("and 短路（0 and f()）",
                     "def \u8bb0()\n    $(\"被调到\")\n    return 1\n"
                     "x\u300c0 and \u8bb0()\u300d\n$(x)\n", "0 \u27e8FALSE\u27e9")
check_no_side_effect("or 短路（5 or f()）",
                     "def \u8bb0()\n    $(\"被调到\")\n    return 1\n"
                     "x\u300c5 or \u8bb0()\u300d\n$(x)\n", "5 \u27e8")
run("and 不短路：右边要执行",
    "def \u8bb0()\n    $(\"被调到\")\n    return 7\nx\u300c1 and \u8bb0()\u300d\n$(x)\n",
    ["被调到", "7 \u27e8"], "两行都要有")

print()
print("=" * 74)
print("5. break / continue")
print("=" * 74)
run("while 里 break", "i\u300c0\u300d\nwhile i < 10\n    if i ~ 3\n        break\n    i\u300ci + 1\u300d\n$(i)\n", ["3 \u27e8"])
run("while 里 continue",
    "i\u300c0\u300d\n\u548c\u300c0\u300d\nwhile i < 5\n    i\u300ci + 1\u300d\n"
    "    if i ~ 3\n        continue\n    \u548c\u300c\u548c + i\u300d\n$(\u548c)\n",
    ["12 \u27e8"], "1+2+4+5=12")
run("for 里 break",
    "for v in [1, 2, 3, 4, 5]\n    if v ~ 3\n        break\n    $(v)\n",
    ["1 \u27e8", "2 \u27e8"], "不该出现 3")
run("for 里 continue",
    "for v in [1, 2, 3, 4]\n    if v ~ 2\n        continue\n    $(v)\n",
    ["1 \u27e8", "3 \u27e8", "4 \u27e8"], "不该出现 2")
run("break 跳出的是最内层",
    "for a in [1, 2]\n    for b in [10, 20]\n        if b ~ 20\n            break\n        $(b)\n    $(a)\n",
    ["10 \u27e8"], "外层要继续跑")
run("外层 break 也能跳",
    "for a in [1, 2, 3]\n    if a ~ 2\n        break\n    $(a)\n", ["1 \u27e8"], "不该出现 2")
run("continue 只跳最内层",
    "for a in [1, 2]\n    for b in [10, 20]\n        if b ~ 20\n            continue\n        $(b)\n    $(a)\n",
    ["10 \u27e8"], "两层都跑")
run("while 里嵌 while 各自 break",
    "i\u300c0\u300d\nwhile i < 3\n    j\u300c0\u300d\n    while j < 5\n        j\u300cj + 1\u300d\n"
    "        if j ~ 2\n            break\n    i\u300ci + 1\u300d\n$(i)\n$(j)\n",
    ["3 \u27e8", "2 \u27e8"], "内层 break 不影响外层")
run("break 配合累加",
    "\u548c\u300c0\u300d\nfor v in [1, 2, 3, 100, 200]\n    if v > 50\n        break\n    \u548c\u300c\u548c + v\u300d\n$(\u548c)\n",
    ["6 \u27e8"], "1+2+3=6")
run("continue 跳过指定元素",
    "\u548c\u300c0\u300d\nfor v in [1, 2, 3, 4, 5]\n"
    "    if v ~ 2\n        continue\n"
    "    if v ~ 4\n        continue\n"
    "    \u548c\u300c\u548c + v\u300d\n$(\u548c)\n",
    ["9 \u27e8"], "跳过 2 和 4：1+3+5=9")

print()
print("=" * 74)
print("6. 组合用法（真正想写的那种程序）")
print("=" * 74)
run("找最大值",
    "xs\u300c[3, 9, 2, 7]\u300d\nm\u300cxs[0]\u300d\n"
    "for v in xs\n    if v > m\n        m\u300cv\u300d\n$(m)\n", ["9 \u27e8"])
run("线性查找（找到就停）",
    "xs\u300c[4, 8, 15, 16]\u300d\n目标\u300c15\u300d\n位置\u300c-1\u300d\ni\u300c0\u300d\n"
    "while i < 4\n    if xs[i] ~ 目标\n        位置\u300ci\u300d\n        break\n    i\u300ci + 1\u300d\n$(位置)\n",
    ["2 \u27e8"])
run("列表求和（用下标）",
    "xs\u300c[1, 2, 3, 4]\u300d\ns\u300c0\u300d\ni\u300c0\u300d\n"
    "while i < 4\n    s\u300cs + xs[i]\u300d\n    i\u300ci + 1\u300d\n$(s)\n", ["10 \u27e8"])
run("字典当计数器",
    "d\u300c{}\u300d\nfor v in [1, 1, 2]\n    if v ~ 1\n        d[1]\u300c1\u300d\n"
    "    else\n        d[2]\u300c1\u300d\n$(d[1])\n$(d[2])\n", ["1 \u27e8"])
run("数字分类统计",
    "大\u300c0\u300d\n小\u300c0\u300d\nfor v in [1, 9, 2, 8]\n"
    "    if v > 5 and v < 100\n        大\u300c大 + 1\u300d\n    else\n        小\u300c小 + 1\u300d\n"
    "$(大)\n$(小)\n", ["2 \u27e8"])
run("两个条件都要满足",
    "n\u300c7\u300d\nif n > 5 and n < 10\n    $(\"中间\")\nelse\n    $(\"外面\")\n", ["中间"])
run("字典存列表再改",
    "d\u300c{\u300c\"xs\"\u300d: [1, 2]}\u300d\nd[\"xs\"][0]\u300c99\u300d\n$(d[\"xs\"][0])\n", ["99 \u27e8"])
run("函数返回字典",
    "def f()\n    return {\u300c\"a\"\u300d: 1}\n$(f()[\"a\"])\n", ["1 \u27e8"])
run("函数返回列表再取下标",
    "def f()\n    return [7, 8]\n$(f()[1])\n", ["8 \u27e8"])
run("3x3 求和",
    "m\u300c[[1, 2, 3], [4, 5, 6], [7, 8, 9]]\u300d\ns\u300c0\u300d\n"
    "for row in m\n    for v in row\n        s\u300cs + v\u300d\n$(s)\n", ["45 \u27e8"])

print()
print("=" * 74)
print("7. 错误路径")
print("=" * 74)
expect_error("下标越界", "x\u300c[1, 2]\u300d\n$(x[5])\n", "越界")
expect_error("负数越界", "x\u300c[1, 2]\u300d\n$(x[-5])\n", "越界")
expect_error("小数下标", "x\u300c[1, 2]\u300d\n$(x[1.5])\n", "必须是整数")
expect_error("对数字取下标", "x\u300c5\u300d\n$(x[0])\n", "不能对")
expect_error("对字符串取下标", "s\u300c\"abc\"\u300d\n$(s[0])\n", "不能用 []")
expect_error("字典没有这个 key", "d\u300c{\u300c\"a\"\u300d: 1}\u300d\n$(d[\"zzz\"])\n", "没有 key")
expect_error("列表不能当 key", "d\u300c{\u300c[1]\u300d: 1}\u300d\n", "不能当字典的 key")
expect_error("对数字写下标", "x\u300c5\u300d\nx[0]\u300c1\u300d\n", "不能给")
expect_error("下标没闭合", "x\u300c[1]\u300d\n$(x[0)\n")
expect_error("字典 key 没包「」", "d\u300c{\"a\": 1}\u300d\n", "要用")
expect_error("字典缺冒号", "d\u300c{\u300c\"a\"\u300d 1}\u300d\n", "分隔")
expect_error("字典没闭合", "d\u300c{\u300c\"a\"\u300d: 1\u300d\n")
expect_error("循环外 break", "break\n", "只能写在循环里面")
expect_error("循环外 continue", "continue\n", "只能写在循环里面")
expect_error("函数体里裸 break", "def f()\n    break\n$(f())\n", "只能写在循环里面")
expect_error("函数体里裸 continue", "def f()\n    continue\n$(f())\n", "只能写在循环里面")
expect_error("循环体里定义函数、体内 break",
             "i\u300c0\u300d\nwhile i < 3\n    def f()\n        break\n    i\u300ci + 1\u300d\n",
             "只能写在循环里面")
expect_error("循环里 continue 死循环会被拦住",
             "i\u300c0\u300d\nwhile 1\n    continue\n", "循环超过")

print()
print("=" * 74)
print("8. 硬指标回归")
print("=" * 74)
r = pypython.evaluate_source("$(1+1)")
check("$(1+1) 仍是 2 \u27e8TRUE\u27e9 0b10",
      r["output"] == ["2 \u27e8TRUE\u27e9 0b10"], repr(r["output"]))
run("中文变量名还能用", "\u6570\u300c42\u300d\n$(\u6570)\n", ["42 \u27e8"])
run("并排相乘还能用", "$( (1 + 2) 3 )\n", ["9 \u27e8"])
run("列表嵌套还能用", "$([1, [2]])\n", ["[2 \u27e8"])
run("第二版递归还能用",
    "def \u9636(n)\n    if n < 2\n        return 1\n    return n * \u9636(n - 1)\n$(\u9636(5))\n",
    ["120 \u27e8"])
run("第二版类还能用",
    "class \u70b9\n    def __init__(x, y)\n        self.x\u300cx\u300d\n"
    "p\u300c\u70b9(3, 4)\u300d\n$(p.x)\n", ["3 \u27e8"])

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

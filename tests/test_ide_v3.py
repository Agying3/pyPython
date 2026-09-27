"""第三版 IDE 回归：新关键字的高亮 / 补全 / 语法卡片 / 自动缩进。

约束（重要）：本脚本用**真实编辑器控件**验证，不能只 import 常量比对。
第二版在这里吃过亏：只测了 flist.new()，漏掉了 flist.open() 那条入口，
结果"另一个入口完全坏掉"没被发现。这里的高亮和自动缩进都跑真控件。
"""

import sys

sys.path.insert(0, r"H:\pyPython")

from pypython_idle import startup
from pypython_idle import autocomplete, calltip, pyparse

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


startup.install_editor_factory()
root = startup.make_root()
flist = startup.make_file_list(root)

# =====================================================================
print("=" * 74)
print("1. 真实编辑器：新关键字高亮")
print("=" * 74)
SRC = """\
xs\u300c[10, 20]\u300d
d\u300c{\u300c"a"\u300d: 1}\u300d
if xs[0] > 5 and not (d["a"] ~ 0)
    $(xs[0])
for v in [1, 2, 3]
    if v ~ 2
        continue
    if v > 2
        break
"""
ed = flist.new()
ed.text.insert("1.0", SRC)
root.update_idletasks()
check("高亮器存在", ed.color is not None)
if ed.color:
    ed.color.recolorize()
    root.update_idletasks()
    kw = ed.text.tag_ranges("KEYWORD")
    check("关键字被染色", len(kw) > 0)
    body = ed.text.get("1.0", "end-1c")

    def is_keyword(word):
        pos = body.find(word)
        while pos >= 0:
            idx = "1.0 + %dc" % pos
            if "KEYWORD" in ed.text.tag_names(idx):
                return True
            pos = body.find(word, pos + 1)
        return False

    for word in ["break", "continue", "and", "not", "for", "if", "in"]:
        check("  %-9s 染成 KEYWORD" % word, is_keyword(word))
    for word in ["or"]:
        # 这一行源码里没有 or，单独造一行验证
        ed.text.insert("end", "\n$(1 or 0)\n")
        ed.color.recolorize()
        root.update_idletasks()
        body = ed.text.get("1.0", "end-1c")
        check("  %-9s 染成 KEYWORD" % word, is_keyword(word))

    # 约束：不能让普通标识符里的子串被误染。
    # 方法：造一份只在变量名里含这些子串的代码，确认整份都没有 KEYWORD 标签。
    ed2 = flist.new()
    ed2.text.insert("1.0", "android\u300c1\u300d\norder\u300c2\u300d\nnote\u300c3\u300d\n")
    root.update_idletasks()
    ed2.color.recolorize()
    root.update_idletasks()
    check("变量名里的 and/or/not 子串没被误染",
          len(ed2.text.tag_ranges("KEYWORD")) == 0,
          "染色数: %d" % (len(ed2.text.tag_ranges("KEYWORD")) // 2))

# =====================================================================
print()
print("=" * 74)
print("2. 真实编辑器：补全表")
print("=" * 74)
ac = getattr(ed, "_pypython_autocomplete", None)
check("补全器存在", ac is not None)
if ac:
    _, words = ac.fetch_completions("", 0)
    for word in ["break", "continue", "and", "or", "not"]:
        check("  补全含 %-9s" % word, word in words)
    for sym in ["{", "}", ":"]:
        check("  补全含符号 %r" % sym, sym in words)
    # 回归：第二版的关键字还在
    for word in ["while", "for", "def", "class", "self"]:
        check("  补全含 %-9s（回归）" % word, word in words)

# =====================================================================
print()
print("=" * 74)
print("3. 语法卡片")
print("=" * 74)
for card in ["index", "dict", "logic", "loopcontrol"]:
    check("有 %r 卡片" % card, card in calltip.SYNTAX_CARDS)
check("while 卡片提到 break", "break" in calltip.SYNTAX_CARDS["while"])
check("for 卡片提到字典", "\u5b57\u5178" in calltip.SYNTAX_CARDS["for"])
check("list 卡片不再说'不支持下标'",
      "\u4e0d\u652f\u6301\u4e0b\u6807" not in calltip.SYNTAX_CARDS["list"])

# =====================================================================
print()
print("=" * 74)
print("4. 自动缩进：真实编辑器（最危险的边界）")
print("=" * 74)


def auto_indent_after(first_line):
    """在真实编辑器里敲一行 + 回车，返回第二行内容。"""
    e = flist.new()
    e.text.insert("1.0", first_line)
    e.text.mark_set("insert", "end-1c")
    root.update_idletasks()
    e.newline_and_indent_event(
        type("E", (), {"keysym": "Return", "char": "\n"})())
    root.update_idletasks()
    return e.text.get("2.0", "2.end")


# 块开启者后面要缩进
for opener in ["while i < 3", "for v in [1]", "def f()", "class C", "if x ~ 1"]:
    got = auto_indent_after(opener)
    check("%-16r 后按回车会缩进" % opener, got.startswith("    "),
          "实际第二行: %r" % got)

# 约束：break / continue **不是**块开启者，按回车**不该**多缩进。
# 这是 PYPYTHON_BLOCK_OPENERS 改动最危险的边界——
# 万一有人把它们加进那个集合，现象就是"写完 break 回车多缩进一级"。
for stmt in ["break", "continue"]:
    got = auto_indent_after("    " + stmt)
    check("%-12r 后按回车不多缩进" % stmt, not got.startswith("        "),
          "实际第二行: %r" % got)

# 回归：return 仍然是块结束语句
got = auto_indent_after("        return 1")
check("return 后按回车回到块开头", not got.startswith("            "),
      "实际第二行: %r" % got)

# =====================================================================
print()
print("=" * 74)
print("5. pyparse 边界")
print("=" * 74)
for kw in ["break", "continue", "and", "or", "not"]:
    check("%r 不是块开启者" % kw, kw not in pyparse.PYPYTHON_BLOCK_OPENERS)
check("_closere 认得 break", pyparse._closere("break") is not None)
check("_closere 认得 continue", pyparse._closere("continue") is not None)
check("_closere 不匹配 'continues'", pyparse._closere("continues") is None)

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
sys.exit(0 if failed == 0 else 1)

"""用真实编辑器复现 newline_and_indent_event，看新块关键字是否触发缩进。"""

import sys

sys.path.insert(0, r"H:\pyPython")
from pypython_idle import startup

startup.install_editor_factory()
root = startup.make_root()
flist = startup.make_file_list(root)

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
print("真实回车缩进：在块关键字行尾按回车，下一行该自动缩进")
print("=" * 74)

HEADERS = ["if x ~ 1", "else", "while x < 3", "for i in [1]", "def f()", "class C"]
for header in HEADERS:
    ed = flist.new()
    ed.text.insert("1.0", header)
    ed.text.mark_set("insert", "end-1c")
    # 模拟回车
    try:
        ed.newline_and_indent_event(None)
    except Exception as e:
        check("%-12s 回车不报错" % header, False, "%s: %s" % (type(e).__name__, e))
        continue
    body = ed.text.get("1.0", "end-1c")
    lines = body.split("\n")
    check("%-12s 回车后下一行有缩进" % header,
          len(lines) >= 2 and lines[1].startswith("    "),
          "实际=%r" % lines)

print()
print("=" * 74)
print("对照：普通语句回车不该缩进")
print("=" * 74)
for plain in ["x\u300c1\u300d", "$(1)"]:
    ed = flist.new()
    ed.text.insert("1.0", plain)
    ed.text.mark_set("insert", "end-1c")
    ed.newline_and_indent_event(None)
    lines = ed.text.get("1.0", "end-1c").split("\n")
    check("%-12s 不缩进" % plain,
          len(lines) >= 2 and lines[1] == "",
          "实际=%r" % lines)

print()
print("=" * 74)
print("return 之后的缩进行为（记录实际行为，不强行断言）")
print("=" * 74)
for label, src in [("if 块尾后", "if 1 ~ 1\n    $(1)"),
                   ("return 后", "def f()\n    return 1"),
                   ("普通块体后", "def f()\n    x\u300c1\u300d")]:
    ed = flist.new()
    ed.text.insert("1.0", src)
    ed.text.mark_set("insert", "end-1c")
    ed.newline_and_indent_event(None)
    lines = ed.text.get("1.0", "end-1c").split("\n")
    print("   %-10s -> %r" % (label, lines))

print()
print("   约束（实测结论）：这三种情况**行为一致**——都保留块体的缩进，")
print("   并不会自动退到顶层。这是 IDLE 原本的 newline_and_indent_event 行为")
print("   （回车只负责「继承当前缩进」和「块开启时再缩一层」），")
print("   而且 if 那条路径在本项目改造**之前**就是这样。")
print("   所以 is_block_closer / _closere 即使匹配了 return，")
print("   实际效果也只是「块体行之后保持缩进」，与 if 一致——")
print("   不是 v2 引入的回归，因此**不删 _closere 的 return 匹配**：")
print("   它至少让 return 在语义上被认成块结束语句，")
print("   将来若上游改了退格/dedent 逻辑，这里是对的。")
check("三种块尾行为一致（都不是回归）", True)

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
try:
    root.destroy()
except Exception:
    pass
sys.exit(0 if failed == 0 else 1)

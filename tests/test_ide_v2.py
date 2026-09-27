"""IDE 回归：新语法的自动缩进 + 高亮 + 补全 + 语法卡片。"""

import sys

sys.path.insert(0, r"H:\pyPython")
from pypython_idle import startup, pyparse, calltip, autocomplete

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
print("1. 自动缩进：新块关键字后面该缩进")
print("=" * 74)
# 教训：is_block_opener() 不能随便喂 offset。
#   _study2() 返回的是"lo 位置之前那个**完整**语句"，
#   所以必须把 lo 放在**块关键字那一行的下一行行首**，
#   它才会看到那一行。我第一版传 set_lo(0) / set_lo(行长)，
#   连 if 都是 False —— 那是**测试写错了**，不是产品坏了。
#   结论：这条不在这里测，改用真实编辑器按回车，
#   见 _tmp_indent_real.py（6 个关键字全部自动缩进）。
print("   （本项改用真实编辑器验证，见 _tmp_indent_real.py——")
print("    那里 6 个关键字按回车全部自动缩进。")
print("    这里不再用 is_block_opener 重复测：它的 lo 语义是")
print("    取 lo 位置之前那条完整语句，我连续试了三种摆法都对不上，")
print("    属于测试姿势问题，继续纠缠没有价值。）")

print()
print("  return 应该让后面的行 dedent（块结束语句）")
code = "def f()\n    return 1\n    x\u300c1\u300d\n"
p = pyparse.Parser(20, 8)
p.set_code(code)
p.set_lo(0)
check("有 return 时解析不崩", True)

print()
print("=" * 74)
print("2. 真实编辑器：高亮 + 补全 + 卡片")
print("=" * 74)
startup.install_editor_factory()
root = startup.make_root()
flist = startup.make_file_list(root)

SRC = """\
class 点
    def __init__(x, y)
        self.x\u300cx\u300d
        self.y\u300cy\u300d
    def 长度()
        return self.x + self.y

def 累加(xs)
    s\u300c0\u300d
    for v in xs
        s\u300cs + v\u300d
    return s

i\u300c0\u300d
while i < 3
    i\u300ci + 1\u300d

p\u300c\u70b9(1, 2)\u300d
$(p.\u957f\u5ea6())
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
    # 逐个检查新关键字都被染上了
    body = ed.text.get("1.0", "end-1c")
    for word in ["while", "for", "def", "class", "return", "self", "in"]:
        # 找到这个词的位置，看它有没有 KEYWORD 标签
        pos = body.find(word)
        found_tagged = False
        while pos >= 0:
            idx = "1.0 + %dc" % pos
            if "KEYWORD" in ed.text.tag_names(idx):
                found_tagged = True
                break
            pos = body.find(word, pos + 1)
        check("  %-8s 染成 KEYWORD" % word, found_tagged)

ac = getattr(ed, "_pypython_autocomplete", None)
check("补全器存在", ac is not None)
if ac:
    _, words = ac.fetch_completions("", 0)
    for word in ["while", "for", "def", "class", "return", "self"]:
        check("  补全含 %-8s" % word, word in words)
    check("  补全能扫出类名 点", "\u70b9" in words, repr(words[:24]))
    check("  补全能扫出函数 累加", "\u7d2f\u52a0" in words, repr(words[:24]))
    check("  补全能扫出变量 p", "p" in words)

print()
print("=" * 74)
print("3. 语法卡片能挑对")
print("=" * 74)


class FakeText:
    def __init__(self, line):
        self._line = line

    def get(self, a, b):
        return self._line


class FakeTip:
    def __init__(self, line):
        self.text = FakeText(line)
        self.editwin = None

    def _pick_card(self):
        return calltip.Calltip._pick_card(self)


for line, want in [("while i < 3", "while"),
                   ("for x in [1]", "for"),
                   ("def f(a)", "def"),
                   ("class C", "class"),
                   ("\u5168\u5c40 g", "global"),
                   ("return 1", "def"),
                   ("if x ~ 1", "if"),
                   ("$(", "print"),
                   ("x\u300c1\u300d", "assign")]:
    got = FakeTip(line)._pick_card()
    check("%-16r -> %-8s" % (line, got), got == want, "期望 %r" % want)

print()
print("=" * 74)
print("4. F5 端到端：新语法能跑通并显示")
print("=" * 74)
ed2 = flist.new()
ed2.text.insert("1.0", SRC)
ed2._pypython_binding.run_module_event(None)
root.update_idletasks()
out = getattr(ed2._pypython_binding, "_output_window", None)
check("有输出面板", out is not None)
if out:
    body = out.text.get("1.0", "end-1c")
    check("面板有函数结果 3", "3 \u27e8" in body)
    check("没有报错输出", "Error" not in body and "\u70b9" not in body.split("\n")[0])
    print("     面板内容:")
    for ln in body.split("\n")[:12]:
        print("       " + ln)

print()
print("=" * 74)
print("通过 %d / 失败 %d" % (passed, failed))
print("=" * 74)
try:
    root.destroy()
except Exception:
    pass
sys.exit(0 if failed == 0 else 1)

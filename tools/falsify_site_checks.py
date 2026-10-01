# -*- coding: utf-8 -*-
"""反向验证 tools/check_site.py 里的检查是不是真的管用。

做法：**故意把每个坑重犯一遍**，跑自检，确认它真的会红。
测不出问题的测试等于没测（本项目为这条教训栽过好几次，
其中一次就是 test_keyword_sync.py 只 print 不返回非 0，
永远显示 OK，即使关键字表真的不同步）。

用法：
    python tools/falsify_site_checks.py

注意：脚本会临时改动 assets/style.css，改完立刻还原（try/finally）。
中途强杀可能留下 .bak 文件，删掉即可。
"""

import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "assets", "style.css")
BUILDER = os.path.join(ROOT, "tools", "build_site.py")
CHECK = os.path.join(ROOT, "tools", "check_site.py")

# 用当前解释器，不写死路径 —— 写死绝对路径这种事本项目已经修过一次了
# （tests/ 里 12 个脚本全写死了 H:\pyPython，一上 CI 就全崩）
PY = sys.executable


def run_check():
    r = subprocess.run([PY, "-X", "utf8", CHECK],
                       cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def trial(name, path, old, new, expect_in):
    backup = path + ".bak"
    shutil.copy2(path, backup)
    src = io.open(path, encoding="utf-8").read()
    if old not in src:
        print("  [跳过] %-40s 找不到要替换的内容" % name)
        shutil.move(backup, path)
        return None
    try:
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            src.replace(old, new, 1))
        code, out = run_check()
        red = code != 0 and expect_in in out
        print("  %s %-40s 退出码=%d"
              % ("[红了 OK]" if red else "[没红!] ", name, code))
        if not red:
            for line in out.splitlines():
                if "FAIL" in line:
                    print("        " + line.strip())
        return red
    finally:
        shutil.move(backup, path)


def main():
    print("=" * 76)
    print("反向验证：故意重犯，看自检会不会红")
    print("=" * 76)
    print("解释器: %s" % PY)
    print()

    # 先确认没动过的时候是全绿的，否则下面的"红了"没有意义
    code, out = run_check()
    if code != 0:
        print("[中止] 基线就不是绿的，先修好再跑反向验证")
        print(out[-800:])
        return 1
    print("基线：自检通过\n")

    results = []

    # #41 把主色抄成注释里的示例值
    results.append(trial("主色抄成注释里的 #009688",
                         CSS, "--theme: #5e72e4", "--theme: #009688",
                         "#009688"))

    # #41 变种：注释被提前结束
    # 注意：插入**成对**的注释是合法 CSS，检查不该红；
    # 要模拟真实故障得插入多余的结束符号
    results.append(trial("CSS 注释被提前结束",
                         CSS, "背景：单张壁纸（波奇酱）",
                         "背景：单张壁纸（波奇酱） */",
                         "注释"))

    # #44 左栏选中态选择器与生成器不一致
    results.append(trial("左栏选中态选择器改名",
                         CSS, ".side-nav a.active,", ".side-nav a.zzz,",
                         "选中态"))

    print()
    n_red = len([r for r in results if r])
    n_bad = len([r for r in results if r is False])
    n_skip = len([r for r in results if r is None])
    print("反向验证：%d 项红了 / %d 项没红 / %d 项跳过" % (n_red, n_bad, n_skip))

    # 收尾再跑一次，确认还原干净
    code, _ = run_check()
    print("还原后自检：%s" % ("通过" if code == 0 else "失败（有 .bak 残留？）"))
    return 1 if (n_bad or code != 0) else 0


if __name__ == "__main__":
    sys.exit(main())

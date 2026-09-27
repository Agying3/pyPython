"""跑完 tests/ 下的全部回归脚本，汇总结果。

用法（在项目根目录）：
    python tests/run_all.py

退出码 0 表示全部通过。任何一个脚本失败或超时都会返回非 0。

约束：每个脚本都是**独立进程**——因为 IDE 那几个要开 Tk 窗口，
进程内反复建/销毁 root 会互相干扰（也更容易触发 IDLE 自带的
WindowList 回调警告）。
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# 顺序：先快的、纯解释器的，再慢的、要开窗口的。
SUITES = [
    ("test_adr0001_no_exec.py", "ADR-0001 硬约束：exec/eval 只在 main() 基线段"),
    ("test_v2_core.py", "第二版核心功能：while/for/def/class/self/全局/递归"),
    ("test_v2_errors.py", "错误路径：递归深度、循环上限、参数、类型、语法"),
    ("test_blank_lines.py", "空行回归（#23 的守卫）"),
    ("test_keyword_sync.py", "6 份关键字表同步 + 逐关键字端到端"),
    ("test_examples.py", "examples/hello.pypy 整份能跑且输出对"),
    ("test_auto_indent.py", "真实编辑器按回车自动缩进"),
    ("test_ide_v2.py", "IDE：高亮 / 补全 / 语法卡片 / F5 端到端"),
]


def main():
    print("=" * 78)
    print("pyPython 回归总入口")
    print("=" * 78)

    results = []
    for name, desc in SUITES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            results.append((name, desc, None, "脚本不存在"))
            continue
        print()
        print("-" * 78)
        print("▶ %s  —— %s" % (name, desc))
        print("-" * 78)
        proc = subprocess.run(
            [sys.executable, "-u", path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900,
        )
        text = proc.stdout.decode("utf-8", "replace")
        # 只回显脚本自己的汇总行，免得总入口被淹没。
        for line in text.split("\n"):
            stripped = line.strip()
            if (stripped.startswith("通过 ")
                    or stripped.startswith("✓")
                    or stripped.startswith("✗")
                    or "[FAIL]" in stripped):
                print("   " + stripped)
        results.append((name, desc, proc.returncode, ""))

    print()
    print("=" * 78)
    print("汇总")
    print("=" * 78)
    failed = 0
    for name, desc, code, note in results:
        if code == 0:
            mark = "OK  "
        else:
            mark = "FAIL"
            failed += 1
        shown = "exit=%s" % code if code is not None else note
        print("  [%s] %-24s %s" % (mark, name, shown))

    print()
    print("=" * 78)
    if failed == 0:
        print("全部 %d 个脚本通过" % len(results))
    else:
        print("%d / %d 个脚本失败" % (failed, len(results)))
    print("=" * 78)

    # 说明：IDE 那几个脚本退出时可能出现 IDLE 自带的
    # "warning: callback failed in WindowList" —— 那是上游 bug，
    # 已用原生 IDLE 复现确认，与本项目无关，且不影响退出码。
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

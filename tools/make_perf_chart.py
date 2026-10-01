#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画性能对比图，输出纯 SVG。

用法（在项目根目录）：
    python tools/make_perf_chart.py            # 实际测量后画图
    python tools/make_perf_chart.py --dry-run  # 只看会写哪些文件

## 为什么不用 matplotlib

ADR-0001 定死了「纯 Python、无第三方库」，ADR-0003 连 json/pickle 都因为
「与不依赖现成工具的项目前提冲突」被否掉了。画个图就引 matplotlib，
是在打自己的脸。

而 SVG 本来就是一串 XML 文本 —— 用标准库拼字符串就能生成，
不需要任何绘图库。这条路比装 matplotlib 还短。

## 为什么画成"区间"而不是"一根柱子"

实测（14 轮采样）：
    pyPython 自身      253 ~ 279 微秒   离散 14%   ← 稳
    基线 A (timeit)   0.368 ~ 0.85 微秒  离散 120%  ← 很不稳
    基线 B (exec)     20 ~ 35 微秒      离散 59%   ← 不稳
    慢 A 倍数          653 ~ 736 倍     离散 12.5%
    慢 B 倍数          7.0 ~ 12.9 倍    离散 58%

基线 A/B 抖动这么大，是因为它们本身只有零点几微秒 ——
GC 一次、系统调度一次，就能让分母翻倍。

所以画"精确的一根柱子"是撒谎。这里画**中位数 + 实测范围**，
并且把采样次数和离散度直接写在图上。看图的人自己判断。

这跟 ADR-0001「两个基线都报、标注哪个没达标」是同一条原则：
不挑对自己有利的口径。
"""

import io
import math
import os
import statistics
import sys
import time
import timeit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pypython import (  # noqa: E402
    CPYTHON_EQUIVALENT, DEMO_2_SOURCE, evaluate_source,
)

OUT_SVG = os.path.join(ROOT, "docs", "perf.svg")

ROUNDS = 300     # 每次测量的回合数（与 pypython.py 用例 2 一致）
TRIALS = 7       # 重复几轮，用来取范围


# ---------------------------------------------------------------- 测量

def measure_a_trial():
    """跑一轮，返回 (pyPython微秒, 基线A微秒, 基线B微秒)。"""
    evaluate_source(DEMO_2_SOURCE)          # 热身

    t0 = time.perf_counter()
    for _ in range(ROUNDS):
        evaluate_source(DEMO_2_SOURCE)
    pypy = (time.perf_counter() - t0) / ROUNDS * 1e6

    code = compile("x = 1 + 1", "<baseline-a>", "exec")

    def once(_c=code):
        exec(_c, {})                        # noqa: S102 — 基线，见 ADR-0001

    base_a = timeit.timeit(once, number=ROUNDS) / ROUNDS * 1e6

    t0 = time.perf_counter()
    for _ in range(ROUNDS):
        exec(CPYTHON_EQUIVALENT, {})        # noqa: S102 — 基线，见 ADR-0001
    base_b = (time.perf_counter() - t0) / ROUNDS * 1e6

    return pypy, base_a, base_b


def collect(trials=TRIALS):
    rows = []
    for i in range(trials):
        p, a, b = measure_a_trial()
        rows.append((p, a, b, p / a, p / b))
    return rows


# ---------------------------------------------------------------- SVG

def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def svg_text(x, y, text, size=13, fill="#24292f", anchor="start",
             weight="normal", family="sans-serif"):
    return ('<text x="%g" y="%g" font-family="%s" font-size="%g" '
            'fill="%s" text-anchor="%s" font-weight="%s">%s</text>'
            % (x, y, family, size, fill, anchor, weight, esc(text)))


def build_svg(rows):
    """把实测结果画成一张对数轴对比图。

    版面分区（宽度 900）：
        0   ~ 150   Y 轴刻度
        150 ~ 640   三根柱子（绘图区）
        640 ~ 900   右侧结论栏（倍数 + 达标情况）
    柱子区必须给右侧结论栏让出位置，否则第三根柱子的数值标签
    会跟结论文字撞在一起 —— 这个撞过我一次，见 tools/README。
    """
    W, H = 900, 560
    ML, MR, MT, MB = 150, 260, 96, 118    # MR 给右侧结论栏留宽
    plot_w = W - ML - MR
    right_x = W - MR + 24                 # 结论栏文字左边界

    bars = []   # (标签, 中位数, 最小值, 最大值, 颜色, 说明)

    pypy = [r[0] for r in rows]
    a = [r[1] for r in rows]
    b = [r[2] for r in rows]
    ra = [r[3] for r in rows]
    rb = [r[4] for r in rows]

    bars.append(("pyPython 解释器\n（给源码字符串 → 跑出结果）",
                 statistics.median(pypy), min(pypy), max(pypy), "#8250df",
                 "本项目的被测对象"))
    bars.append(("基线 A · CPython\n（timeit 裸执行，不含编译）",
                 statistics.median(a), min(a), max(a), "#1f883d",
                 "最有利于本项目的口径"))
    bars.append(("基线 B · CPython\n（exec 全流程，含编译）",
                 statistics.median(b), min(b), max(b), "#bf8700",
                 "与 pyPython 同口径"))

    # 对数轴范围
    lo_all = min(min(x[2], x[1]) for x in bars)
    hi_all = max(max(x[3], x[1]) for x in bars)
    axis_lo = 10 ** math.floor(math.log10(lo_all))
    axis_hi = 10 ** math.ceil(math.log10(hi_all))
    if axis_hi == axis_lo:
        axis_hi = axis_lo * 10

    def y_of(v):
        t = (math.log10(v) - math.log10(axis_lo)) / (
            math.log10(axis_hi) - math.log10(axis_lo))
        return MT + (1 - t) * (H - MT - MB)

    out = []
    out.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">' % (W, H, W, H))
    out.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H))

    # 标题
    out.append(svg_text(W / 2, 36, "pyPython 性能对比", 21,
                        anchor="middle", weight="bold"))
    out.append(svg_text(
        W / 2, 60,
        "本项目的核心指标：越慢越好　·　对数轴　·　柱高为中位数，"
        "细线为 %d 轮实测范围" % TRIALS,
        12.5, fill="#57606a", anchor="middle"))
    out.append(svg_text(
        W / 2, 79,
        "测试机：本机本次　·　每轮 %d 回合　·　数字会随 GC 与负载漂移，"
        "只可用于比较量级" % ROUNDS,
        11.5, fill="#8c959f", anchor="middle"))

    # 网格线（每个数量级一根）
    e = int(math.log10(axis_lo))
    while 10 ** e <= axis_hi + 1e-9:
        v = 10 ** e
        if axis_lo <= v <= axis_hi:
            y = y_of(v)
            out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" '
                       'stroke="#d0d7de" stroke-width="1"/>'
                       % (ML, y, ML + plot_w, y))
            label = ("%g 微秒" % v) if v >= 1 else ("%g 微秒" % v)
            out.append(svg_text(ML - 10, y + 4, label, 11.5,
                                fill="#57606a", anchor="end"))
        e += 1

    # 柱子
    n = len(bars)
    slot = plot_w / n
    bar_w = slot * 0.44

    for i, (label, med, vmin, vmax, color, note) in enumerate(bars):
        cx = ML + slot * (i + 0.5)
        x = cx - bar_w / 2
        y_top = y_of(med)
        y_base = y_of(axis_lo)
        out.append('<rect x="%g" y="%g" width="%g" height="%g" fill="%s" '
                   'rx="3"/>' % (x, y_top, bar_w, y_base - y_top, color))

        # 范围线
        ymin, ymax = y_of(vmin), y_of(vmax)
        out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#24292f" '
                   'stroke-width="2"/>' % (cx, ymax, cx, ymin))
        for yy in (ymin, ymax):
            out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" '
                       'stroke="#24292f" stroke-width="2"/>'
                       % (cx - 9, yy, cx + 9, yy))

        # 数值
        out.append(svg_text(cx, y_top - 22, "%.1f" % med, 15,
                            anchor="middle", weight="bold", fill=color))
        out.append(svg_text(cx, y_top - 8, "微秒/次", 10.5,
                            anchor="middle", fill="#8c959f"))
        out.append(svg_text(cx, ymin + 16,
                            "%.2f ~ %.2f" % (vmin, vmax), 10.5,
                            anchor="middle", fill="#57606a"))

        # 说明
        ty = H - MB + 30
        for j, part in enumerate(label.split("\n")):
            out.append(svg_text(cx, ty + j * 15, part, 11.5,
                                anchor="middle"))
        out.append(svg_text(cx, ty + 2 * 15 + 4, note, 10.5,
                            anchor="middle", fill="#8c959f"))

    # 倍数标注（右侧结论栏）
    med_a = statistics.median(ra)
    med_b = statistics.median(rb)
    box_x = W - MR + 12
    box_w = MR - 32
    box_y = MT + 8
    out.append('<rect x="%g" y="%g" width="%g" height="196" fill="#f6f8fa" '
               'stroke="#d0d7de" rx="6"/>' % (box_x, box_y, box_w))
    out.append(svg_text(right_x, box_y + 26,
                        "相对基线慢多少（中位数）", 12,
                        fill="#57606a", weight="bold"))
    out.append(svg_text(right_x, box_y + 52,
                        "基线 A", 12, fill="#57606a"))
    out.append(svg_text(right_x, box_y + 72,
                        "%.0f 倍" % med_a, 18, fill="#1f883d",
                        weight="bold"))
    out.append(svg_text(right_x, box_y + 90,
                        "%.2f 个数量级" % math.log10(med_a), 11.5,
                        fill="#8c959f"))
    out.append(svg_text(right_x, box_y + 118,
                        "基线 B", 12, fill="#57606a"))
    out.append(svg_text(right_x, box_y + 138,
                        "%.1f 倍" % med_b, 18, fill="#bf8700",
                        weight="bold"))
    out.append(svg_text(right_x, box_y + 156,
                        "%.2f 个数量级" % math.log10(med_b), 11.5,
                        fill="#8c959f"))

    # 达标结论（不藏未达标的那个）
    ok_a = math.log10(med_a) >= 2
    ok_b = math.log10(med_b) >= 2
    verdict_y = box_y + 196 + 28
    out.append(svg_text(right_x, verdict_y, "需求「慢 ≥2 个数量级」",
                        12, fill="#57606a", weight="bold"))
    out.append(svg_text(right_x, verdict_y + 24,
                        "基线 A　" + ("达标 ✅" if ok_a else "未达标 ❌"),
                        13, fill="#1f883d" if ok_a else "#cf222e"))
    out.append(svg_text(right_x, verdict_y + 46,
                        "基线 B　" + ("达标 ✅" if ok_b else "未达标 ❌"),
                        13, fill="#1f883d" if ok_b else "#cf222e"))
    out.append(svg_text(right_x, verdict_y + 72,
                        "（B 未达标是如实的，", 11, fill="#8c959f"))
    out.append(svg_text(right_x, verdict_y + 88,
                        "　理由见下方与 ADR-0001）", 11, fill="#8c959f"))

    # 底注
    foot = ("基线 B 未达标是结构性的：exec 的编译是一次性 C 实现开销，"
            "而 pyPython 每次调用都重做纯 Python 词法+语法分析。")
    out.append(svg_text(ML, H - 22, foot, 11, fill="#8c959f"))

    out.append("</svg>")
    return "\n".join(out), (med_a, med_b, ra, rb)


def main():
    dry = "--dry-run" in sys.argv
    print("pyPython 性能图生成器（纯标准库，无第三方依赖）")
    print("=" * 70)
    print("采样：%d 轮 x %d 回合" % (TRIALS, ROUNDS))
    print()

    rows = collect()
    print("%6s %12s %12s %12s %10s %10s" %
          ("轮次", "pyPython", "基线A", "基线B", "慢A", "慢B"))
    print("-" * 70)
    for i, (p, a, b, ra, rb) in enumerate(rows, 1):
        print("%6d %12.2f %12.4f %12.2f %10.1f %10.1f"
              % (i, p, a, b, ra, rb))
    print("-" * 70)

    svg, (ma, mb, ras, rbs) = build_svg(rows)
    print()
    print("中位倍数：A = %.0f 倍  B = %.1f 倍" % (ma, mb))
    print("范围：A %.0f~%.0f   B %.1f~%.1f"
          % (min(ras), max(ras), min(rbs), max(rbs)))

    if dry:
        print()
        print("--dry-run：没写文件。会写到：%s" % OUT_SVG)
        return 0

    os.makedirs(os.path.dirname(OUT_SVG), exist_ok=True)
    with io.open(OUT_SVG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    print()
    print("已写出：%s（%d 字节）" % (OUT_SVG, len(svg.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())

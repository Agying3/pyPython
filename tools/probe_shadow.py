# -*- coding: utf-8 -*-
"""量卡片边缘：圆角、外侧阴影的暗度与抖动（玻璃感很大一部分来自这两样）。

做法：
  · 圆角：从卡片左右边界向内扫，找"该行第一个属于卡片的像素"，
    拟合半径；这里只做粗量（返回每行的内缩量）。
  · 阴影：卡片外侧 24px 内每 2px 取一行横向亮度，统计**均值**和**抖动**
    （相邻像素亮度一阶差分的绝对值均值）。阴影若带模糊，抖动会很小、
    亮度单调爬升；若是硬边框，抖动会很大。

用法：python tools/probe_shadow.py <截图> <x0> <y0> <x1> <y1>
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    shot = sys.argv[1]
    x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
    from PIL import Image
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    px = im.load()
    lum = lambda p: (p[0] * 299 + p[1] * 587 + p[2] * 114) / 1000.0

    print("=" * 70)
    print("%s  区域 %s" % (os.path.basename(shot), (x0, y0, x1, y1)))
    print("=" * 70)

    # —— 圆角：卡片底部左角
    print("\n底部左圆角（每行的内缩量，越大越圆）:")
    base_x = None
    for dy in range(0, 24, 2):
        y = y1 - 1 - dy
        row = [lum(px[x, y]) for x in range(x0 - 4, min(W, x0 + 40))]
        # 跳到卡片内部（亮度明显高于左侧壁纸且稳定）
        thr = max(row) * 0.7
        idx = next((i for i, v in enumerate(row) if v > thr), 0)
        print("  y-%02d 内缩 %2d px" % (dy, idx - 4))

    # —— 外侧阴影：取卡片左侧竖条，逐行向外
    print("\n左侧外 24px（均值亮度 / 逐像素抖动）:")
    for d in range(0, 25, 4):
        vals = []
        for y in range(y0 + 10, y1 - 10, 3):
            x = x0 - 1 - d
            if 0 <= x < W:
                vals.append(lum(px[x, y]))
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        jit = sum(abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))) / max(1, len(vals) - 1)
        print("  -%-2d  %.1f   抖动 %.2f" % (d + 1, avg, jit))

    print("\n卡片内 4 个角的亮度（看有没有内阴影/渐晕）:")
    for name, (cx, cy) in {
        "左上": (x0 + 8, y0 + 8), "右上": (x1 - 8, y0 + 8),
        "左下": (x0 + 8, y1 - 8), "右下": (x1 - 8, y1 - 8),
        "正中": ((x0 + x1) // 2, (y0 + y1) // 2),
    }.items():
        print("  %s  %.1f" % (name, lum(px[cx, cy])))


if __name__ == "__main__":
    main()

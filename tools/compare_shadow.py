# -*- coding: utf-8 -*-
"""同一位置比两张截图：卡片下沿往下的"暗影深度"。

为什么这么比：阴影强度不能靠"我感觉"，也不能只看 CSS 声明（两边用的不是同一档）。
   取卡片水平中点、从底边往下逐像素，跟**画面左下角没被卡片盖住的壁纸**
   做基准，算相对压暗量。两边用同一个算法，差值就是真实差距。

用法：
    python tools/compare_shadow.py <截图> <卡片中线x> <卡片底边y> <基准x> <基准y> [标签]
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lum = lambda p: (p[0] * 299 + p[1] * 587 + p[2] * 114) / 1000.0


def profile(px, W, H, x, y0, base, n=26):
    rows = []
    for dy in range(1, n):
        y = y0 + dy
        if y >= H:
            break
        v = lum(px[x, y])
        rows.append((dy, v, base - v))
    return rows


def main():
    from PIL import Image

    shot = sys.argv[1]
    x, y0 = int(sys.argv[2]), int(sys.argv[3])
    bx, by = int(sys.argv[4]), int(sys.argv[5])
    tag = sys.argv[6] if len(sys.argv) > 6 else os.path.basename(shot)

    im = Image.open(shot).convert("RGB")
    W, H = im.size
    px = im.load()
    base = lum(px[bx, by])

    print("=" * 62)
    print("%s   基准壁纸亮度 %.1f" % (tag, base))
    print("=" * 62)
    rows = profile(px, W, H, x, y0, base)
    for dy, v, d in rows:
        bar = "#" * max(0, int(d))
        print("  +%-3d %6.1f  压暗 %+6.1f  %s" % (dy, v, -d, bar))

    if rows:
        peak = max(rows, key=lambda t: t[2])
        print()
        print("最深压暗：+%d px 处 %.1f" % (peak[0], peak[2]))
        over5 = [dy for dy, v, d in rows if d > 5]
        print("压暗超过 5 的扩散范围：+1..+%d px" % (over5[-1] if over5 else 0))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""量卡片阴影的真实扩散：从卡片边界向外逐像素看亮度，反推 offset/blur/alpha。

为什么重写一次：#48 抄了 shadow-sm（0 2px 4px .075），但截图里卡片下方
明显压暗一大片，4px 扩散做不到那个效果 —— 说明生效的阴影不止这一条，
或者还有一层父级/伪元素的投影。只看一个 computed 属性不足以定案。

做法：
  · 在卡片**正下方**取一条竖线（阴影的 offset-y 方向），
    逐像素记亮度，跟"远离卡片的壁纸基准"比；
  · 同理取左侧竖线，看水平扩散；
  · 用衰减到 90% / 50% / 10% 的距离，反推 blur 半径与 alpha。

用法：python tools/probe_card_shadow.py <截图> <x> <卡片底边y> <基准x> <基准y>
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lum = lambda p: (p[0] * 299 + p[1] * 587 + p[2] * 114) / 1000.0


def profile(px, coords):
    return [round(lum(px[x, y]), 1) for (x, y) in coords]


def main():
    shot = sys.argv[1]
    x = int(sys.argv[2])          # 卡片中线 x
    y_bottom = int(sys.argv[3])   # 卡片底边 y
    bx = int(sys.argv[4]) if len(sys.argv) > 4 else x
    by = int(sys.argv[5]) if len(sys.argv) > 5 else y_bottom + 120

    from PIL import Image
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    px = im.load()

    print("=" * 70)
    print("卡片阴影剖面  %s" % os.path.basename(shot))
    print("=" * 70)

    base = lum(px[bx, by])
    inside = lum(px[x, y_bottom - 6])
    print("卡片内亮度        %.1f" % inside)
    print("远处壁纸基准      %.1f  (x=%d,y=%d)" % (base, bx, by))
    print()

    print("卡片下方逐像素（偏移 y，亮度，相对基准的差）:")
    rows = []
    for dy in range(1, 31):
        y = y_bottom + dy
        if y >= H:
            break
        v = lum(px[x, y])
        rows.append((dy, v))
        if dy <= 24:
            print("  +%-3d %6.1f  %+6.1f" % (dy, v, v - base))

    print()
    print("卡片左侧逐像素（偏移 x）:")
    for dx in range(1, 25):
        xx = x - 300 - dx   # 从卡片左边缘往外；调用时保证 x-300 是边缘
        if xx < 0:
            break
        v = lum(px[xx, y_bottom - 40])
        print("  -%-3d %6.1f  %+6.1f" % (dx, v, v - base))

    # 反推：最大暗度出现在哪个偏移、衰减到一半的位置
    if rows:
        dy_max, v_min = min(rows, key=lambda t: t[1])
        depth = base - v_min
        print()
        print("最暗处在 +%d px，比基准暗 %.1f" % (dy_max, depth))
        half = [dy for dy, v in rows if (base - v) < depth * 0.5]
        if half:
            print("暗度衰减到一半的位置：+%d px（≈ blur/2）" % half[0])
            print("→ 估 blur ≈ %d px，alpha ≈ %.2f" % (half[0] * 2, depth / 255.0))


if __name__ == "__main__":
    main()

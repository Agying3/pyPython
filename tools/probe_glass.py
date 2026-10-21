# -*- coding: utf-8 -*-
"""量"玻璃感"：卡片/左栏/页脚那几块像素做统计，判断底色是否真半透明、
阴影往外衰减多远。

为什么不能读 CSS：参考站暗色壁纸上放 rgba(66,66,66,.95) 的卡片，
   只看声明值像是"一块不透明的灰"。可"玻璃感"= 底色 + 阴影 + 圆角
   三者叠出来的观感，光看某一个属性判断不了，所以直接量像素。

做法：
  1. 卡片内取三块（左中右 / 上中下），比同一底色的 RGB 差异：
     差异大 = 壁纸透进来了（半透明或叠加），差异小 = 不透明；
  2. 卡片边缘往外扫一条线，看亮度相对远处壁纸的衰减幅度和距离，
     反推阴影 blur 大概多大。

用法：python tools/probe_glass.py <截图> <x0> <y0> <x1> <y1>
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def box_stat(px, W, H, x0, y0, x1, y1):
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    n = 0
    r = g = b = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = px[x, y]
            r += p[0]
            g += p[1]
            b += p[2]
            n += 1
    if not n:
        return (0, 0, 0, 0)
    return (round(r / n, 1), round(g / n, 1), round(b / n, 1), n)


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "_ref", "xing.png")
    from PIL import Image
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    px = im.load()

    x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6]) if len(sys.argv) > 5 \
        else (0, 0, W, H)

    print("=" * 68)
    print("玻璃感测量：%s  取样 %s" % (os.path.basename(shot), (x0, y0, x1, y1)))
    print("=" * 68)

    w, h = x1 - x0, y1 - y0
    spots = {
        "左上": (x0 + w // 6, y0 + h // 6),
        "中部": (x0 + w // 2, y0 + h // 2),
        "右下": (x0 + w * 5 // 6, y0 + h * 5 // 6),
    }
    vals = []
    for name, (cx, cy) in spots.items():
        st = box_stat(px, W, H, cx - 10, cy - 10, cx + 10, cy + 10)
        vals.append(st[:3])
        print("  %s  RGB %.1f, %.1f, %.1f" % ((name,) + st[:3]))

    spread = max(max(v[i] for v in vals) - min(v[i] for v in vals) for i in range(3))
    print("\n区域内色差极值 %.1f  → %s" % (
        spread, "基本均匀（不透）" if spread < 6 else "壁纸透过来了"))

    mid_y = min(H - 1, y0 + h // 2)
    base = box_stat(px, W, H, max(0, x0 - 26), mid_y - 2, max(1, x0 - 16), mid_y + 2)
    print("\n卡片左边缘向外 20px 亮度（基准=外侧壁纸 %.1f）:" % base[0])
    out = []
    for d in range(0, 21, 2):
        x = x0 - 1 - d
        if x < 0:
            break
        p = px[x, mid_y]
        out.append("-%-2d %5.1f" % (d + 1, sum(p) / 3))
    print("  " + " | ".join(out))


if __name__ == "__main__":
    main()

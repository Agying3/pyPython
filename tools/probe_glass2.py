# -*- coding: utf-8 -*-
"""量内容区的玻璃感：卡片底色 RGB + 与它下面壁纸的**局部**亮度相关性。

为什么不是"区域内色差"：卡片比壁纸亮得多，色差大并不能证明半透明 ——
真正能证明的是「壁纸某处偏亮，卡片同一位置也偏亮」，即逐位置相关。

输出：
  · 卡片内采样点的 RGB 均值
  · 卡片 RGB 与"卡片外同一行壁纸"的相关系数（>0.5 说明透出来了）
  · 从卡片边缘向外的亮度曲线（阴影 blur 大概多大）

用法：python tools/probe_glass2.py <截图> <x0> <y0> <x1> <y1>
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pearson(a, b):
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / (va ** 0.5 * vb ** 0.5)


def main():
    shot = sys.argv[1]
    x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
    from PIL import Image
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    px = im.load()

    print("=" * 70)
    print("玻璃感测量 %s 区域 %s" % (os.path.basename(shot), (x0, y0, x1, y1)))
    print("=" * 70)

    # 卡片内部：竖向采样，每 8 行取一行、横向每 20 列取一列
    rows = range(y0, y1, 8)
    inner = []
    for y in rows:
        for x in range(x0, x1, 20):
            inner.append(px[x, y])
    n = len(inner)
    avg = tuple(round(sum(p[i] for p in inner) / n, 1) for i in range(3))
    print("卡片内均值 RGB  %.1f, %.1f, %.1f   (%d 个采样点)" % (avg + (n,)))

    # 与同一行"卡片左侧壁纸"的亮度做相关 —— 卡片紧贴壁纸，局部亮度同向起伏
    band = 40  # 左侧取 40px 宽的壁纸条
    card_lum, wall_lum = [], []
    for y in rows:
        xs = [px[x, y] for x in range(x0, x1, 20)]
        ws = [px[x, y] for x in range(max(0, x0 - band), x0 - 2, 6)]
        if not xs or not ws:
            continue
        card_lum.append(sum(sum(p) for p in xs) / len(xs))
        wall_lum.append(sum(sum(p) for p in ws) / len(ws))
    r = pearson(card_lum, wall_lum)
    print("卡片亮度 vs 左侧壁纸亮度 相关系数 r = %.2f" % r)
    print("  → %s" % ("壁纸明显透进来（玻璃）" if r > 0.5
                      else "透得不明显（更接近实底）" if r > 0.2
                      else "看不到透过（实底 + 阴影）"))

    # 阴影：左右两侧向外扫
    for side in ("左", "右"):
        mid_y = y1 - 6
        line = []
        for d in range(0, 25, 3):
            x = x0 - 2 - d if side == "左" else x1 + 1 + d
            if 0 <= x < W:
                line.append("%d:%d" % (d, round(sum(px[x, mid_y]) / 3)))
        print("%s边缘外亮度 %s" % (side, "  ".join(line)))


if __name__ == "__main__":
    main()

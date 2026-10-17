# -*- coding: utf-8 -*-
"""量参考站首屏那行标题的真实字号 —— 用字形轮廓反推，不靠肉眼。

背景：#41/#42 之后本项目不再"看着像"就下结论。首屏标题是中文，
    getComputedStyle 只能给出 CSS 声明值（参考站是 40px 一类），
    但屏幕上真正占多高，取决于字体文件本身：汉仪唐美人的汉字实际高度
    只占 em 的 0.79，字距也留白很大。所以改成"从像素反推字号"。

做法：
  1. 从截图里找出标题那几行像素（亮度阈值，只取壁纸上明显发白的点）；
  2. 把每行字按横向空隙切成字块，得到每个字的**墨迹高度**；
  3. 用字体文件算同一个字在 1em 下的墨迹高度（unitsPerEm 归一）；
  4. 字号 = 屏幕墨迹高 / 字体墨迹高 × 1em。

用法：python tools/probe_hero_font.py [截图] [字体文件]
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ink_rows(im, box, thr=180):
    """返回 [(y_top, y_bottom, [x 区间...]), ...]，每个元素是一行字。"""
    px = im.load()
    x0, y0, x1, y1 = box
    rows = []
    for y in range(y0, y1):
        xs = [x for x in range(x0, x1)
              if px[x, y][0] > thr and px[x, y][1] > thr and px[x, y][2] > thr]
        if xs:
            rows.append((y, xs))
    lines, cur = [], []
    last_y = None
    for y, xs in rows:
        if last_y is not None and y - last_y > 3:
            lines.append(cur)
            cur = []
        cur.append((y, xs))
        last_y = y
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ys = [y for y, _ in ln]
        out.append((min(ys), max(ys), len(ln)))
    return out


def glyph_ink_ratio(font_path, ch):
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen

    f = TTFont(font_path)
    upm = f["head"].unitsPerEm
    cmap = f.getBestCmap()
    g = cmap.get(ord(ch))
    if not g:
        return None
    gs = f.getGlyphSet()
    bp = BoundsPen(gs)
    gs[g].draw(bp)
    if not bp.bounds:
        return None
    y0, y1 = bp.bounds[1], bp.bounds[3]
    return (y1 - y0) / float(upm)


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_ref", "xing.png")
    font = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        ROOT, "_ref", "fonts", "echo-13.woff2")

    from PIL import Image
    im = Image.open(shot).convert("RGB")
    W, H = im.size
    print("=" * 66)
    print("首屏标题字号反推（截图 %dx%d）" % (W, H))
    print("=" * 66)

    # 标题区：截图中部偏上，先粗扫再按行切
    lines = ink_rows(im, (int(W * .15), int(H * .40), int(W * .85), int(H * .50)))
    print("找到 %d 行亮像素" % len(lines))
    for (a, b, n) in lines:
        print("  y=%4d..%4d  高=%3d px  像素数=%d" % (a, b, b - a + 1, n))
    if not lines:
        print("没找到字，调阈值或截图区域")
        return 1

    # 取最高那行当标题
    a, b, _ = max(lines, key=lambda t: t[1] - t[0])
    ink_px = b - a + 1

    ratios = {}
    for ch in "小星文化博客的这们么":
        r = glyph_ink_ratio(font, ch)
        if r:
            ratios[ch] = round(r, 4)
    print()
    print("字体 %s 的汉字墨迹高度（em 归一）:" % os.path.basename(font))
    for k, v in ratios.items():
        print("  %s  %.4f em" % (k, v))

    common = [v for v in ratios.values()]
    if not common:
        return 1
    med = sorted(common)[len(common) // 2]
    px_size = ink_px / med
    print()
    print("屏幕墨迹高 %d px ÷ 字体墨迹 %.4f em = 字号 %.1f px" % (ink_px, med, px_size))
    print("（一个字的宽度同样反推：%d px 宽 ÷ %.2f em = 字号 %.1f px）" % (
        ink_px, med, ink_px / med))
    return 0


if __name__ == "__main__":
    sys.exit(main())

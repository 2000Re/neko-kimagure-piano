"""チャンネルのアイコンとバナーを生成する(動画と同じねこ・鍵盤・配色・フォント)。

使い方: python3 tools/make_branding.py [--out branding] [--name ねこのきまぐれピアノ] [--fur orange]
  icon.png   : アイコン(800x800。YouTube上では円形に切り抜かれる)
  banner.png : バナー(2560x1440。文字は全デバイスで表示される中央1546x423に収める)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cat_sprites import FURS, _render  # noqa: E402
from common import BG, hsv_to_rgb  # noqa: E402
from text import SERIF_L, draw_text  # noqa: E402

BGC = tuple(int(c) for c in BG)

def note_color(i, n):
    h = (0.55 + i / n * 0.8) % 1.0
    return tuple(int(c) for c in hsv_to_rgb(np.array([h]), np.array([0.6]), np.array([1.0]))[0] * 255)


def keyboard(d, x0, y0, width, height, n_white, pressed=()):
    """白鍵 n_white 本の鍵盤を描く。pressed は色を付ける白鍵の番号。"""
    wk = width / n_white
    for i in range(n_white):
        fill = note_color(i, n_white) if i in pressed else (236, 234, 228)
        d.rectangle([x0 + i * wk + 2, y0, x0 + (i + 1) * wk - 2, y0 + height], fill=fill)
    for i in range(n_white - 1):
        if i % 7 in (0, 1, 3, 4, 5):  # C# D# F# G# A#
            cx = x0 + (i + 1) * wk
            d.rectangle([cx - wk * 0.3, y0, cx + wk * 0.3, y0 + height * 0.62], fill=(30, 30, 36))


def icon(path, fur):
    """横向きに歩くねこが鍵盤の上にいるアイコン。円に切り抜かれても収まる大きさにしている。"""
    size = 800
    img = Image.new("RGB", (size, size), BGC)
    d = ImageDraw.Draw(img)
    key_top = 540
    keyboard(d, -40, key_top, size + 80, 300, 9, pressed=(3, 5))
    cat = Image.fromarray(_render(cat_rows("walk"), cat_tail(), fur))
    scale = 560 / cat.width
    cat = cat.resize((int(cat.width * scale), int(cat.height * scale)), Image.NEAREST)
    img.paste(cat, ((size - cat.width) // 2, key_top - cat.height + 6), cat)
    font = ImageFont.truetype(str(SERIF_L), 110)
    for (x, y), i in (((330, 260), 2), ((430, 150), 6)):  # しっぽと頭の間、背中の上
        d.text((x, y), "♪", font=font, fill=note_color(i, 9), anchor="mm")
    img.save(path)
    print(path)


def banner(path, fur, name):
    w, h = 2560, 1440
    img = Image.new("RGB", (w, h), BGC)
    d = ImageDraw.Draw(img)
    keyboard(d, 0, 1000, w, 440, 28, pressed=(5, 9, 16, 21))   # 下部の鍵盤(PC・テレビで見える)
    cx, cy = w / 2, h / 2
    draw_text(d, (cx, cy - 85), "ねこが歩くと、音楽になる。", SERIF_L, 50, (170, 180, 205), tracking=8)
    draw_text(d, (cx, cy + 45), name, SERIF_L, 112, (246, 242, 232), tracking=10)
    # 歩くねこ(安全領域の左端)と音符(右端)
    cat = Image.fromarray(_render(cat_rows("walk"), cat_tail(), fur))
    cat = cat.resize((cat.width * 9 // 14, cat.height * 9 // 14), Image.NEAREST)
    img.paste(cat, (int(cx - 765), int(cy + 195 - cat.height)), cat)  # 名前の行より下に置く
    font = ImageFont.truetype(str(SERIF_L), 90)
    for k, (dx, dy) in enumerate(((680, -60), (740, 15), (700, 90))):
        d.text((cx + dx, cy + dy), "♪", font=font, fill=note_color(k * 5 + 3, 20), anchor="mm")
    img.save(path)
    print(path)


def cat_rows(kind):
    import cat_sprites as cs
    return cs.WALK_BODY + cs.WALK_LEGS[0]


def cat_tail():
    import cat_sprites as cs
    return cs.TAIL_UP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="branding")
    ap.add_argument("--name", default="ねこのきまぐれピアノ")
    ap.add_argument("--fur", choices=list(FURS), default="orange")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    icon(out / "icon.png", args.fur)
    banner(out / "banner.png", args.fur, args.name)


if __name__ == "__main__":
    main()

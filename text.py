"""同梱フォントで日本語を描く。フォントはサブセットなので、収録外の文字は豆腐にせずエラーにする。"""
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
SERIF_L = FONT_DIR / "NotoSerifJP-Light.otf"


def _font(path, size):
    return ImageFont.truetype(str(path), size)


def check_glyphs(path, text):
    """同梱フォントはサブセットなので、収録外の文字があれば黙って豆腐にせず止める。"""
    from fontTools.ttLib import TTFont  # 生成時のみ必要
    cmap = TTFont(str(path), lazy=True).getBestCmap()
    missing = {c for c in text if ord(c) not in cmap and not c.isspace()}
    if missing:
        raise ValueError(f"{path.name} に無い文字: {''.join(sorted(missing))}(tools/subset_fonts.py を参照)")


def draw_text(d, xy, text, path, size, fill, tracking=0):
    check_glyphs(path, text)
    font = _font(path, size)
    if not tracking:
        d.text(xy, text, font=font, fill=fill, anchor="mm")
        return
    widths = [d.textlength(c, font=font) for c in text]
    x = xy[0] - (sum(widths) + tracking * (len(text) - 1)) / 2
    for c, w in zip(text, widths):
        d.text((x, xy[1]), c, font=font, fill=fill, anchor="lm")
        x += w + tracking

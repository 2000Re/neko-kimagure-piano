"""ドット絵のねこ(右向き16x11ドット)。歩く2コマ・跳ねる・座る2コマ・まばたき。"""
import numpy as np

# ---------------------------------------------------------------- ドット絵(右向き、16x11)
# F=毛 B=おなか・口元 D=目 P=鼻・耳の内側 .=透明
WALK_BODY = [
    "..........F...F.",
    "..........FP.PF.",
    "..........FFFFF.",
    "..........FDFDF.",
    "..........FBPBF.",
    "....FFFFFFFFFFF.",
    "..FFFFFFFFFFFF..",
    "..FFFFFFFFFFFF..",
    "..FFBBBBBBBBF...",
]
WALK_LEGS = [["..F.F.....F.F...", "..F.F.....F.F..."],
             ["...F.F.....F.F..", "...F.F.....F.F.."]]
JUMP_LEGS = ["..FF......FF....", "................"]
TAIL_DOWN = [(3, 0), (4, 0), (5, 1), (6, 1)]
TAIL_UP = [(0, 1), (1, 0), (2, 0), (3, 0), (4, 1), (5, 1), (6, 1)]

SIT = [
    "..........F...F.",
    "..........FP.PF.",
    "..........FFFFF.",
    "..........FDFDF.",
    "..........FBPBF.",
    ".........FFFFFF.",
    "........FFFFFFF.",
    ".......FFFFFFBF.",
    ".......FFFFFFBF.",
    ".......FFFFFFBF.",
    "......FFFF.FFFF.",
]
SIT_TAIL = [[(10, 1), (10, 2), (10, 3), (10, 4), (10, 5)],          # 地面に沿って伸ばす
            [(9, 1), (10, 2), (10, 3), (10, 4), (10, 5)]]           # 先だけ持ち上げる
BLINK_ROW = (3, "..........FFFFF.")

PX = 14  # ドット1つの大きさ(px)
SPRITE_W, SPRITE_H = 16 * PX, 11 * PX
FURS = {
    "orange": {"F": (232, 150, 72), "B": (250, 232, 205), "D": (40, 30, 30), "P": (240, 140, 150)},
    "gray":   {"F": (150, 152, 165), "B": (225, 225, 232), "D": (30, 30, 40), "P": (235, 150, 160)},
    "white":  {"F": (240, 238, 232), "B": (255, 255, 255), "D": (60, 70, 90), "P": (245, 150, 165)},
    "tuxedo": {"F": (58, 58, 70), "B": (240, 240, 240), "D": (230, 210, 90), "P": (240, 150, 160)},
}


def _render(rows, extra, fur):
    img = np.zeros((11 * PX, 16 * PX, 4), dtype=np.uint8)
    grid = [list(r) for r in rows]
    for y, x in extra:
        grid[y][x] = "F"
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            if c != ".":
                img[y * PX:(y + 1) * PX, x * PX:(x + 1) * PX] = (*FURS[fur][c], 255)
    return img


def build_sprites(fur):
    """(名前, 向き) → RGBA画像"""
    base = {}
    for leg in (0, 1):
        tail = TAIL_UP if leg else TAIL_DOWN
        base[f"walk{leg}"] = _render(WALK_BODY + WALK_LEGS[leg], tail, fur)
    base["jump"] = _render(WALK_BODY + JUMP_LEGS, TAIL_UP, fur)
    for t in (0, 1):
        base[f"sit{t}"] = _render(SIT, SIT_TAIL[t], fur)
        blink = list(SIT)
        blink[BLINK_ROW[0]] = BLINK_ROW[1]
        base[f"sit{t}_blink"] = _render(blink, SIT_TAIL[t], fur)
    return {(k, d): (v if d > 0 else v[:, ::-1]) for k, v in base.items() for d in (1, -1)}

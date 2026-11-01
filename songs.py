"""知っている曲(作者の死後70年以上たった曲)を、ねこに弾かせる。

ランダムに歩いて踏んだ音が鳴る通常回とは逆に、先にメロディがあり、
その鍵盤を足が踏むように、ねこの立ち位置・向き・歩く/跳ねるを決める。
音は今までどおり「足の下の鍵盤」が鳴る(ねこがその鍵盤の上にいるときにだけ鳴らす)。
"""
import math

from cat_sprites import PX
from common import DURATION, FPS
from piano import FRONT, KEYS, MAX_X, STEP, WK

# 音名 → MIDI(C4=60)。"#" は半音上げ
_NAME = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    n = _NAME[name[0]] + (1 if "#" in name else 0)
    return 12 * (int(name[-1]) + 1) + n


KEY_BY_MIDI = {k["midi"]: k for k in KEYS}


def center(m):
    k = KEY_BY_MIDI[m]
    return (k["x0"] + k["x1"]) / 2


def half_width(m):
    k = KEY_BY_MIDI[m]
    return (k["x1"] - k["x0"]) / 2 - 4


# ---------------------------------------------------------------- 曲
# どれも作者が亡くなって70年以上たった曲か、作者不明の古い曲(民謡など)。使うのはメロディだけで、
# 歌詞(日本語訳詞には著作権が残っているものがある)は使わない。
# 楽譜の書き方: "音名:拍" を空白区切り。"-" は休符。拍の長さ(秒)は曲ごとに決める。4つめの数は移調(半音)。
# 2オクターブ(C4〜B5)に収まるように移調してある。冒頭の1〜2フレーズだけ(7秒の動画に収める)。
MELODIES = {
    "twinkle": ("きらきら星", 0.37,
                "G4:1 G4:1 D5:1 D5:1 E5:1 E5:1 D5:2 C5:1 C5:1 B4:1 B4:1 A4:1 A4:1 G4:2"),
    "kaeru": ("かえるの合唱", 0.34,
              "C5:1 D5:1 E5:1 F5:1 E5:1 D5:1 C5:1 -:1 E5:1 F5:1 G5:1 A5:1 G5:1 F5:1 E5:2"),
    "mary": ("メリーさんのひつじ", 0.36,
             "E5:1 D5:1 C5:1 D5:1 E5:1 E5:1 E5:2 D5:1 D5:1 D5:2 E5:1 G5:1 G5:2"),
    "choucho": ("ちょうちょう", 0.34,
                "G4:1 E4:1 E4:2 F4:1 D4:1 D4:2 C4:1 D4:1 E4:1 F4:1 G4:1 G4:1 G4:2", 7),
    "london": ("ロンドン橋", 0.36,
               "G4:1.5 A4:0.5 G4:1 F4:1 E4:1 F4:1 G4:2 D4:1 E4:1 F4:2 E4:1 F4:1 G4:2", 7),
    "jinglebells": ("ジングルベル", 0.33,
                    "E5:1 E5:1 E5:2 E5:1 E5:1 E5:2 E5:1 G5:1 C5:1.5 D5:0.5 E5:4"),
    # ---- クリスマスの曲(12月に優先して選ぶ。CHRISTMAS を参照)
    "silentnight": ("きよしこの夜", 0.25,
                    "G4:1.5 A4:0.5 G4:1 E4:3 G4:1.5 A4:0.5 G4:1 E4:3 D5:2 D5:1 B4:3 C5:2 C5:1 G4:3"),
    "joytotheworld": ("もろびとこぞりて", 0.3,
                      "C5:2 B4:1.5 A4:0.5 G4:3 F4:1 E4:2 D4:2 C4:3", 5),
    "wewish": ("おめでとうクリスマス", 0.33,
               "G4:1 C5:1 C5:0.5 D5:0.5 C5:0.5 B4:0.5 A4:1 A4:1 A4:1 D5:1 D5:0.5 E5:0.5 D5:0.5 C5:0.5 "
               "B4:1 G4:1 G4:1 A4:1 D5:1 B4:1 C5:2"),
    "deckthehalls": ("ひいらぎかざろう", 0.33,
                     "G5:1.5 F5:0.5 E5:1 D5:1 C5:1 D5:1 E5:1 C5:1 D5:0.5 E5:0.5 F5:0.5 D5:0.5 E5:1.5 D5:0.5 C5:1 B4:1 C5:2"),
    "joy": ("歓喜の歌(ベートーヴェン)", 0.34,
            "E4:1 E4:1 F4:1 G4:1 G4:1 F4:1 E4:1 D4:1 C4:1 C4:1 D4:1 E4:1 E4:1.5 D4:0.5 D4:2", 7),
    "unmei": ("運命(ベートーヴェン)", 0.17,
              "-:1 G4:1 G4:1 G4:1 D#4:7 -:2 F4:1 F4:1 F4:1 D4:9", 5),
    "elise": ("エリーゼのために(ベートーヴェン)", 0.2,
              "E5:1 D#5:1 E5:1 D#5:1 E5:1 B4:1 D5:1 C5:1 A4:2 -:1 C4:1 E4:1 A4:1 B4:2 -:1 E4:1 G#4:1 B4:1 C5:3"),
    "turkish": ("トルコ行進曲(モーツァルト)", 0.16,
                "G#4:1 F#4:1 F4:1 F#4:1 A4:4 B4:1 A4:1 G#4:1 A4:1 C#5:4 "
                "D5:1 C#5:1 C5:1 C#5:1 G#5:1 F#5:1 F5:1 F#5:1 G#5:1 F#5:1 F5:1 F#5:1 A5:4"),
    "wedding": ("結婚行進曲(ワーグナー)", 0.38,
                "G4:1 C5:0.75 C5:0.25 C5:2 G4:1 D5:0.75 B4:0.25 C5:2"),
    "saints": ("聖者の行進", 0.21,
               "C5:1 E5:1 F5:1 G5:4 C5:1 E5:1 F5:1 G5:4 C5:1 E5:1 F5:1 G5:2 E5:2 C5:2 E5:2 D5:4"),
    "hotaru": ("蛍の光(スコットランド民謡)", 0.4,
               "G4:1 C5:1.5 C5:0.5 C5:1 E5:1 D5:1.5 C5:0.5 D5:1 E5:1 C5:1.5 C5:0.5 E5:1 G5:1 A5:3"),
    "yankee": ("アルプス一万尺", 0.3,
               "C5:1 C5:1 D5:1 E5:1 C5:1 E5:1 D5:1 G4:1 C5:1 C5:1 D5:1 E5:1 C5:2 B4:2"),
    "macdonald": ("ゆかいな牧場", 0.34,
                  "G4:1 G4:1 G4:1 D4:1 E4:1 E4:1 D4:2 B4:1 B4:1 A4:1 A4:1 G4:3", 5),
    "goinghome": ("家路(ドヴォルザーク)", 0.42,
                  "E4:1.5 G4:0.5 G4:2 E4:1.5 D4:0.5 C4:2 D4:1 E4:1 G4:1 E4:1 D4:3", 7),
    "brahms": ("ブラームスの子守歌", 0.3,
               "E4:1 E4:1 G4:3 E4:1 E4:1 G4:3 E4:1 G4:1 C5:2 B4:2 A4:1 A4:1 G4:3"),
}

T0 = 0.15  # 最初の音(1コマ目からすぐ音が鳴るように)


def melody_events(score, beat, shift=0):
    """shift: 移調(半音)。画面の端に寄りすぎないよう、まん中あたりで弾ける高さにする。"""
    ev, t = [], T0
    for tok in score.split():
        name, length = tok.split(":")
        if name != "-":
            ev.append((round(t, 4), [midi(name) + shift], 0.85))
        t += float(length) * beat
    return ev


def nekofunjatta():
    """ねこふんじゃった(作者不明の古い曲)。嬰ヘ長調、黒鍵だけ。

    「ねこ」(2つの短い音)→「ふん」(低い音)→「じゃっ」「た」(和音2回)をくり返す。
    I(F#)→I→V7(C#7)→I。8分音符=0.3秒。
    """
    e, t0 = 0.30, T0
    ev = [(t0, [midi("D#5")], 0.8), (t0 + e / 2, [midi("C#5")], 0.8)]
    bars = [("F#4", ["A#4", "C#5"]), ("F#4", ["A#4", "C#5"]),
            ("G#4", ["B4", "C#5"]), ("F#4", ["A#4", "C#5"])]
    T = t0 + e
    for b, (bass, chord) in enumerate(bars):
        ev.append((T, [midi(bass)], 1.0))
        ev.append((T + e, [midi(c) for c in chord], 0.7))
        if b < len(bars) - 1:
            ev.append((T + 2 * e, [midi(c) for c in chord], 0.7))
            ev.append((T + 3 * e, [midi("D#5")], 0.8))
            ev.append((T + 3.5 * e, [midi("C#5")], 0.8))
        T += 4 * e
    return [(round(t, 4), ms, v) for t, ms, v in ev]


# 12月は、知っている曲の回をクリスマスの曲から選ぶ。12月以外はクリスマスの曲を選ばない
CHRISTMAS = {"jinglebells", "silentnight", "joytotheworld", "wewish", "deckthehalls"}

# 曲のID → (曲名, 打鍵リストを作る関数)
SONGS = {"nekofunjatta": ("ねこふんじゃった", nekofunjatta)}
for _id, (_name, _beat, _score, *_shift) in MELODIES.items():
    SONGS[_id] = (_name, lambda s=_score, b=_beat, sh=(_shift or [0])[0]: melody_events(s, b, sh))


# ---------------------------------------------------------------- 立ち位置の計算
PAW_COLS = [12, 10, 7, 4, 2]  # 鍵盤を押せる足の列(前足 → 後ろ足)


def paw_offset(col, facing):
    sx = col if facing > 0 else 15 - col
    return sx * PX + PX / 2


def fit_pose(keys, facing, prev_x):
    """keys を足で押せる x を探す。前足を優先し、前の位置から動く距離が短いものを選ぶ。"""
    keys = sorted(keys, key=center, reverse=facing > 0)  # 進む向きの先頭の鍵盤から
    best = None
    cols_list = [[c] for c in PAW_COLS] if len(keys) == 1 else \
        [[a, b] for a in PAW_COLS for b in PAW_COLS if a > b] if len(keys) == 2 else \
        [[a, b, c] for a in PAW_COLS for b in PAW_COLS for c in PAW_COLS if a > b > c]
    for cols in cols_list:
        # 1つめの鍵盤の中央に1本目の足を置き、残りの足が鍵盤の中に入るか
        xs = [center(k) - paw_offset(c, facing) for k, c in zip(keys, cols)]
        x = sum(xs) / len(xs)
        if not 0 <= x <= MAX_X:
            continue
        if any(abs(x + paw_offset(c, facing) - center(k)) > half_width(k) for k, c in zip(keys, cols)):
            continue
        cost = abs(x - prev_x) + (0 if cols[0] == FRONT else 40)
        if best is None or cost < best[0]:
            best = (cost, x)
    if best is None:
        raise ValueError(f"足が届かない: {keys} facing={facing}")
    return best[1]


def plan_song(events):
    """曲の打鍵 → (コマごとのねこの姿, 打鍵リスト)。

    姿は {x, facing, sprite, yoff}。打鍵は通常回と同じ (ステップ, 鍵盤, 強さ)。
    """
    centers = [sum(center(m) for m in ms) / len(ms) for _, ms, _ in events]
    poses = []
    facing = 1 if len(centers) < 2 or centers[1] >= centers[0] else -1
    x = None
    for i, (t, ms, _) in enumerate(events):
        if i > 0 and abs(centers[i] - centers[i - 1]) > 1:
            facing = 1 if centers[i] > centers[i - 1] else -1
        try:
            x = fit_pose(ms, facing, centers[i] if x is None else x)
        except ValueError:  # 端の鍵盤は、その向きでは足が届かないことがある → 向きを変える
            facing = -facing
            x = fit_pose(ms, facing, centers[i] if x is None else x)
        poses.append((t, x, facing))

    n_frames = int(DURATION * FPS)
    frames = []
    for fi in range(n_frames):
        t = fi / FPS
        # 今いる区間: 最後に踏んだ打鍵 i と次の打鍵 i+1
        i = max([j for j, p in enumerate(poses) if p[0] <= t + 1e-6], default=-1)
        if i < 0:
            t1, x1, f1 = poses[0]
            frames.append({"x": x1, "facing": f1, "sprite": "walk0", "yoff": 0})
            continue
        t0, x0, f0 = poses[i]
        leg = i % 2
        if i == len(poses) - 1:
            # 弾き終えたら、少し間をおいてその場でおすわり
            sit = t - t0 > 0.6
            frames.append({"x": x0, "facing": f0, "sprite": ("sit0" if sit else f"walk{leg}"),
                           "yoff": 0, "blink": sit and 0.9 < t - t0 - 0.6 < 1.05})
            continue
        t1, x1, f1 = poses[i + 1]
        gap, dx = t1 - t0, x1 - x0
        if abs(dx) > 1.3 * WK:      # 遠いので跳ねる
            dur = min(gap * 0.9, 0.42)
            start = t1 - dur
            if t < start:
                frames.append({"x": x0, "facing": f0, "sprite": f"walk{leg}", "yoff": 0})
            else:
                p = (t - start) / dur
                frames.append({"x": x0 + dx * p, "facing": 1 if dx > 0 else -1, "sprite": "jump",
                               "yoff": -int(min(90, 25 + 0.25 * abs(dx)) * math.sin(math.pi * p))})
        else:                        # 近いので歩く(次の音の直前に一歩)
            dur = min(gap, 0.22)
            start = t1 - dur
            if t < start:
                frames.append({"x": x0, "facing": f0, "sprite": f"walk{leg}", "yoff": -3 if leg else 0})
            else:
                p = (t - start) / dur
                f = f1 if p > 0.3 else f0
                frames.append({"x": x0 + dx * p, "facing": f, "sprite": f"walk{1 - leg}",
                               "yoff": -3 if 1 - leg else 0})
    notes = [(t / STEP, KEY_BY_MIDI[m], v) for t, ms, v in events for m in ms]
    return frames, notes


def check_paws(frames, notes):
    """打鍵の瞬間に、その鍵盤の上にねこの足があるか(描画と音がずれていないか)を確かめる。"""
    bad = []
    for s, k, _ in notes:
        fr = frames[min(math.ceil(s * STEP * FPS - 1e-6), len(frames) - 1)]
        ok = any(abs(fr["x"] + paw_offset(c, fr["facing"]) - center(k["midi"])) <= half_width(k["midi"]) + 2
                 for c in PAW_COLS)
        if not ok:
            bad.append((round(s * STEP, 2), k["midi"]))
    return bad



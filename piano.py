"""ねこがピアノの鍵盤の上を歩き、踏んだ鍵盤の音が鳴る動画を作る。

ねこの行動(歩く・座る・跳ねる・振り返る)と、歩き方(歩幅・テンポ・足の運び・ためらい)を
毎回ランダムに組み合わせる。足の下の鍵盤をそのまま押す(白鍵も黒鍵も)。
"""
import math
import random
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cat_sprites import PX, build_sprites
from common import BG, DURATION, FADE_OUT, FPS, H, SR, W, fade_curve, fft_convolve, hsv_to_rgb, make_reverb_ir
from text import SERIF_L, draw_text

# ---------------------------------------------------------------- 鍵盤
WHITE_KEYS = 14                    # 2オクターブ(C4〜B5)
WK = W / WHITE_KEYS                # 白鍵の幅
KEY_TOP, KEY_H = 900, 520          # 白鍵の上端と高さ(下端1420はShortsのUIに被らない)
BK_W, BK_H = WK * 0.6, KEY_H * 0.62
WHITE_OFFS = [0, 2, 4, 5, 7, 9, 11]
BLACK_AFTER = {0: 1, 1: 3, 3: 6, 4: 8, 5: 10}  # 白鍵の番号(オクターブ内) → その右の黒鍵の半音
BASE_MIDI = 60


def build_keys():
    """鍵盤の一覧: {midi, black, x0, x1}。"""
    keys = []
    for i in range(WHITE_KEYS):
        octv, n = divmod(i, 7)
        keys.append({"midi": BASE_MIDI + 12 * octv + WHITE_OFFS[n], "black": False, "x0": i * WK, "x1": (i + 1) * WK})
        if n in BLACK_AFTER and i < WHITE_KEYS - 1:
            cx = (i + 1) * WK
            keys.append({"midi": BASE_MIDI + 12 * octv + BLACK_AFTER[n], "black": True,
                         "x0": cx - BK_W / 2, "x1": cx + BK_W / 2})
    return keys


KEYS = build_keys()
BLACKS = [k for k in KEYS if k["black"]]


def key_at(x, mode="all"):
    """足の x 座標 → 押される鍵盤。"""
    if mode == "black":
        return min(BLACKS, key=lambda k: abs((k["x0"] + k["x1"]) / 2 - x))
    for k in BLACKS:  # 黒鍵は白鍵の上に乗っているので先に判定
        if k["x0"] <= x < k["x1"]:
            return k
    return next(k for k in KEYS if not k["black"] and k["x0"] <= x < k["x1"])


# ---------------------------------------------------------------- ねこの行動と打鍵
SPRITE_W, SPRITE_H = 16 * PX, 11 * PX
STEP = 0.1                         # 行動の単位(秒)
N_STEPS = int(DURATION / STEP)
JUMP_PX, JUMP_STEPS, JUMP_HEIGHT = 46, 5, 90
MAX_X = W - SPRITE_W


def paw_x(x, facing, px_in_sprite):
    sx = px_in_sprite if facing > 0 else 15 - px_in_sprite
    return x + sx * PX + PX / 2


FRONT, MID, BACK = 12, 7, 3  # 前足・おなかの下・後ろ足(ドット絵上の列)
GAITS = {  # 足の運び: 着地ごとにどの足で押すか(繰り返し)
    "交互": [[FRONT], [BACK]],
    "前前後後": [[FRONT], [FRONT], [BACK], [BACK]],
    "前足だけ": [[FRONT]],
    "そろえて": [[FRONT, BACK]],          # 前後の足で同時に押す(2音の和音)
    "気まぐれ": None,                      # 毎回ランダムに選ぶ
}


def plan_and_notes(rng, mode="all"):
    """ステップごとの行動と、打鍵(ステップ・鍵盤・強さ)を作る。

    歩くたびに「歩き方」(歩幅・テンポ・足の運び・ためらい)を毎回ランダムに決めるので、
    メロディの形が回ごとに変わる。
    """
    plan, notes = [], []
    x = rng.uniform(0, MAX_X)
    facing = rng.choice([1, -1])
    state = "walk"
    while len(plan) < N_STEPS:
        s0 = len(plan)
        if state == "walk":
            n = rng.randint(8, 16)
            stride = rng.uniform(10, 32)               # 1ステップで進むpx(小股〜大股)
            every = rng.choice([1, 2, 2, 3])           # 何ステップごとに着地するか(テンポ)
            gait = GAITS[rng.choice(list(GAITS))]
            hesitate = rng.choice([0.0, 0.0, 0.15])    # 足を止めて休符にする確率
            leg, landing = 0, 0
            for i in range(n):
                if i % every == 0:
                    leg ^= 1  # 着地ごとに足の絵を切り替える
                    if rng.random() >= hesitate:
                        paws = gait[landing % len(gait)] if gait else rng.choice([[FRONT], [BACK], [MID]])
                        vel = 0.7 if len(paws) > 1 else 0.85
                        for px in paws:
                            notes.append((s0 + i, key_at(paw_x(x, facing, px), mode), vel))
                    landing += 1
                plan.append({"x": x, "facing": facing, "state": "walk", "i": i, "n": n, "leg": leg})
                x += stride * facing
                if not 0 <= x <= MAX_X:
                    facing, x = -facing, min(max(x, 0), MAX_X)
            r = rng.random()
            state = "sit" if r < 0.35 else "jump" if r < 0.8 else "walk"
            if state == "walk":
                facing = -facing
        elif state == "sit":
            n = rng.randint(7, 11)
            plan += [{"x": x, "facing": facing, "state": "sit", "i": i, "n": n} for i in range(n)]
            # 座った瞬間に、おしりの下の鍵盤を1〜3つ、そっと押す
            for px in rng.sample([4, 7, 10], rng.randint(1, 3)):
                notes.append((s0, key_at(paw_x(x, facing, px), mode), 0.5))
            state = "walk"
        else:
            if not 0 <= x + JUMP_PX * JUMP_STEPS * facing <= MAX_X:
                facing = -facing
            for i in range(JUMP_STEPS):
                plan.append({"x": x, "facing": facing, "state": "jump", "i": i, "n": JUMP_STEPS})
                x += JUMP_PX * facing
            # 着地: 2〜3か所を同時に強く
            land = s0 + JUMP_STEPS - 1
            lx = x - JUMP_PX * facing
            for px in ([FRONT, BACK] if rng.random() < 0.6 else [FRONT, MID, BACK]):
                notes.append((land, key_at(paw_x(lx, facing, px), mode), 1.0))
            state = "walk"
    plan = plan[:N_STEPS]
    last = (DURATION - FADE_OUT + 0.4) / STEP  # フェードアウト中は新しい音を鳴らさない
    notes = [(s, k, v) for s, k, v in notes if s < last]
    return plan, notes


def melody_signature(notes):
    """同じ曲かどうかの判定用。音の並びを「音程差」で表すので、移調しただけの同じ曲も同じ値になる。
    同時に押した音(和音)は低い順に並べる。"""
    seq = [k["midi"] for s, k, _ in sorted(notes, key=lambda n: (n[0], n[1]["midi"]))]
    return ",".join(str(b - a) for a, b in zip(seq, seq[1:]))


def pick_performance(seed, mode="all", used_signatures=frozenset(), max_tries=50):
    """過去と同じ曲にならない演奏を選ぶ。被ったらシードをずらして作り直す。"""
    for t in range(max_tries):
        rng = random.Random(seed * 1000 + t)
        plan, notes = plan_and_notes(rng, mode)
        sig = melody_signature(notes)
        if sig not in used_signatures:
            return rng, plan, notes, sig
    raise RuntimeError("過去と被らない演奏が見つからない")


# ---------------------------------------------------------------- 音

def piano_tone(f, k):
    """倍音ごとに減衰の速さを変えた、素朴なピアノ風の音。"""
    w = np.zeros_like(k)
    for h, a in ((1, 1.0), (2, 0.45), (3, 0.22), (4, 0.12), (5, 0.06)):
        fh = f * h * (1 + 0.0004 * h * h)  # 弦のわずかなインハーモニシティ
        w += a * np.sin(2 * np.pi * fh * k) * np.exp(-k * h ** 0.8 / 1.4)
    return w * np.minimum(k / 0.003, 1.0)


def synth(notes, seed):
    n = int(DURATION * SR)
    left, right = np.zeros(n), np.zeros(n)
    rng = random.Random(seed)
    length = int(2.5 * SR)
    for s, key, vel in notes:
        p0 = int((s * STEP + rng.uniform(0, 0.01)) * SR)
        seg = min(length, n - p0)
        if seg <= 0:
            continue
        k = np.arange(seg) / SR
        f = 440.0 * 2 ** ((key["midi"] - 69) / 12)
        w = vel * 0.3 * piano_tone(f, k)
        pan = ((key["x0"] + key["x1"]) / 2 / W) * 1.4 - 0.7
        a = (pan + 1) * np.pi / 4
        left[p0:p0 + seg] += math.cos(a) * w
        right[p0:p0 + seg] += math.sin(a) * w
    ir_l, ir_r = make_reverb_ir(np.random.default_rng(seed))
    mono = (left + right) / 2
    left, right = left + 0.45 * fft_convolve(mono, ir_l), right + 0.45 * fft_convolve(mono, ir_r)
    out = np.stack([left, right], axis=1)
    fade = int(FADE_OUT * SR)
    out[-fade:] *= fade_curve(np.linspace(1, 0, fade))[:, None]
    out /= np.abs(out).max()
    out = np.tanh(out * 1.2) / np.tanh(1.2) * 0.89
    return (out * 32767).astype(np.int16)


# ---------------------------------------------------------------- 映像

def key_color(key):
    h = ((key["midi"] - BASE_MIDI) / 24 * 0.8 + 0.55) % 1.0
    return tuple(int(c) for c in hsv_to_rgb(np.array([h]), np.array([0.6]), np.array([1.0]))[0] * 255)


def make_drawer(plan, notes, fur):
    """t 秒時点の1コマを返す関数を作る。動画にも、サムネイル用の静止画にも使う。"""
    sprites = {k: Image.fromarray(v) for k, v in build_sprites(fur).items()}
    note_font = ImageFont.truetype(str(SERIF_L), 64)
    # 画面上部は問いかけだけ。番号は画面に出さず、YouTubeのタイトル末尾にだけ付ける
    header = Image.new("RGB", (W, 300), tuple(int(c) for c in BG))
    d = ImageDraw.Draw(header)
    draw_text(d, (W / 2, 170), "このねこ、何の曲を弾く？", SERIF_L, 76, (244, 240, 230), tracking=4)
    press = [(s * STEP, key, vel) for s, key, vel in notes]

    def draw(t, fade=True):
        img = Image.new("RGB", (W, H), tuple(int(c) for c in BG))
        img.paste(header, (0, 0))
        d = ImageDraw.Draw(img)
        down = {id(k): max(0.0, 1 - (t - t0) / 0.22) for t0, k, _ in press if 0 <= t - t0 < 0.22}
        for k in KEYS:  # 白鍵 → 黒鍵の順に描く
            if k["black"]:
                continue
            p = down.get(id(k), 0)
            y = KEY_TOP + 8 * p
            fill = tuple(int(c * (1 - 0.35 * p) + kc * 0.35 * p) for c, kc in zip((236, 234, 228), key_color(k)))
            d.rectangle([k["x0"] + 2, y, k["x1"] - 2, KEY_TOP + KEY_H], fill=fill)
        for k in BLACKS:
            p = down.get(id(k), 0)
            y = KEY_TOP + 6 * p
            fill = tuple(int(30 * (1 - p) + kc * p * 0.8) for kc in key_color(k))
            d.rectangle([k["x0"], y, k["x1"], KEY_TOP + BK_H + 6 * p], fill=fill)
        # 鍵盤から立ちのぼる音符
        for t0, k, vel in press:
            age = t - t0
            if 0 <= age < 1.2:
                a = 1 - age / 1.2
                cx = (k["x0"] + k["x1"]) / 2 + 18 * math.sin(age * 5 + k["midi"])
                cy = KEY_TOP - SPRITE_H - 30 - 320 * age
                col = tuple(int(BG[i] + (key_color(k)[i] - BG[i]) * a) for i in range(3))
                d.text((cx, cy), "♪", font=note_font, fill=col, anchor="mm")
        # ねこ
        s = min(int(t / STEP), N_STEPS - 1)
        frac = t / STEP - s
        pl = plan[s]
        nx = plan[min(s + 1, N_STEPS - 1)]
        x = pl["x"] + (nx["x"] - pl["x"]) * frac if nx["state"] == pl["state"] else pl["x"]
        yoff = 0
        if pl["state"] == "walk":
            name, yoff = f"walk{pl['leg']}", (0 if pl["leg"] == 0 else -3)
        elif pl["state"] == "sit":
            name = f"sit{(pl['i'] // 3) % 2}" + ("_blink" if pl["i"] == pl["n"] // 2 else "")
        else:
            name = "jump"
            yoff = -int(JUMP_HEIGHT * math.sin(math.pi * (pl["i"] + frac) / pl["n"]))
        spr = sprites[(name, pl["facing"])]
        img.paste(spr, (int(x), KEY_TOP - SPRITE_H + 2 + yoff), spr)
        frame = np.asarray(img, dtype=np.float64)
        if fade and t > DURATION - FADE_OUT:
            frame = BG + (frame - BG) * fade_curve((DURATION - t) / FADE_OUT)
        return frame.astype(np.uint8)

    return draw


def render(plan, notes, fur, out_path, audio_path, thumb_path=None, thumb_t=2.5):
    """動画を書き出す。thumb_path を渡すと、thumb_t 秒時点の1コマ(フェードなし)も保存する。"""
    draw = make_drawer(plan, notes, fur)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(audio_path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(int(DURATION * FPS)):
        proc.stdin.write(draw(fi / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    if thumb_path:
        Image.fromarray(draw(thumb_t, fade=False)).save(thumb_path, quality=92)

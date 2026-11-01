"""lo-fi「ねこふんじゃった」長尺サンプル(横長 1920x1080)。

ねこが弾くのはメロディ(足の下の鍵盤だけが鳴る)。伴奏(エレピ・ベース・ドラム)と
レコードのノイズ・雨音は、ねこの部屋で流れているバンドの音として重ねる。
使い方: python3 tools/lofi_sample.py OUT_DIR   (試作。投稿の仕組みにはまだ組み込んでいない)
"""
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import piano  # noqa: E402
import songs  # noqa: E402
from common import BG, FPS, SR, write_wav  # noqa: E402
from text import SERIF_L, draw_text  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
rng = random.Random(7)
nrng = np.random.default_rng(7)

# ---------------------------------------------------------------- 曲の構成
BPM = 74
BEAT = 60 / BPM
BAR = 4 * BEAT
SWING = 0.6  # 裏の8分を少し遅らせる

SECTIONS = [("intro", 4), ("A", 8), ("A2", 8), ("B", 8), ("A", 8), ("A2end", 8), ("outro", 4)]
N_BARS = sum(n for _, n in SECTIONS)
TOTAL = N_BARS * BAR + 2.0
CHORDS = [  # 4小節で一回り: (名前, エレピの和音, ベースの根音)
    ("F#maj9", [54, 58, 61, 65, 68], 42),
    ("D#m9", [51, 54, 58, 61, 65], 39),
    ("G#m9", [56, 59, 63, 66, 70], 44),
    ("C#13", [56, 59, 65, 70], 37),
]
M = songs.midi
CAT_BAR = {  # 和音ごとの、ねこの「ふん」(低い音)と「じゃっ・た」(2つの足で和音)
    "F#maj9": (M("F#4"), [M("A#4"), M("C#5")]),
    "D#m9": (M("F#4"), [M("A#4"), M("C#5")]),
    "G#m9": (M("G#4"), [M("B4"), M("C#5")]),
    "C#13": (M("G#4"), [M("B4"), M("C#5")]),
}
B_LINE = [  # 間奏で、ねこがゆっくり歩きながら弾く旋律(2拍ごと)
    ["A#4", "C#5"], ["D#5", "C#5"], ["B4", "A#4"], ["G#4", None],
    ["C#5", "D#5"], ["F#5", "D#5"], ["D#5", "C#5"], ["A#4", "G#4"],
]

bars = []  # (小節の開始時刻, セクション名, セクション内の小節番号)
t = 0.0
for name, n in SECTIONS:
    for i in range(n):
        bars.append((t, name, i))
        t += BAR


def hum(x=0.012):
    return rng.uniform(-x, x)


cat_events = []
for bi, (t0, sec, i) in enumerate(bars):
    chord = CHORDS[bi % 4][0]
    low, stab = CAT_BAR[chord]
    nxt = bars[bi + 1][1] if bi + 1 < len(bars) else None
    play_motif = sec in ("A", "A2", "A2end")
    if sec == "A2" and i == 7:
        # 間奏の前: 黒鍵を駆け上がる
        for k, n in enumerate(["F#4", "G#4", "A#4", "C#5", "D#5", "F#5", "G#5", "A#5"]):
            cat_events.append((t0 + (k // 2) * BEAT + (k % 2) * SWING * BEAT, [M(n)], 0.55 + 0.05 * k))
        continue
    if play_motif:
        cat_events.append((t0 + hum(), [low], 0.95))
        cat_events.append((t0 + BEAT + hum(), stab, 0.6))
        cat_events.append((t0 + 2 * BEAT + hum(), stab, 0.55))
    if sec == "B":
        for k, n in enumerate(B_LINE[i]):
            if n:
                cat_events.append((t0 + 2 * k * BEAT + hum(), [M(n)], 0.7))
    # 次の小節の「ふん」へつながる「ねこ」(D#5 C#5)
    if (play_motif and not (sec == "A2end" and i == 7) and not (sec == "A2" and i == 6)) or \
            (sec == "intro" and i == 3) or (sec == "B" and i == 7):
        cat_events.append((t0 + 3 * BEAT + hum(), [M("D#5")], 0.75))
        cat_events.append((t0 + (3 + SWING) * BEAT + hum(), [M("C#5")], 0.7))
    if sec == "A2end" and i == 7:
        # おしまい: 最後の「ふん・じゃーん」
        end = bars[bi][0] + BAR
        cat_events.append((end, [M("F#4")], 0.9))
        cat_events.append((end + BEAT, [M("A#4"), M("C#5")], 0.6))

cat_events.sort(key=lambda e: e[0])
cat_events = [(round(t, 4), ms, v) for t, ms, v in cat_events]

# ---------------------------------------------------------------- 音
N = int(TOTAL * SR)


def buf():
    return np.zeros(N)


def add(dst, start_t, sig):
    p0 = int(start_t * SR)
    if p0 >= N:
        return
    seg = min(len(sig), N - p0)
    dst[p0:p0 + seg] += sig[:seg]


def fft_filter(x, lo=None, hi=None, order=2):
    """なめらかな低域・高域カット(FFTで一度に)。"""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    H = np.ones_like(f)
    if hi:
        H /= np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        H *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(X * H, len(x))


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ねこのピアノ(Shortsと同じ音色を、少しこもらせる)
cat = buf()
for t0, ms, v in cat_events:
    for j, m in enumerate(ms):
        k = np.arange(int(3.0 * SR)) / SR
        add(cat, t0 + j * 0.006, v * 0.3 * piano.piano_tone(hz(m), k))
cat = fft_filter(cat, hi=3200)

# エレピ(FMの簡単なローズ風)
ep = buf()


def ep_note(f, dur, v):
    k = np.arange(int((dur + 0.4) * SR)) / SR
    idx = 1.1 * np.exp(-k / 0.35) + 0.15
    w = np.sin(2 * np.pi * f * k + idx * np.sin(2 * np.pi * f * k))
    w += 0.06 * np.sin(2 * np.pi * 4 * f * k) * np.exp(-k / 0.12)  # 打鍵のきらっとした音
    env = np.minimum(k / 0.006, 1) * np.exp(-k / 2.2)
    env *= np.clip((dur + 0.4 - k) / 0.4, 0, 1)  # 離鍵
    return v * w * env


for bi, (t0, sec, i) in enumerate(bars + [(bars[-1][0] + BAR, "end", 0)]):
    _, notes, _ = CHORDS[bi % 4] if sec != "end" else CHORDS[0]
    hits = [(0, 0.5, 2.5 * BEAT)] if sec in ("intro", "outro", "end") else \
        [(0, 0.45, 2.5 * BEAT), ((2 + SWING) * BEAT, 0.25, 1.3 * BEAT)]
    if sec == "end":
        hits = [(0, 0.5, 6.0)]
    for off, v, dur in hits:
        for j, m in enumerate(notes):
            add(ep, t0 + off + j * 0.012 + hum(0.006), ep_note(hz(m), dur, v))
# ゆっくり揺れるトレモロ(左右)
tt = np.arange(N) / SR
trem = 0.5 + 0.5 * np.sin(2 * np.pi * 0.35 * tt)
ep_l, ep_r = ep * (0.75 + 0.25 * trem), ep * (1.0 - 0.25 * trem)

# ベース
bass = buf()


def bass_note(f, dur, v):
    k = np.arange(int((dur + 0.1) * SR)) / SR
    w = np.sin(2 * np.pi * f * k) + 0.2 * np.sin(4 * np.pi * f * k)
    env = np.minimum(k / 0.01, 1) * np.exp(-k / 1.4) * np.clip((dur + 0.1 - k) / 0.1, 0, 1)
    return v * w * env


for bi, (t0, sec, i) in enumerate(bars):
    if sec in ("intro", "outro"):
        continue
    root = CHORDS[bi % 4][2]
    add(bass, t0, bass_note(hz(root), 1.8 * BEAT, 0.9))
    add(bass, t0 + (2 + SWING) * BEAT, bass_note(hz(root + 7), 0.8 * BEAT, 0.6))
    add(bass, t0 + (3 + SWING) * BEAT, bass_note(hz(root + (12 if i % 2 else 10)), 0.35 * BEAT, 0.5))

# ドラム
drums = buf()
kick_env = buf()
k = np.arange(int(0.5 * SR)) / SR
KICK = np.sin(2 * np.pi * np.cumsum(48 + 70 * np.exp(-k / 0.035)) / SR) * np.exp(-k / 0.25)
noise = nrng.standard_normal(int(0.4 * SR))
SNARE = fft_filter(noise, lo=900, hi=4500)[:len(noise)]
ks = np.arange(len(noise)) / SR
SNARE = SNARE / np.abs(SNARE).max() * np.exp(-ks / 0.11) + 0.5 * np.sin(2 * np.pi * 185 * ks) * np.exp(-ks / 0.05)
HAT = fft_filter(nrng.standard_normal(int(0.12 * SR)), lo=6000)
HAT = HAT / np.abs(HAT).max() * np.exp(-np.arange(len(HAT)) / SR / 0.022)
for bi, (t0, sec, i) in enumerate(bars):
    if sec in ("intro", "outro"):
        continue
    soft = sec == "B"
    if not soft:
        for b in ([0, 1 + SWING] + ([3 + SWING] if i % 2 else [])):
            add(drums, t0 + b * BEAT, 0.9 * KICK)
            add(kick_env, t0 + b * BEAT, np.exp(-k / 0.18))
    for b in (1, 3):
        add(drums, t0 + b * BEAT + 0.018, (0.25 if soft else 0.5) * SNARE)
    for e in range(8):
        b = e // 2 + (SWING if e % 2 else 0)
        add(drums, t0 + b * BEAT + hum(0.006), (0.12 if e % 2 else 0.2) * (0.7 if soft else 1) * HAT)
drums = fft_filter(drums, hi=7000)

# レコードのノイズと雨音
crackle = buf()
for _ in range(int(TOTAL * 9)):
    p = rng.randrange(N - 200)
    crackle[p] += rng.uniform(-1, 1) * rng.random() ** 3
crackle = fft_filter(crackle, lo=1200, hi=6000) * 0.5
hiss = fft_filter(nrng.standard_normal(N), lo=2000, hi=8000) * 0.004
rain = fft_filter(nrng.standard_normal(N), lo=400, hi=2500) * 0.02

# ミックス(キックに合わせて伴奏を少し沈める)
duck = 1 - 0.3 * np.clip(kick_env, 0, 1)
L = 0.95 * cat * 1.0 + 0.55 * ep_l * duck + 0.55 * bass * duck + 0.6 * drums + crackle + hiss + rain
R = 0.95 * cat * 0.92 + 0.55 * ep_r * duck + 0.55 * bass * duck + 0.6 * drums + crackle + hiss * 1.1 + rain * 0.9
# テープの揺れ(ワウ・フラッター)
warp = tt + 0.0018 * np.sin(2 * np.pi * 0.45 * tt) + 0.00015 * np.sin(2 * np.pi * 5.5 * tt)
L, R = np.interp(warp, tt, L), np.interp(warp, tt, R)
L, R = fft_filter(L, lo=30, hi=9000), fft_filter(R, lo=30, hi=9000)
out = np.stack([L, R], axis=1)
fade_in, fade_out = int(1.5 * SR), int(6 * SR)
out[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
out[-fade_out:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fade_out)))[:, None]
out /= np.abs(out).max()
out = np.tanh(out * 1.3) / np.tanh(1.3) * 0.89
write_wav(OUT / "lofi.wav", (out * 32767).astype(np.int16))
print("audio done", round(TOTAL, 1), "s,", len(cat_events), "cat events", flush=True)

# ---------------------------------------------------------------- 映像
plan, notes = songs.plan_song(cat_events, duration=TOTAL)
bad = songs.check_paws(plan, notes)
assert not bad, bad
draw_scene = piano.make_drawer(plan, notes, "orange")

W2, H2 = 1920, 1080
CROP = (0, 470, 1080, 1425)  # 縦長の画面から、ねこと鍵盤のところだけ
SX, SY = 420, 50
WOOD_Y = SY + (CROP[3] - CROP[1])
BGc = tuple(int(c) for c in BG)

base = Image.new("RGB", (W2, H2), BGc)
d = ImageDraw.Draw(base)
# 机
d.rectangle([0, WOOD_Y, W2, H2], fill=(58, 40, 30))
d.rectangle([0, WOOD_Y, W2, WOOD_Y + 6], fill=(84, 60, 44))
# 窓(左)
WX0, WY0, WX1, WY1 = 80, 140, 350, 560
d.rectangle([WX0 - 14, WY0 - 14, WX1 + 14, WY1 + 14], fill=(40, 32, 30))
for y in range(WY0, WY1):
    a = (y - WY0) / (WY1 - WY0)
    d.line([WX0, y, WX1, y], fill=(int(18 + 22 * a), int(22 + 14 * a), int(48 + 20 * a)))
d.ellipse([250, 190, 306, 246], fill=(236, 226, 190))  # 月
d.ellipse([238, 182, 290, 234], fill=(22, 25, 52))      # 三日月にする影
d.rectangle([WX0 + (WX1 - WX0) // 2 - 5, WY0, WX0 + (WX1 - WX0) // 2 + 5, WY1], fill=(40, 32, 30))
d.rectangle([WX0, WY0 + (WY1 - WY0) // 2 - 5, WX1, WY0 + (WY1 - WY0) // 2 + 5], fill=(40, 32, 30))
d.rectangle([WX0 - 30, WY1 + 14, WX1 + 30, WY1 + 30], fill=(64, 48, 40))  # 窓の下の台
# 観葉植物(窓の下)
d.rectangle([150, WY1 - 50, 200, WY1 + 14], fill=(150, 88, 60))
for ang in range(-60, 61, 30):
    a = math.radians(ang - 90)
    d.line([175, WY1 - 50, 175 + 70 * math.cos(a), WY1 - 50 + 80 * math.sin(a)], fill=(70, 120, 80), width=10)
# 机の上のランプ(右)
LX = 1690
glow = Image.new("L", (W2, H2), 0)
ImageDraw.Draw(glow).ellipse([LX - 330, 300, LX + 330, 960], fill=60)
glow = glow.filter(ImageFilter.GaussianBlur(120))
warm = Image.new("RGB", (W2, H2), (255, 190, 110))
base = Image.composite(warm, base, glow)
d = ImageDraw.Draw(base)
d.rectangle([LX - 70, WOOD_Y - 14, LX + 70, WOOD_Y], fill=(40, 34, 32))      # 台
d.rectangle([LX - 6, 620, LX + 6, WOOD_Y - 14], fill=(40, 34, 32))           # 柱
d.polygon([(LX - 110, 640), (LX + 110, 640), (LX + 60, 540), (LX - 60, 540)], fill=(196, 120, 70))  # かさ
d.rectangle([LX - 40, 640, LX + 40, 652], fill=(255, 226, 160))              # 電球の光
# マグカップ
MX = 1560
d.rectangle([MX - 34, WOOD_Y - 70, MX + 34, WOOD_Y], fill=(214, 206, 196))
d.rectangle([MX + 34, WOOD_Y - 56, MX + 52, WOOD_Y - 20], outline=(214, 206, 196), width=8)
# 曲名
draw_text(d, (1700, 170), "ねこふんじゃった", SERIF_L, 44, (236, 226, 206), tracking=3)
draw_text(d, (1700, 225), "lo-fi", SERIF_L, 30, (196, 176, 150), tracking=6)

# 周辺減光と粒子
yy, xx = np.mgrid[0:H2, 0:W2]
vign = 1 - 0.35 * (((xx - W2 / 2) / (W2 / 2)) ** 2 + ((yy - H2 / 2) / (H2 / 2)) ** 2) / 2
vign = vign[..., None].astype(np.float32)
GRAINS = [nrng.normal(0, 4, (H2, W2, 1)).astype(np.float32) for _ in range(6)]
DROPS = [(rng.uniform(WX0, WX1), rng.uniform(0, 1), rng.uniform(380, 520)) for _ in range(60)]


def frame(t):
    img = base.copy()
    sc = draw_scene(t, fade=False)[CROP[1]:CROP[3], CROP[0]:CROP[2]]
    mask = Image.fromarray(((np.abs(sc.astype(np.int16) - BG.astype(np.int16)).sum(axis=2) > 6) * 255).astype(np.uint8))
    img.paste(Image.fromarray(sc), (SX, SY), mask)
    d = ImageDraw.Draw(img)
    for x, ph, sp in DROPS:  # 窓の雨
        y = WY0 + ((ph * (WY1 - WY0) + sp * t) % (WY1 - WY0))
        d.line([x, y, x - 3, min(y + 16, WY1)], fill=(110, 130, 170))
    for j in range(3):  # 湯気
        for s in range(10):
            yy_ = WOOD_Y - 80 - s * 9 - ((t * 20 + j * 30) % 30)
            xx_ = MX - 14 + j * 14 + 6 * math.sin(t * 1.5 + s * 0.6 + j)
            c = int(120 - s * 9)
            d.rectangle([xx_, yy_, xx_ + 4, yy_ + 4], fill=(c, c, c + 8))
    a = np.asarray(img, dtype=np.float32) * vign + GRAINS[int(t * 12) % len(GRAINS)]
    if t < 1.5:
        a *= t / 1.5
    if t > TOTAL - 6:
        a *= max(0.0, (TOTAL - t) / 6)
    return np.clip(a, 0, 255).astype(np.uint8)


Image.fromarray(frame(45.0)).save(OUT / "still.jpg", quality=90)
if len(sys.argv) > 2:
    for tt_ in (5.0, 20.0, 80.0):
        Image.fromarray(frame(tt_)).save(OUT / f"still_{int(tt_)}.jpg", quality=85)
    sys.exit()
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W2}x{H2}",
       "-r", str(FPS), "-i", "-", "-i", str(OUT / "lofi.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
       "-crf", "22", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT / "lofi_nekofunjatta.mp4")]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
nf = int(TOTAL * FPS)
for fi in range(nf):
    proc.stdin.write(frame(fi / FPS).tobytes())
    if fi % 600 == 0:
        print(f"frame {fi}/{nf}", flush=True)
proc.stdin.close()
proc.wait()
print("done", proc.returncode)

"""知っている曲を、ねこが弾く lo-fi の横長動画(1920x1080、2分前後)にする。

Shortsで使っている冒頭のフレーズ(songs.MELODIES)をもとに、
前奏 → メイン → 3度を重ねたメイン → 間奏(ゆっくり崩す) → メイン → 後奏 の形に組む。
和音はメロディから自動で選び、lo-fi らしい7th・9thの和音にする。
ねこが弾く(足の下の鍵盤が鳴る)のはメロディだけ。エレピ・ベース・ドラム・レコードのノイズ・雨音は、
ねこの部屋で流れているバンドの音として重ねる。

使い方: python3 lofi.py twinkle --out out_lofi [--seed 1] [--fur orange]
"""
import argparse
import math
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import piano
import songs
from cat_sprites import FURS
from common import BG, FPS, SR, write_wav
from text import SERIF_L, draw_text

# 曲ごとの設定。tonic: 主音(0=ド)、minor: 短調、meter: 1小節の拍数、
# unit: 楽譜の1拍が lo-fi の何拍か、pickup: 弱起(楽譜の拍数)、bpm: lo-fi のテンポ
LOFI = {
    "twinkle": dict(tonic=7, minor=False, meter=4, unit=1, pickup=0, bpm=74),
    "brahms": dict(tonic=0, minor=False, meter=3, unit=1, pickup=1, bpm=66,
                   chords=[(0, "maj7"), (0, "maj7"), (2, "m7"), (7, "7")]),
    "elise": dict(tonic=9, minor=True, meter=3, unit=0.5, pickup=2, bpm=72,
                  chords=[(7, "7"), (0, "m7"), (7, "7"), (0, "m7")]),
}
# chords: 自動で選んだ和音がしっくりこない曲だけ、区間ごとの和音(度数, 種類)を手で書く
SWING = 0.6  # 裏の8分を少し遅らせる
SCALE = {False: [0, 2, 4, 5, 7, 9, 11], True: [0, 2, 3, 5, 7, 8, 11]}
QUALITY = {"maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "7": [0, 4, 7, 10]}
DIATONIC = {  # (根音の度数(半音), 種類, 好みの重み)
    False: [(0, "maj7", 0.25), (2, "m7", 0.0), (4, "m7", 0.0), (5, "maj7", 0.2), (7, "7", 0.15), (9, "m7", 0.08)],
    True: [(0, "m7", 0.25), (5, "m7", 0.12), (7, "7", 0.15), (8, "maj7", 0.08), (3, "maj7", 0.0), (10, "7", 0.0)],
}


# ---------------------------------------------------------------- 曲の組み立て
def parse_phrase(song_id, cfg):
    """楽譜 → [(lo-fi の拍位置, 長さ, MIDI)]。小節の頭を0にする(弱起はマイナス)。"""
    _, _, score, *shift = songs.MELODIES[song_id]
    shift = shift[0] if shift else 0
    notes, pos = [], 0.0
    for tok in score.split():
        name, length = tok.split(":")
        length = float(length)
        if name != "-":
            notes.append(((pos - cfg["pickup"]) * cfg["unit"], length * cfg["unit"], songs.midi(name) + shift))
        pos += length
    bars = math.ceil((pos - cfg["pickup"]) * cfg["unit"] / cfg["meter"] - 1e-9)
    return notes, bars


def swing(b):
    frac = b - math.floor(b)
    return b + (SWING - 0.5) if abs(frac - 0.5) < 1e-6 else b


def harmonize(notes, bars, cfg):
    """区間ごとに、メロディの音を一番多く含む和音を選ぶ。4拍子は2拍ごと、3拍子は1小節ごと。"""
    seg_len = 2 if cfg["meter"] == 4 else cfg["meter"]
    n_seg = bars * cfg["meter"] // seg_len
    if "chords" in cfg:
        return [(d, q, s * seg_len, (s + 1) * seg_len) for s, (d, q) in enumerate(cfg["chords"])]
    last_note_seg = int(max(p for p, _, _ in notes) // seg_len)
    chords = []
    for s in range(n_seg):
        s0, s1 = s * seg_len, (s + 1) * seg_len
        best = None
        for deg, q, prior in DIATONIC[cfg["minor"]]:
            pcs = {(cfg["tonic"] + deg + iv) % 12 for iv in QUALITY[q]}
            score, sounding = prior, 0
            if deg == 0 and s in (0, last_note_seg):
                score += 0.6
            if deg == 7 and s == last_note_seg - 1:
                score += 0.3
            for p, ln, m in notes:
                ov = min(p + ln, s1) - max(p, s0)
                if ov <= 0:
                    continue
                sounding += 1
                w = ov * (1.5 if abs(p - s0) < 1e-6 else 1.0)
                score += w if m % 12 in pcs else -0.4 * w
            if best is None or score > best[0]:
                best = (score, deg, q, sounding)
        if best[3] == 0 and chords:
            chords.append(chords[-1][:2] + (s0, s1))
        else:
            chords.append((best[1], best[2], s0, s1))
    return chords  # [(度数, 種類, 開始拍, 終了拍)]


def third_below(m, cfg):
    scale = sorted({(cfg["tonic"] + d) % 12 for d in SCALE[cfg["minor"]]})
    steps, x = 0, m
    while steps < 2:
        x -= 1
        if x % 12 in scale:
            steps += 1
    return x


def arrange(song_id, seed):
    cfg = LOFI[song_id]
    rng = random.Random(seed)
    phrase, P = parse_phrase(song_id, cfg)
    chords = harmonize(phrase, P, cfg)
    meter = cfg["meter"]
    reps = 2 if P >= 4 else 4 if P <= 2 else 3
    plan = [("intro", 4)] + [(name, P * reps) for name in ("A", "A3rd", "B", "A")] + [("outro", 4)]
    beat = 60 / cfg["bpm"]

    def hum(x=0.012):
        return rng.uniform(-x, x)

    events, sections, bar0 = [], [], 0
    for name, n in plan:
        sections.append((name, bar0, n))
        if name in ("A", "A3rd", "B"):
            for r in range(n // P):
                base = (bar0 + r * P) * meter
                if name == "B":  # 間奏: 強拍で鳴っている音だけを、ゆっくり
                    grid = [0, 2] if meter == 4 else [0]
                    for b in range(P):
                        for g in grid:
                            at = b * meter + g
                            for p, ln, m in phrase:
                                if p <= at + 1e-6 < p + ln:
                                    events.append(((base + at) * beat + hum(), [m], 0.62))
                                    break
                    continue
                for p, ln, m in phrase:
                    ms = [m]
                    if name == "A3rd" and ln >= 1 and third_below(m, cfg) >= 60:
                        ms = [third_below(m, cfg), m]
                    events.append(((base + swing(p)) * beat + hum(), ms, 0.8 if len(ms) == 1 else 0.6))
        bar0 += n
    total_bars = bar0
    events = sorted([(round(t, 4), ms, v) for t, ms, v in events if t >= 0], key=lambda e: e[0])
    # 足が届かない3度は、上の音だけにする
    fixed, facing = [], 1
    for t, ms, v in events:
        if len(ms) == 2:
            try:
                songs.fit_pose(ms, facing, songs.center(ms[1]))
            except ValueError:
                ms, v = [ms[1]], 0.8
        fixed.append((t, ms, v))
    return dict(cfg=cfg, beat=beat, chords=chords, P=P, sections=sections, total_bars=total_bars,
                events=fixed, total=total_bars * meter * beat + 2.5)


# ---------------------------------------------------------------- 音
def fft_filter(x, lo=None, hi=None, order=2):
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


def ep_note(f, dur, v):
    k = np.arange(int((dur + 0.4) * SR)) / SR
    idx = 1.1 * np.exp(-k / 0.35) + 0.15
    w = np.sin(2 * np.pi * f * k + idx * np.sin(2 * np.pi * f * k))
    w += 0.06 * np.sin(2 * np.pi * 4 * f * k) * np.exp(-k / 0.12)
    env = np.minimum(k / 0.006, 1) * np.exp(-k / 2.2) * np.clip((dur + 0.4 - k) / 0.4, 0, 1)
    return v * w * env


def bass_note(f, dur, v):
    k = np.arange(int((dur + 0.1) * SR)) / SR
    w = np.sin(2 * np.pi * f * k) + 0.2 * np.sin(4 * np.pi * f * k)
    env = np.minimum(k / 0.01, 1) * np.exp(-k / 1.4) * np.clip((dur + 0.1 - k) / 0.1, 0, 1)
    return v * w * env


def voicing(cfg, deg, q):
    """エレピの和音(根音・3度・5度・7度・9度)と、ベースの根音。"""
    pc = (cfg["tonic"] + deg) % 12
    r = 45 + (pc - 45) % 12
    ivs = QUALITY[q] + [14]
    return [r + iv for iv in ivs], 36 + (pc - 36) % 12


def synth_lofi(arr, seed):
    cfg, beat, meter = arr["cfg"], arr["beat"], arr["cfg"]["meter"]
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    N = int(arr["total"] * SR)
    tt = np.arange(N) / SR

    def add(dst, t0, sig):
        p0 = int(t0 * SR)
        if 0 <= p0 < N:
            seg = min(len(sig), N - p0)
            dst[p0:p0 + seg] += sig[:seg]

    def hum(x=0.008):
        return rng.uniform(-x, x)

    # ねこのピアノ
    cat = np.zeros(N)
    k3 = np.arange(int(3.0 * SR)) / SR
    for t0, ms, v in arr["events"]:
        for j, m in enumerate(ms):
            add(cat, t0 + j * 0.006, v * 0.3 * piano.piano_tone(hz(m), k3))
    cat = fft_filter(cat, hi=3200)

    ep, bass, drums, kick_env = np.zeros(N), np.zeros(N), np.zeros(N), np.zeros(N)
    k = np.arange(int(0.5 * SR)) / SR
    KICK = np.sin(2 * np.pi * np.cumsum(48 + 70 * np.exp(-k / 0.035)) / SR) * np.exp(-k / 0.25)
    noise = nrng.standard_normal(int(0.4 * SR))
    ks = np.arange(len(noise)) / SR
    SNARE = fft_filter(noise, lo=900, hi=4500)
    SNARE = SNARE / np.abs(SNARE).max() * np.exp(-ks / 0.11) + 0.5 * np.sin(2 * np.pi * 185 * ks) * np.exp(-ks / 0.05)
    HAT = fft_filter(nrng.standard_normal(int(0.12 * SR)), lo=6000)
    HAT = HAT / np.abs(HAT).max() * np.exp(-np.arange(len(HAT)) / SR / 0.022)

    P = arr["P"]
    for name, bar0, n in arr["sections"]:
        for b in range(n):
            gb = bar0 + b                      # 曲全体での小節番号
            t_bar = gb * meter * beat
            for deg, q, s0, s1 in arr["chords"]:
                if not (b % P) * meter <= s0 < (b % P + 1) * meter:
                    continue
                notes, root = voicing(cfg, deg, q)
                st = t_bar + (s0 - (b % P) * meter) * beat
                ln = (s1 - s0) * beat
                for j, m in enumerate(notes):
                    add(ep, st + j * 0.012 + hum(), ep_note(hz(m), ln * 0.9, 0.42))
                if name not in ("intro", "outro"):
                    add(bass, st, bass_note(hz(root), min(ln, 1.8 * beat), 0.9))
                    if ln >= 2 * beat:
                        add(bass, st + (1 + SWING) * beat, bass_note(hz(root + 7), 0.8 * beat, 0.55))
            if name in ("intro", "outro"):
                continue
            soft = name == "B"
            kicks = [0, 1 + SWING] if meter == 4 else [0]
            if b % 2:
                kicks.append(meter - 1 + SWING)
            snares = [1, 3] if meter == 4 else [2]
            if not soft:
                for kb in kicks:
                    add(drums, t_bar + kb * beat, 0.9 * KICK)
                    add(kick_env, t_bar + kb * beat, np.exp(-k / 0.18))
            for sb in snares:
                add(drums, t_bar + sb * beat + 0.018, (0.25 if soft else 0.5) * SNARE)
            for e in range(2 * meter):
                hb = e // 2 + (SWING if e % 2 else 0)
                add(drums, t_bar + hb * beat + hum(0.006), (0.12 if e % 2 else 0.2) * (0.7 if soft else 1) * HAT)
    # 最後に主和音をのばす
    end_t = arr["total_bars"] * meter * beat
    notes, _ = voicing(cfg, 0, "m7" if cfg["minor"] else "maj7")
    for j, m in enumerate(notes):
        add(ep, end_t + j * 0.015, ep_note(hz(m), 2.0, 0.4))
    drums = fft_filter(drums, hi=7000)
    trem = 0.5 + 0.5 * np.sin(2 * np.pi * 0.35 * tt)
    crackle = np.zeros(N)
    for _ in range(int(arr["total"] * 9)):
        crackle[rng.randrange(N - 200)] += rng.uniform(-1, 1) * rng.random() ** 3
    crackle = fft_filter(crackle, lo=1200, hi=6000) * 0.5
    hiss = fft_filter(nrng.standard_normal(N), lo=2000, hi=8000) * 0.004
    rain = fft_filter(nrng.standard_normal(N), lo=400, hi=2500) * 0.02
    duck = 1 - 0.3 * np.clip(kick_env, 0, 1)
    L = 0.95 * cat + 0.55 * ep * (0.75 + 0.25 * trem) * duck + 0.55 * bass * duck + 0.6 * drums + crackle + hiss + rain
    R = 0.87 * cat + 0.55 * ep * (1.0 - 0.25 * trem) * duck + 0.55 * bass * duck + 0.6 * drums + crackle + 1.1 * hiss + 0.9 * rain
    warp = tt + 0.0018 * np.sin(2 * np.pi * 0.45 * tt) + 0.00015 * np.sin(2 * np.pi * 5.5 * tt)
    L, R = np.interp(warp, tt, L), np.interp(warp, tt, R)
    out = np.stack([fft_filter(L, lo=30, hi=9000), fft_filter(R, lo=30, hi=9000)], axis=1)
    fi, fo = int(1.5 * SR), int(6 * SR)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    out[-fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo)))[:, None]
    out /= np.abs(out).max()
    out = np.tanh(out * 1.3) / np.tanh(1.3) * 0.89
    return (out * 32767).astype(np.int16)


# ---------------------------------------------------------------- 映像
W2, H2 = 1920, 1080
CROP = (0, 470, 1080, 1425)  # 縦長の画面から、ねこと鍵盤のところだけ
SX, SY = 420, 50
WOOD_Y = SY + (CROP[3] - CROP[1])
WIN = (80, 140, 350, 560)
LX, MX = 1690, 1560


def build_room(title):
    BGc = tuple(int(c) for c in BG)
    base = Image.new("RGB", (W2, H2), BGc)
    d = ImageDraw.Draw(base)
    d.rectangle([0, WOOD_Y, W2, H2], fill=(58, 40, 30))
    d.rectangle([0, WOOD_Y, W2, WOOD_Y + 6], fill=(84, 60, 44))
    x0, y0, x1, y1 = WIN
    d.rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 14], fill=(40, 32, 30))
    for y in range(y0, y1):
        a = (y - y0) / (y1 - y0)
        d.line([x0, y, x1, y], fill=(int(18 + 22 * a), int(22 + 14 * a), int(48 + 20 * a)))
    d.ellipse([250, 190, 306, 246], fill=(236, 226, 190))
    d.ellipse([238, 182, 290, 234], fill=(22, 25, 52))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    d.rectangle([cx - 5, y0, cx + 5, y1], fill=(40, 32, 30))
    d.rectangle([x0, cy - 5, x1, cy + 5], fill=(40, 32, 30))
    d.rectangle([x0 - 30, y1 + 14, x1 + 30, y1 + 30], fill=(64, 48, 40))
    d.rectangle([150, y1 - 50, 200, y1 + 14], fill=(150, 88, 60))
    for ang in range(-60, 61, 30):
        a = math.radians(ang - 90)
        d.line([175, y1 - 50, 175 + 70 * math.cos(a), y1 - 50 + 80 * math.sin(a)], fill=(70, 120, 80), width=10)
    glow = Image.new("L", (W2, H2), 0)
    ImageDraw.Draw(glow).ellipse([LX - 330, 300, LX + 330, 960], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    base = Image.composite(Image.new("RGB", (W2, H2), (255, 190, 110)), base, glow)
    d = ImageDraw.Draw(base)
    d.rectangle([LX - 70, WOOD_Y - 14, LX + 70, WOOD_Y], fill=(40, 34, 32))
    d.rectangle([LX - 6, 620, LX + 6, WOOD_Y - 14], fill=(40, 34, 32))
    d.polygon([(LX - 110, 640), (LX + 110, 640), (LX + 60, 540), (LX - 60, 540)], fill=(196, 120, 70))
    d.rectangle([LX - 40, 640, LX + 40, 652], fill=(255, 226, 160))
    d.rectangle([MX - 34, WOOD_Y - 70, MX + 34, WOOD_Y], fill=(214, 206, 196))
    d.rectangle([MX + 34, WOOD_Y - 56, MX + 52, WOOD_Y - 20], outline=(214, 206, 196), width=8)
    size = 44 if len(title) <= 8 else max(30, int(380 / len(title)))
    draw_text(d, (1700, 170), title, SERIF_L, size, (236, 226, 206), tracking=3)
    draw_text(d, (1700, 225), "lo-fi", SERIF_L, 30, (196, 176, 150), tracking=6)
    return base


def make_frame_fn(arr, fur, title, seed):
    plan, notes = songs.plan_song(arr["events"], duration=arr["total"])
    bad = songs.check_paws(plan, notes)
    if bad:
        raise RuntimeError(f"ねこの足が鍵盤に乗っていない打鍵がある {bad[:5]}")
    draw_scene = piano.make_drawer(plan, notes, fur)
    base = build_room(title)
    rng = random.Random(seed)
    yy, xx = np.mgrid[0:H2, 0:W2]
    vign = (1 - 0.35 * (((xx - W2 / 2) / (W2 / 2)) ** 2 + ((yy - H2 / 2) / (H2 / 2)) ** 2) / 2)[..., None]
    grain = np.random.default_rng(seed).normal(0, 3, (H2, W2, 1))
    static = vign.astype(np.float32), grain.astype(np.float32)
    x0, y0, x1, y1 = WIN
    drops = [(rng.uniform(x0, x1), rng.uniform(0, 1), rng.uniform(380, 520)) for _ in range(60)]
    total = arr["total"]
    bgi = BG.astype(np.int16)

    def frame(t):
        img = base.copy()
        sc = draw_scene(t, fade=False)[CROP[1]:CROP[3], CROP[0]:CROP[2]]
        mask = ((np.abs(sc.astype(np.int16) - bgi).sum(axis=2) > 6) * 255).astype(np.uint8)
        img.paste(Image.fromarray(sc), (SX, SY), Image.fromarray(mask))
        d = ImageDraw.Draw(img)
        for x, ph, sp in drops:
            y = y0 + ((ph * (y1 - y0) + sp * t) % (y1 - y0))
            d.line([x, y, x - 3, min(y + 16, y1)], fill=(110, 130, 170))
        for j in range(3):
            for s in range(10):
                ys = WOOD_Y - 80 - s * 9 - ((t * 20 + j * 30) % 30)
                xs = MX - 14 + j * 14 + 6 * math.sin(t * 1.5 + s * 0.6 + j)
                c = int(120 - s * 9)
                d.rectangle([xs, ys, xs + 4, ys + 4], fill=(c, c, c + 8))
        a = np.asarray(img, dtype=np.float32) * static[0] + static[1]
        if t < 1.5:
            a *= t / 1.5
        if t > total - 6:
            a *= max(0.0, (total - t) / 6)
        return np.clip(a, 0, 255).astype(np.uint8)

    return frame


def render_lofi(song_id, out_dir, seed, fur=None, still_only=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    fur = fur or rng.choice(list(FURS))
    title = songs.SONGS[song_id][0].split("(")[0]  # 「(ベートーヴェン)」などは画面には出さない
    arr = arrange(song_id, seed)
    frame = make_frame_fn(arr, fur, title, seed)
    Image.fromarray(frame(min(40.0, arr["total"] / 2))).save(out / "lofi_thumb.jpg", quality=90)
    if still_only:
        return arr
    wav = out / "lofi.wav"
    write_wav(wav, synth_lofi(arr, seed))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W2}x{H2}",
           "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "23", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out / "lofi.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for fi in range(int(arr["total"] * FPS)):
        proc.stdin.write(frame(fi / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    wav.unlink()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")
    return arr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song", choices=list(LOFI))
    ap.add_argument("--out", default="out_lofi")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--fur", choices=list(FURS))
    ap.add_argument("--still", action="store_true", help="静止画だけ(確認用)")
    args = ap.parse_args()
    arr = render_lofi(args.song, args.out, args.seed, args.fur, args.still)
    names = {d: n for d, n in [(0, "I"), (2, "ii"), (3, "III"), (4, "iii"), (5, "IV"), (7, "V"), (8, "VI"), (9, "vi"), (10, "VII")]}
    print(songs.SONGS[args.song][0], f"{arr['total']:.0f}秒",
          " ".join(f"{names[d]}{q}" for d, q, _, _ in arr["chords"]))


if __name__ == "__main__":
    main()

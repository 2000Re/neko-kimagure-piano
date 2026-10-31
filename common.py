"""動画・音声の共通設定と、汎用の小さな関数。"""
import wave

import numpy as np

W, H = 1080, 1920
FPS = 30
DURATION = 7.0
FADE_OUT = 1.2       # 最後のこの秒数で音と映像をフェードアウトする
SR = 44100
BG = np.array([8, 8, 14], dtype=np.float64)


def make_reverb_ir(rng_np, seconds=2.2, decay=0.45):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    irs = []
    for _ in range(2):  # L/Rで別のノイズにすると広がりが出る
        noise = rng_np.standard_normal(n) * np.exp(-t / decay)
        noise = np.convolve(noise, np.ones(6) / 6, mode="same")  # 高域を少し丸める
        pre = int(0.018 * SR)
        noise = np.concatenate([np.zeros(pre), noise])
        irs.append(noise / np.sqrt((noise ** 2).sum()))
    return irs


def fft_convolve(a, b):
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[:len(a)]


def hsv_to_rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, tt = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    table = [(v, tt, p), (q, v, p), (p, v, tt), (p, q, v), (tt, p, v), (v, p, q)]
    return np.stack([np.choose(i, [t[c] for t in table]) for c in range(3)], axis=-1)


def fade_curve(x):
    """x: 1→0 の進行度。コサインで滑らかに減衰させる。"""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0, 1))


def write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(samples.tobytes())

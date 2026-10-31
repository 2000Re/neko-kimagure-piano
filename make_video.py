"""次に投稿する動画を1本生成する。

upload_history.json を見て連番を決め、過去と同じ曲にならない演奏を選び、
out/ に video.mp4・thumbnail.jpg(サムネイル用の静止画)・meta.json(タイトル・説明文など)を書き出す。

使い方:
  python3 make_video.py                 # 本番と同じ(履歴を見て次の1本)
  python3 make_video.py --seed 1        # シード指定の試作
"""
import argparse
import json
import random
from pathlib import Path

import piano
from cat_sprites import FURS
from common import write_wav

ROOT = Path(__file__).parent
FUR_JP = {"orange": "茶トラ", "gray": "グレー", "white": "しろ", "tuxedo": "ハチワレ"}


def youtube_title(number):
    return f"ねこが歩くと、音楽になる。🐾 #{number}"


def youtube_description(fur):
    return "\n".join([
        "ドット絵のねこが、ピアノの鍵盤の上を歩きます。",
        "足が踏んだ鍵盤の音が、そのまま流れています。",
        "歩き方も、座るタイミングも、跳ねる場所も毎回ちがうので、同じ曲は二度とできません。",
        "",
        f"今日のねこ: {FUR_JP[fur]}",
        "何の曲に聞こえたか、コメントで教えてください。",
        "",
        "#ねこ #猫 #ピアノ #ドット絵 #shorts",
    ])


TAGS = ["ねこ", "猫", "cat", "ピアノ", "piano", "ドット絵", "pixel art", "ねこピアノ", "癒し", "shorts"]


def load_history(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--history", default=str(ROOT / "upload_history.json"))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--number", type=int, help="連番を上書きする(試作用)")
    ap.add_argument("--fur", choices=list(FURS))
    args = ap.parse_args()

    history = load_history(args.history)
    number = args.number or max((h["number"] for h in history), default=0) + 1
    used = {h["key"] for h in history}

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**32)
    rng, plan, notes, signature = piano.pick_performance(seed, used_signatures=used)
    fur = args.fur or rng.choice(list(FURS))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "audio.wav"
    write_wav(wav, piano.synth(notes, seed))
    piano.render(plan, notes, fur, out / "video.mp4", wav, thumb_path=out / "thumbnail.jpg")
    wav.unlink()

    meta = {
        "number": number,
        "key": signature,  # 曲の署名(音程差の並び)。同じ曲を二度作らないための重複判定に使う
        "title": youtube_title(number),
        "description": youtube_description(fur),
        "tags": TAGS,
        "params": {"seed": seed, "fur": fur, "notes": len(notes)},
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"#{number} {meta['title']} ({FUR_JP[fur]}, {len(notes)}音)\n  -> {out / 'video.mp4'}")


if __name__ == "__main__":
    main()

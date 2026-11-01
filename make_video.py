"""次に投稿する動画を1本生成する。

upload_history.json を見て連番を決め、演奏を選び、out/ に video.mp4・thumbnail.jpg(サムネイル用の静止画)・meta.json(タイトル・説明文など)を書き出す。

2回に1回(偶数回)は、知っている曲(作者の死後70年以上たった曲。songs.py)をねこが弾く。
曲は、まだ使っていない曲(使った回数が少ない曲)から選ぶ。12月はクリスマスの曲から選ぶ。
奇数回はこれまでどおり、ねこが気まぐれに歩いて、過去と同じにならない曲を作る。

使い方:
  python3 make_video.py                 # 本番と同じ(履歴を見て次の1本)
  python3 make_video.py --seed 1        # シード指定の試作
  python3 make_video.py --song twinkle  # 知っている曲の回の試作(--song random で通常回)
"""
import argparse
import json
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import piano
import songs
from cat_sprites import FURS
from common import write_wav

ROOT = Path(__file__).parent
FUR_JP = {"orange": "茶トラ", "gray": "グレー", "white": "しろ", "tuxedo": "ハチワレ"}


def youtube_title(number):
    return f"ねこが歩くと、音楽になる。🐾 #{number}"


def youtube_description(fur, known_song=False):
    # 知っている曲の回も、曲名は書かない(何の曲かを当ててもらう)
    if known_song:
        lines = ["今日のねこは、どこかで聞いたことのあるメロディを弾いているようです。",
                 "",
                 f"今日のねこ: {FUR_JP[fur]}",
                 "何の曲か分かったら、コメントで教えてください。"]
    else:
        lines = ["歩き方も、座るタイミングも、跳ねる場所も毎回ちがうので、同じ曲は二度とできません。",
                 "",
                 f"今日のねこ: {FUR_JP[fur]}",
                 "何の曲に聞こえたか、コメントで教えてください。"]
    return "\n".join([
        "ドット絵のねこが、ピアノの鍵盤の上を歩きます。",
        "足が踏んだ鍵盤の音が、そのまま流れています。",
        *lines,
        "",
        "#ねこ #猫 #ピアノ #ドット絵 #shorts",
    ])


TAGS = ["ねこ", "猫", "cat", "ピアノ", "piano", "ドット絵", "pixel art", "ねこピアノ", "癒し", "shorts"]


def load_history(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def is_song_episode(number):
    """2回に1回(偶数回)は知っている曲。"""
    return number % 2 == 0


def pick_song(history, rng, month, only=None):
    """使った回数が一番少ない曲から、ランダムに1曲選ぶ。全部使い終えたら2周目に入る。
    12月(日本時間)はクリスマスの曲だけから選び、12月以外はクリスマスの曲を除く。
    返り値は (曲ID, その曲を使うのが何回目か)。only で曲を指定できる(試作用)。"""
    used = {}
    for h in history:
        if h.get("song"):
            used[h["song"]] = used.get(h["song"], 0) + 1
    if only:
        return only, used.get(only, 0) + 1
    pool = [k for k in songs.SONGS if (k in songs.CHRISTMAS) == (month == 12)]
    least = min(used.get(k, 0) for k in pool)
    song_id = rng.choice(sorted(k for k in pool if used.get(k, 0) == least))
    return song_id, used.get(song_id, 0) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--history", default=str(ROOT / "upload_history.json"))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--number", type=int, help="連番を上書きする(試作用)")
    ap.add_argument("--fur", choices=list(FURS))
    ap.add_argument("--song", choices=["random", *songs.SONGS], help="曲を指定する(試作用)")
    ap.add_argument("--month", type=int, help="月を上書きする(試作用。12でクリスマスの曲)")
    args = ap.parse_args()

    history = load_history(args.history)
    number = args.number or max((h["number"] for h in history), default=0) + 1
    used = {h["key"] for h in history}

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**32)
    song_id = None
    if args.song not in (None, "random") or (args.song is None and is_song_episode(number)):
        rng = random.Random(seed)
        month = args.month or datetime.now(ZoneInfo("Asia/Tokyo")).month
        song_id, nth = pick_song(history, rng, month, only=args.song)
        plan, notes = songs.plan_song(songs.SONGS[song_id][1]())
        bad = songs.check_paws(plan, notes)
        if bad:
            raise RuntimeError(f"{song_id}: ねこの足が鍵盤に乗っていない打鍵がある {bad}")
        # 同じ曲を2周目以降に使っても投稿済みチェックにかからないよう、何回目かを含める
        signature = f"song:{song_id}:{nth}"
    else:
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
        "key": signature,  # 曲の署名(音程差の並び / 知っている曲は song:曲ID:何回目)。重複判定に使う
        "title": youtube_title(number),
        "description": youtube_description(fur, known_song=song_id is not None),
        "tags": TAGS,
        "params": {"seed": seed, "fur": fur, "notes": len(notes), "song": song_id},
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    what = songs.SONGS[song_id][0] if song_id else "気まぐれ"
    print(f"#{number} {meta['title']} ({FUR_JP[fur]}, {what}, {len(notes)}音)\n  -> {out / 'video.mp4'}")


if __name__ == "__main__":
    main()

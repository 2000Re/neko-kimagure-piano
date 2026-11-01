"""make_video.py の出力(out/video.mp4 + out/meta.json)をYouTubeにアップロードし、
upload_history.json に記録する。

外部ライブラリに依存しない(標準ライブラリのurllibのみ)。
必要な環境変数: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
任意: YT_CHANNEL_ID … 設定すると、アップロード先チャンネルが一致しない場合に中止する
      (別チャンネルへの誤投稿防止)

終了コード: 0 成功 / 1 その他の失敗 / 2 Secretsが未設定 / 3 リフレッシュトークンが無効(再取得が必要)
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_ENV = ["YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?uploadType=media&videoId="
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"


class TokenInvalid(Exception):
    pass


def set_output(name, value):
    """GitHub Actions のステップ出力に書く(ローカル実行時は何もしない)。"""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def request(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=300) as res:
        return res.status, dict(res.headers), res.read()


def get_access_token():
    data = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    try:
        _, _, body = request(TOKEN_URL, data=data)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if "invalid_grant" in detail or "invalid_client" in detail:
            raise TokenInvalid(detail) from e
        raise RuntimeError(f"アクセストークンの取得に失敗しました (HTTP {e.code}): {detail}") from e
    return json.loads(body)["access_token"]


def check_channel(token, expected):
    _, _, body = request(CHANNELS_URL, headers={"Authorization": f"Bearer {token}"})
    items = json.loads(body).get("items", [])
    actual = items[0]["id"] if items else None
    if actual != expected:
        name = items[0]["snippet"]["title"] if items else "(なし)"
        raise SystemExit(f"アップロード先のチャンネルが違います: {name} ({actual}) / 期待値 {expected}")
    print(f"channel ok: {items[0]['snippet']['title']}")


def upload(token, video_path, meta, privacy):
    body = json.dumps({
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": "10",  # Music
            "defaultLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }).encode()
    size = video_path.stat().st_size
    _, headers, _ = request(UPLOAD_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(size),
    })
    location = headers.get("Location") or headers.get("location")
    # 動画は1〜2MBなので一括PUT。5xx・通信断のときだけ再試行する
    for attempt in range(4):
        try:
            _, _, res = request(location, data=video_path.read_bytes(), method="PUT", headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
            })
            return json.loads(res)["id"]
        except (urllib.error.URLError, TimeoutError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                raise
            wait = 2 ** (attempt + 1)
            print(f"upload failed ({e}), retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("アップロードに4回失敗しました")


def set_thumbnail(token, video_id, image_path):
    """カスタムサムネイルを設定する。Shortsで効くかは未確定なので、失敗しても投稿は止めない。

    戻り値: 成功したら True。失敗したら理由を表示して False。
    """
    try:
        request(THUMBNAIL_URL + urllib.parse.quote(video_id), data=image_path.read_bytes(), method="POST",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"})
    except urllib.error.HTTPError as e:
        print(f"サムネイルの設定に失敗しました (HTTP {e.code}): {e.read().decode(errors='replace')}", file=sys.stderr)
        return False
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"サムネイルの設定に失敗しました: {e}", file=sys.stderr)
        return False
    print("thumbnail set")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out")
    ap.add_argument("--history", default=str(Path(__file__).parent / "upload_history.json"))
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    args = ap.parse_args()

    out = Path(args.dir)
    meta = json.loads((out / "meta.json").read_text())
    history_path = Path(args.history)
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    if any(h["key"] == meta["key"] for h in history):
        raise SystemExit(f"投稿済みのパラメータです: {meta['key']}")

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"GitHub Secrets が未設定です: {', '.join(missing)}(README の初回セットアップ手順4)", file=sys.stderr)
        sys.exit(2)

    try:
        token = get_access_token()
    except TokenInvalid as e:
        print(f"リフレッシュトークンが無効です。README の手順で再取得してください。\n{e}", file=sys.stderr)
        set_output("token_invalid", "true")
        sys.exit(3)

    if os.environ.get("YT_CHANNEL_ID"):
        check_channel(token, os.environ["YT_CHANNEL_ID"])

    video_id = upload(token, out / "video.mp4", meta, args.privacy)
    print(f"uploaded: https://youtube.com/shorts/{video_id}")
    set_output("video_id", video_id)

    thumb = out / "thumbnail.jpg"
    thumbnail_set = set_thumbnail(token, video_id, thumb) if thumb.exists() else False

    p = meta["params"]
    history.append({
        "number": meta["number"],
        "fur": p["fur"],
        "key": meta["key"],
        "seed": p["seed"],
        "song": p.get("song"),  # 知っている曲の回は曲ID(songs.py)。気まぐれの回は null
        "title": meta["title"],
        "video_id": video_id,
        "privacy": args.privacy,
        "thumbnail_set": thumbnail_set,
        "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")

    # 描き終えた状態の静止画を thumbnails/ にも残す(APIで設定できなかったときに手動で設定する用)
    if thumb.exists():
        dst = history_path.parent / "thumbnails" / f"{meta['number']:03d}.jpg"
        dst.parent.mkdir(exist_ok=True)
        shutil.copyfile(thumb, dst)


if __name__ == "__main__":
    main()

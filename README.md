# ねこピアノ — ねこが歩くと、音楽になる。

ドット絵のねこがピアノの鍵盤の上を歩き、足が踏んだ鍵盤の音がそのまま流れる7秒の縦動画を、
毎日自動でYouTubeに投稿する。

- 動画の生成は外部APIに依存しない(numpy・Pillow・ffmpegのみ。フォントは `fonts/` に同梱)
- ねこの行動(歩く・座る・跳ねる・振り返る)と歩き方(歩幅・テンポ・足の運び・ためらい)は毎回ランダム
- 同じ曲は二度と作らない(曲の署名=音程差の並びで判定。移調しただけの同じ曲も同じとみなす)
- 2回に1回(偶数回)は、だれでも知っている曲をねこが弾く(`songs.py`)。使うのは、作者の死後70年以上たった曲か
  作者不明の古い曲(民謡など)のメロディだけ。メロディの鍵盤を足が踏むように、ねこの立ち位置・歩く・跳ねるを決める。
  曲は使った回数が少ないものから選び、一巡したら2周目に入る。12月(日本時間)はクリスマスの曲だけから選び、
  12月以外はクリスマスの曲を選ばない(`songs.CHRISTMAS`)。説明文にも曲名は書かない(何の曲かを当ててもらう)

## 仕組み

| ファイル | 役割 |
|---|---|
| `piano.py` | 鍵盤・ねこの行動計画・打鍵・ピアノ音の合成・映像のレンダリング |
| `songs.py` | 知っている曲の楽譜と、その鍵盤を踏むためのねこの動きの計算 |
| `cat_sprites.py` | ドット絵のねこ(歩く2コマ・跳ねる・座る2コマ・まばたき、毛色4種) |
| `make_video.py` | 履歴を見て連番と演奏を決め、`out/` に `video.mp4`・`thumbnail.jpg`・`meta.json` を出力 |
| `youtube_upload.py` | `out/` をアップロードし、`upload_history.json` に追記(標準ライブラリのみ) |
| `posted_today.py` | 定期実行で、最後の投稿から12時間以内か(=もう投稿済みか)を判定する |
| `get_youtube_refresh_token.py` | リフレッシュトークンの取得(ローカルで一度だけ) |
| `upload_history.json` | 投稿済み記録。`key` は曲の署名(知っている曲の回は `song:曲ID:何回目`)、`song` は曲ID |
| `thumbnails/` | 投稿ごとの静止画(`001.jpg` など)。サムネイルを手動設定する用 |
| `.github/workflows/post.yml` | 生成 → artifact → 投稿 → 履歴コミット。失敗時はIssueで通知 |

画面上部は「このねこ、何の曲を弾く？」の問いかけのみ。番号は画面に出さず、
YouTubeのタイトル末尾(`ねこが歩くと、音楽になる。🐾 #12`)にだけ付ける。

## ローカルで試す

```sh
sudo apt install ffmpeg
pip install -r requirements.txt
python3 make_video.py --out out              # 本番と同じ選び方で1本
python3 make_video.py --out out --seed 1     # シード指定
python3 make_video.py --out out --song twinkle   # 知っている曲の回(曲IDは songs.py)
python3 make_video.py --out out --song random    # 気まぐれの回
```

## 初回セットアップ

### 1. YouTubeチャンネル
新しいチャンネル(ブランドアカウント)を作成する。

### 2. Google Cloud
「模様の楽譜」で作った Google Cloud プロジェクト `moyou-gakufu` の OAuth クライアントをそのまま使える
(本番環境に公開済みなので、トークンが7日で切れる制限はない)。新しく作る場合は、OAuth同意画面を
必ず「本番環境」に公開すること(公開にはホームページ・プライバシーポリシーのURLが必要)。

### 3. リフレッシュトークンの取得(ローカルPC)
```sh
pip install google-auth-oauthlib
python3 get_youtube_refresh_token.py client_secret_xxx.json
```
ブラウザのアカウント選択で**ねこピアノのチャンネルを選ぶ**こと。表示されたチャンネル名を必ず確認する。
「Googleで確認されていません」と出たら「詳細」→「移動」で進む(個人使用のアプリなので審査は不要)。

### 4. GitHub
Settings → Secrets and variables → Actions で登録する。

| 種類 | 名前 | 値 |
|---|---|---|
| Secret | `YT_CLIENT_ID` | 手順3の出力 |
| Secret | `YT_CLIENT_SECRET` | 手順3の出力 |
| Secret | `YT_REFRESH_TOKEN` | 手順3の出力 |
| Secret | `YT_CHANNEL_ID` | 手順3の出力。別チャンネルへの誤投稿を防ぐ |
| Variable | `AUTO_POST` | `true` で定期投稿を有効にする。手順5のテスト投稿が成功してから設定する |

### 5. 動作確認
Actions → post → Run workflow で、まず `dry_run` にチェックを入れて実行し、artifactの動画を確認する。
次に `privacy: private` で1本投稿してみる。問題なければ変数 `AUTO_POST` を `true` にする。

### 6. cron-job.org
| 項目 | 値 |
|---|---|
| URL | `https://api.github.com/repos/2000Re/neko-kimagure-piano/actions/workflows/post.yml/dispatches` |
| 実行スケジュール | 毎日 19:37、タイムゾーン Asia/Tokyo |
| Request method | `POST` |
| Headers | `Accept: application/vnd.github+json`<br>`Authorization: Bearer <トークン>`<br>`X-GitHub-Api-Version: 2022-11-28`<br>`Content-Type: application/json` |
| Request body | `{"ref":"main","inputs":{"scheduled":"true"}}` |

成功するとHTTP 204が返る。`X-GitHub-Api-Version: 2022-11-28` は **2028-03-10 に提供終了**なので、それまでに書き換えること。

## 運用

- 毎日 19:37 JST に cron-job.org が起動する。GitHub自身の定期実行は遅延・スキップが多いので 21:37 JST の予備としてだけ残している。
  どちらも最後の投稿から12時間以内なら何もしない。止めたいときは変数 `AUTO_POST` を `false` にする
- **`post.yml` を Claude(GitHub App経由のpush)が変更した後は、GitHubのWeb画面で `post.yml` を1文字でも編集してコミットし直すこと。**
  App経由のpushでは定期実行(schedule)が登録されない
- サムネイル: 投稿時にAPIで設定を試みるが、2026-10時点ではShortsに反映されない。`thumbnails/` の画像をPC版YouTube Studioで手動設定する
- 失敗するとIssueが立つ。トークン失効は `token-invalid` ラベル、それ以外は `post-failure` ラベル

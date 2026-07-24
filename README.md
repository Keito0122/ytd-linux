# ytd (Linux版)

yt-dlp のコマンドを短縮する CLI ツールです。長いオプションを覚えなくても、
よく使う操作を短いフラグで実行できます。

## 動作環境

- 一般的なLinuxディストリビューション(Debian/Ubuntu系、Fedora系、Arch系など)
- Python 3.9+ / pip
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) / ffmpeg(インストーラーが導入を試みます)

## インストール

```bash
unzip ytd_linux.zip -d ytd
cd ytd
bash install.sh
```

`install.sh` は以下を行います。

- `pip install --user yt-dlp pyyaml`
- ffmpeg 未導入の場合、`apt` / `dnf` / `pacman` のうち検出できたものに応じて
  インストールコマンドを案内(自動実行はしません。sudo権限が必要なため)
- `~/.local/share/ytd` へ本体を配置
- `~/.local/bin/ytd` にシンボリックリンクを作成
- `~/.config/ytd/config.yml` を雛形から作成

`~/.local/bin` がPATHに入っていない場合はインストール時に警告が出ます。
その場合はお使いのシェルの設定ファイル(`~/.bashrc` や `~/.zshrc` など)に
以下を追加してください。

```bash
export PATH="$HOME/.local/bin:$PATH"
```

追加後、シェルを再起動(または `source ~/.bashrc`)してください。

インストール後は以下で確認できます。

```bash
ytd --help
```

## 基本的な使い方

```bash
ytd "VIDEO_URL"
ytd "VIDEO_URL" --option value
```

> ⚠ **URLは必ずダブルクォートで囲んでください。**
> YouTubeのURLは `&si=...` のようなパラメータを含むことが多く、クオートを忘れると
> bash/zsh が `&` をバックグラウンド実行の区切りと解釈し、後ろのオプションが
> 独立したコマンドとして実行されてエラーになります。

### 使用例

```bash
ytd "VIDEO_URL"                            最高画質・mp4で保存
ytd "VIDEO_URL" --quality 1080p            1080pで保存
ytd "VIDEO_URL" --format mp3               MP3に変換して保存
ytd "VIDEO_URL" --cookie                    Configの既定Cookieを使用
ytd "VIDEO_URL" --output ~/Videos           保存先を指定
ytd "PLAYLIST_URL" --playlist               プレイリスト全体を取得
ytd "VIDEO_URL" --info                      ダウンロードせず情報のみ表示
```

## オプション一覧

| オプション | 説明 |
|---|---|
| `--format` | 出力形式(`mp4`, `webm`, `mkv`, `mp3`, `m4a`, `aac`, `wav`, `flac`, `opus`, `ogg`) |
| `--quality` | 画質・音質(`best`, `2160p`〜`144p` / 音声: `320k`〜`128k`) |
| `--cookie [PATH]` | Cookie使用。パス省略時はConfigの既定Cookieを使用 |
| `--output PATH` | 保存先フォルダー |
| `--playlist` | プレイリスト全体を取得(未指定時は先頭1件のみ) |
| `--audio` | 音声のみ取得 |
| `--video-only` | 映像のみ取得(音声なし) |
| `--subtitle` | 字幕を保存 |
| `--embed-subtitle` | 字幕を動画に埋め込み |
| `--thumbnail` | サムネイルを保存 |
| `--embed-thumbnail` | サムネイルを埋め込み |
| `--metadata` | メタデータを埋め込み |
| `--archive` / `--no-archive` | ダウンロード済み管理(既定: 有効) |
| `--info` | ダウンロードせず動画情報を表示 |
| `--list-format` | 利用可能フォーマット一覧を表示 |
| `--list-subtitle` | 利用可能字幕一覧を表示 |
| `--update` | yt-dlp を更新 |
| `--help` | ヘルプを表示 |

## Config ファイル

`~/.config/ytd/config.yml` で既定値を変更できます。
優先順位は **コマンドライン引数 > Config > デフォルト値** です。

```yaml
cookie: ~/Downloads/cookies.txt
output: ~/Downloads
format: mp4
quality: best
playlist: false
embed_thumbnail: true
embed_metadata: true
filename_max_length: 120
archive: true
```

## 主な機能

- **ファイル名自動短縮**: タイトルが長い動画(`filename_max_length` 超)は
  自動的に `サイト名_動画ID.拡張子` で保存されます(例: `Youtube_dQw4w9WgXcQ.mp4`)。
- **重複ダウンロード確認**: 同じ動画を再度ダウンロードしようとすると警告し、
  `Y`/`N` で続行可否を確認します(`--archive` が有効な場合)。
- **多重起動防止**: 同一URLに対して同時に複数の `ytd` が実行されるとファイル競合が
  起きるため、実行中のプロセスがあれば新しい実行を拒否します。
- **プレイリストURL誤爆防止**: プレイリストのURL(`list=` を含む)なのに
  `--playlist` を付け忘れた場合、警告した上で先頭1件のみに制限します。

## トラブルシューティング

**`command not found: ytd`**
→ `~/.local/bin` がPATHに入っているか確認してください(`echo $PATH`)。
入っていなければ上記のインストール手順にある `export PATH=...` を設定ファイルに追加してください。

**`✗ yt-dlp が見つかりません`**
→ `python3 -m pip install --user yt-dlp` を実行してください。

**`⚠ ffmpeg が見つかりません`**
→ ディストリビューションに応じてインストールしてください。

```bash
sudo apt install ffmpeg      # Debian / Ubuntu系
sudo dnf install ffmpeg      # Fedora系
sudo pacman -S ffmpeg        # Arch系
```

**動画が途中で止まる・エラーで終わる**
→ `ytd --update` で yt-dlp を最新化してください(YouTube側の仕様変更に追従するため頻繁な更新が必要です)。

## アンインストール

```bash
rm -rf ~/.local/share/ytd
rm -f ~/.local/bin/ytd
rm -rf ~/.config/ytd   # Config・ダウンロード履歴も削除する場合
```

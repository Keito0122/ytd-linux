#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ytd - yt-dlp のコマンドを短縮する Termux 向けラッパーCLI
com.keitodev.ytd.main

仕様書 (ytd 仕様書 / Keito0122/ytd README.md) に基づいて実装。
"""

import argparse
import atexit
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# ---------------------------------------------------------------------------
# 定数・デフォルト値 (仕様 12章)
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "ytd"
CONFIG_PATH = CONFIG_DIR / "config.yml"
ARCHIVE_PATH = CONFIG_DIR / "archive.json"
LOCK_DIR = CONFIG_DIR / "locks"


def _default_output_dir() -> str:
    """OSごとの標準ダウンロードフォルダーを既定の保存先とする。"""
    if platform.system() == "Windows":
        return str(Path.home() / "Downloads")
    # Linux (Termuxでない一般的なディストリビューション)
    xdg = os.environ.get("XDG_DOWNLOAD_DIR")
    if xdg:
        return xdg
    candidate = Path.home() / "Downloads"
    return str(candidate)


DEFAULT_OUTPUT = _default_output_dir()

DEFAULTS = {
    "format": "mp4",
    "quality": "best",
    "cookie": None,
    "output": DEFAULT_OUTPUT,
    "playlist": False,
    "embed_thumbnail": False,
    "embed_metadata": False,
    "filename_max_length": 120,
    "archive": True,
}

AUDIO_FORMATS = {"mp3", "m4a", "aac", "wav", "flac", "opus", "ogg"}
VIDEO_FORMATS = {"mp4", "webm", "mkv"}
VIDEO_QUALITIES = {
    "best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p",
}
AUDIO_BITRATES = {"320k", "256k", "192k", "128k"}

HELP_TEXT = """\
ytd - yt-dlp のコマンドを短縮するツール

基本形:
  ytd "VIDEO_URL"
  ytd "VIDEO_URL" --option value

オプション一覧:
  --format          出力形式を指定する (mp4, webm, mkv, mp3, m4a, aac, wav, flac, opus, ogg)
  --quality         品質を指定する (best, 2160p, 1440p, 1080p, 720p, 480p, 360p, 240p, 144p / 音声: 320k,256k,192k,128k)
  --cookie [PATH]   Cookieを使う。PATH省略時はConfigの既定Cookieを使用
  --output PATH     保存先フォルダーを指定する
  --playlist        プレイリスト全体を取得する
  --audio           音声のみ取得する
  --video-only      映像のみ取得する
  --subtitle        字幕を保存する
  --embed-subtitle  字幕を埋め込む
  --thumbnail       サムネイルを保存する
  --embed-thumbnail サムネイルを埋め込む
  --metadata        メタデータを埋め込む
  --archive         ダウンロード済み管理を行う (デフォルト有効)
  --no-archive      ダウンロード済み管理を無効にする
  --info            動画情報のみ表示する
  --list-format     利用可能フォーマット一覧を表示する
  --list-subtitle   利用可能字幕一覧を表示する
  --update          yt-dlp を更新する
  --help            このヘルプを表示する

代表的な使い方:
  ytd "VIDEO_URL"                                  最高品質で保存
  ytd "VIDEO_URL" --quality 1080p                   1080pで保存
  ytd "VIDEO_URL" --format mp3                      MP3で保存
  ytd "VIDEO_URL" --cookie                          Configの既定Cookieを使用
  ytd "VIDEO_URL" --output /storage/emulated/0/Movies  保存先を指定
  ytd "PLAYLIST_URL" --playlist                     プレイリストを取得

設定ファイル: ~/.config/ytd/config.yml
優先順位: コマンドライン引数 > Config > デフォルト値

⚠ 注意: URLは必ずダブルクォートで囲んでください。
  YouTubeのURLは "&si=..." のようなパラメータを含むことが多く、
  クオートを忘れるとシェル(bash/zsh/cmd.exe/PowerShell)が "&" を
  コマンド区切りと解釈し、オプションが正しく渡りません。
  例: ytd "https://youtube.com/watch?v=xxxx&si=yyyy" --quality 1080p
"""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """~/.config/ytd/config.yml を読み込む。無ければデフォルトのみ返す。"""
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        if yaml is None:
            print(
                "⚠ pyyaml が見つかりません。Config は無視されます。"
                " `pip install pyyaml` でインストールしてください。",
                file=sys.stderr,
            )
            return cfg
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            cfg.update({k: v for k, v in loaded.items() if v is not None})
        except Exception as e:
            print(f"⚠ Config読み込みに失敗しました ({e})。デフォルト値を使用します。", file=sys.stderr)
    return cfg


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# ダウンロード済み管理 (7.7)
# ---------------------------------------------------------------------------

def load_archive() -> dict:
    if ARCHIVE_PATH.exists():
        try:
            with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"ids": []}
    return {"ids": []}


def save_archive(archive: dict):
    ensure_config_dir()
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def get_video_id(url: str, cookie_args: list) -> str | None:
    """yt-dlpでダウンロードせずに動画IDのみ取得する。"""
    cmd = ["yt-dlp", "--no-warnings", "--skip-download", "--print", "%(id)s", url] + cookie_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        vid = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return vid
    except Exception:
        return None


def check_archive_and_confirm(url: str, cookie_args: list, use_archive: bool) -> bool:
    """既にダウンロード済みなら警告して確認する。続行してよければ True。"""
    if not use_archive:
        return True

    video_id = get_video_id(url, cookie_args)
    if video_id is None:
        # ID取得に失敗した場合はチェックをスキップして続行
        return True

    archive = load_archive()
    if video_id in archive.get("ids", []):
        print("⚠ この動画は既にダウンロードされています。")
        answer = input("もう一度ダウンロードしますか？ [Y] Yes / [N] No (default: N): ").strip().lower()
        if answer != "y":
            print("中止しました。")
            return False

    return True


def record_archive(url: str, cookie_args: list):
    video_id = get_video_id(url, cookie_args)
    if video_id is None:
        return
    archive = load_archive()
    if video_id not in archive.get("ids", []):
        archive.setdefault("ids", []).append(video_id)
        save_archive(archive)


# ---------------------------------------------------------------------------
# プレイリストURL判定
# ---------------------------------------------------------------------------

def looks_like_playlist_url(url: str) -> bool:
    """URLがプレイリスト形式(list=パラメータ / playlistページ)かどうかを判定する。"""
    return ("list=" in url) or ("/playlist" in url)


# ---------------------------------------------------------------------------
# 多重起動防止ロック (同一URLへの同時実行によるファイル競合を防ぐ)
# ---------------------------------------------------------------------------

def _lock_file_for(url: str) -> Path:
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return LOCK_DIR / f"{key}.lock"


def _pid_is_alive(pid: int) -> bool:
    if platform.system() == "Windows":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # 権限エラー = 別ユーザーのプロセスとして生存している
        return True
    except Exception:
        return False


def acquire_lock(url: str) -> Path | None:
    """
    同じURLに対する多重実行を防ぐ。
    既に実行中(プロセス生存)なら None を返す。
    古い(プロセスが死んでいる)ロックは自動的に上書きする。
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_file_for(url)

    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text().strip())
        except Exception:
            existing_pid = None
        if existing_pid and _pid_is_alive(existing_pid) and existing_pid != os.getpid():
            return None
        # 古いロックは掃除して継続

    lock_path.write_text(str(os.getpid()))
    atexit.register(release_lock, lock_path)
    return lock_path


def release_lock(lock_path: Path):
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ファイル名自動短縮 (7.6)
# ---------------------------------------------------------------------------

def build_output_template(url: str, cookie_args: list, max_length: int, output_dir: str) -> str:
    """
    タイトルが長すぎる場合は "サイト名_ID.ext" 形式に自動短縮する。
    それ以外は通常のタイトルを使う。
    """
    cmd = [
        "yt-dlp", "--no-warnings", "--skip-download",
        "--print", "%(title)s",
        "--print", "%(extractor_key)s",
        url,
    ] + cookie_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().splitlines()
        title = lines[0] if len(lines) >= 1 else ""
        extractor = lines[1] if len(lines) >= 2 else "Video"
    except Exception:
        title = ""
        extractor = "Video"

    if title and len(title) <= max_length:
        template = "%(title)s.%(ext)s"
    else:
        # 例: YouTube_dQw4w9WgXcQ.mp4 / Niconico_sm12345678.mp4
        template = f"{extractor}_%(id)s.%(ext)s"

    return str(Path(output_dir) / template)


# ---------------------------------------------------------------------------
# 引数変換ロジック
# ---------------------------------------------------------------------------

def resolve_value(cli_value, config_value, default_value):
    """優先順位: CLI引数 > Config > デフォルト値 (仕様11章)"""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value


def build_format_selector(fmt: str, quality: str, audio_only: bool, video_only: bool) -> tuple[list, str | None]:
    """
    --format / --quality から yt-dlp の -f / 拡張子オプションを組み立てる。
    戻り値: (yt-dlp追加引数, 音声抽出フォーマット or None)
    """
    args = []
    audio_extract_fmt = None

    is_audio_format = fmt in AUDIO_FORMATS

    if is_audio_format or audio_only:
        # 音声抽出として扱う
        args += ["-x"]
        if is_audio_format:
            audio_extract_fmt = fmt
            args += ["--audio-format", fmt]
        if quality in AUDIO_BITRATES:
            bitrate = quality.rstrip("k")
            args += ["--audio-quality", bitrate + "K" if not quality.endswith("K") else quality]
        elif quality == "best":
            args += ["--audio-quality", "0"]
    else:
        # 動画として扱う
        height_map = {
            "2160p": 2160, "1440p": 1440, "1080p": 1080, "720p": 720,
            "480p": 480, "360p": 360, "240p": 240, "144p": 144,
        }
        if video_only:
            if quality == "best" or quality not in height_map:
                args += ["-f", "bestvideo"]
            else:
                h = height_map[quality]
                args += ["-f", f"bestvideo[height<={h}]"]
        else:
            if quality == "best" or quality not in height_map:
                args += ["-f", "bestvideo+bestaudio/best"]
            else:
                h = height_map[quality]
                args += ["-f", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"]

        if fmt in VIDEO_FORMATS:
            args += ["--merge-output-format", fmt]

    return args, audio_extract_fmt


def build_cookie_args(cookie_cli, cookie_config) -> list:
    """
    --cookie の解決 (仕様 7.3)
    - フラグのみ: Configの既定Cookieを使用
    - パス指定あり: そのファイルを使用
    - どちらも無ければ Cookie なし
    """
    if cookie_cli is True:
        # --cookie のみ指定 (値なし)
        if cookie_config:
            return ["--cookies", cookie_config]
        return []
    if isinstance(cookie_cli, str):
        return ["--cookies", os.path.expanduser(cookie_cli)]
    # --cookie 自体が指定されていない場合は Cookie を使わない
    return []


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def check_dependency(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def print_ffmpeg_hint():
    system = platform.system()
    if system == "Windows":
        hint = (
            "  winget install --id Gyan.FFmpeg -e\n"
            "  または https://www.gyan.dev/ffmpeg/builds/ から取得してPATHに追加してください。"
        )
    else:
        hint = (
            "  Debian/Ubuntu系: sudo apt install ffmpeg\n"
            "  Fedora系       : sudo dnf install ffmpeg\n"
            "  Arch系         : sudo pacman -S ffmpeg"
        )
    print(f"⚠ ffmpeg が見つかりません。動画結合や音声変換ができない場合があります。\n{hint}", file=sys.stderr)


def run_ytdlp(cmd: list):
    print("▶ 実行中: " + " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ytd", add_help=False)
    parser.add_argument("url", nargs="?", help="動画・プレイリストのURL")
    parser.add_argument("--format", dest="format", default=None)
    parser.add_argument("--quality", dest="quality", default=None)
    parser.add_argument("--cookie", dest="cookie", nargs="?", const=True, default=None)
    parser.add_argument("--output", dest="output", default=None)
    parser.add_argument("--playlist", dest="playlist", action="store_true", default=None)
    parser.add_argument("--audio", dest="audio", action="store_true")
    parser.add_argument("--video-only", dest="video_only", action="store_true")
    parser.add_argument("--subtitle", dest="subtitle", action="store_true")
    parser.add_argument("--embed-subtitle", dest="embed_subtitle", action="store_true")
    parser.add_argument("--thumbnail", dest="thumbnail", action="store_true")
    parser.add_argument("--embed-thumbnail", dest="embed_thumbnail", action="store_true", default=None)
    parser.add_argument("--metadata", dest="metadata", action="store_true", default=None)
    parser.add_argument("--archive", dest="archive", action="store_true", default=None)
    parser.add_argument("--no-archive", dest="no_archive", action="store_true")
    parser.add_argument("--info", dest="info", action="store_true")
    parser.add_argument("--list-format", dest="list_format", action="store_true")
    parser.add_argument("--list-subtitle", dest="list_subtitle", action="store_true")
    parser.add_argument("--update", dest="update", action="store_true")
    parser.add_argument("--help", dest="help", action="store_true")
    return parser


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.help or (args.url is None and not args.update):
        print(HELP_TEXT)
        return 0

    if args.update:
        if not check_dependency("yt-dlp"):
            print("✗ yt-dlp が見つかりません。`pip install -U yt-dlp` を実行してください。", file=sys.stderr)
            return 1
        return run_ytdlp(["yt-dlp", "-U"])

    if not check_dependency("yt-dlp"):
        print("✗ yt-dlp が見つかりません。`pip install yt-dlp` でインストールしてください。", file=sys.stderr)
        return 1

    if not check_dependency("ffmpeg"):
        print_ffmpeg_hint()

    cfg = load_config()

    fmt = resolve_value(args.format, cfg.get("format"), DEFAULTS["format"])
    quality = resolve_value(args.quality, cfg.get("quality"), DEFAULTS["quality"])
    output_dir = os.path.expanduser(resolve_value(args.output, cfg.get("output"), DEFAULTS["output"]))
    playlist = resolve_value(args.playlist, cfg.get("playlist"), DEFAULTS["playlist"])
    embed_thumbnail = resolve_value(args.embed_thumbnail, cfg.get("embed_thumbnail"), DEFAULTS["embed_thumbnail"])
    embed_metadata = resolve_value(args.metadata, cfg.get("embed_metadata"), DEFAULTS["embed_metadata"])
    filename_max_length = int(cfg.get("filename_max_length", DEFAULTS["filename_max_length"]))
    use_archive_default = resolve_value(args.archive, cfg.get("archive"), DEFAULTS["archive"])
    use_archive = False if args.no_archive else use_archive_default

    if fmt not in AUDIO_FORMATS and fmt not in VIDEO_FORMATS:
        print(f"✗ 未対応のフォーマットです: {fmt}", file=sys.stderr)
        return 1
    if quality not in VIDEO_QUALITIES and quality not in AUDIO_BITRATES:
        print(f"✗ 未対応の品質指定です: {quality}", file=sys.stderr)
        return 1

    cookie_config = cfg.get("cookie")
    if cookie_config:
        cookie_config = os.path.expanduser(cookie_config)
    cookie_args = build_cookie_args(args.cookie, cookie_config)

    url = args.url

    # --info / --list-format / --list-subtitle は情報表示のみ
    if args.info:
        return run_ytdlp(["yt-dlp", "--dump-json", url] + cookie_args)
    if args.list_format:
        return run_ytdlp(["yt-dlp", "-F", url] + cookie_args)
    if args.list_subtitle:
        return run_ytdlp(["yt-dlp", "--list-subs", url] + cookie_args)

    # プレイリストURLなのに --playlist が付いていない場合は警告する。
    # (これが無いと yt-dlp の --no-playlist は playlist?list=... 形式のURLには
    #  効かず、意図せず全件ダウンロードされてしまうことがある)
    url_is_playlist_shaped = looks_like_playlist_url(url)
    if not playlist and url_is_playlist_shaped:
        print(
            "⚠ このURLはプレイリストのようですが --playlist が指定されていません。\n"
            "  安全のため先頭の1件のみ取得します。プレイリスト全体が欲しい場合は\n"
            "  --playlist を付けて実行し直してください。"
        )

    # 同一URLへの多重実行防止 (シェルの引用符忘れ等でバックグラウンド起動が
    # 重複した場合のファイル競合を防ぐ)
    lock_path = acquire_lock(url)
    if lock_path is None:
        print("✗ 同じURLに対する ytd が既に実行中です。多重起動は行いません。", file=sys.stderr)
        return 1

    try:
        # 重複ダウンロード確認 (プレイリストの場合はスキップし yt-dlp 内蔵管理に委ねる)
        if not playlist:
            if not check_archive_and_confirm(url, cookie_args, use_archive):
                return 0

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        fmt_args, _audio_fmt = build_format_selector(fmt, quality, args.audio, args.video_only)

        # ファイル名自動短縮 (プレイリストは %(title)s のまま。長さは個別対応が難しいため簡略化)
        if playlist:
            out_template = str(Path(output_dir) / "%(playlist_title)s/%(title)s.%(ext)s")
        else:
            out_template = build_output_template(url, cookie_args, filename_max_length, output_dir)

        cmd = ["yt-dlp", url, "-o", out_template] + fmt_args + cookie_args

        if not playlist:
            cmd += ["--no-playlist"]
            if url_is_playlist_shaped:
                # --no-playlist が効かない playlist?list=... 形式のURL向けの保険
                cmd += ["--playlist-items", "1"]

        if args.subtitle:
            cmd += ["--write-sub", "--sub-langs", "all"]
        if args.embed_subtitle:
            cmd += ["--embed-subs", "--write-sub", "--sub-langs", "all"]
        if args.thumbnail:
            cmd += ["--write-thumbnail"]
        if embed_thumbnail:
            cmd += ["--embed-thumbnail", "--write-thumbnail"]
        if embed_metadata:
            cmd += ["--add-metadata"]

        rc = run_ytdlp(cmd)

        if rc == 0 and not playlist:
            record_archive(url, cookie_args)

        return rc
    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    sys.exit(main())

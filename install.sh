#!/usr/bin/env bash
# ytd インストールスクリプト (一般的なLinuxディストリビューション向け)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/ytd"
BIN_DIR="$HOME/.local/bin"

echo "-> Python / pip を確認しています..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "  python3 が見つかりません。ディストリビューションのパッケージマネージャでインストールしてください。" >&2
    exit 1
fi

echo "-> 依存パッケージをインストールしています..."
python3 -m pip install --user --upgrade yt-dlp pyyaml

echo "-> ffmpeg を確認しています..."
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "  ffmpeg が見つかりません。"
    if command -v apt >/dev/null 2>&1; then
        echo "  検出: apt (Debian/Ubuntu系) -> sudo apt install ffmpeg"
    elif command -v dnf >/dev/null 2>&1; then
        echo "  検出: dnf (Fedora系)        -> sudo dnf install ffmpeg"
    elif command -v pacman >/dev/null 2>&1; then
        echo "  検出: pacman (Arch系)       -> sudo pacman -S ffmpeg"
    else
        echo "  お使いのディストリビューションのパッケージマネージャでffmpegをインストールしてください。"
    fi
fi

echo "-> ytd を $INSTALL_DIR に配置しています..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/com" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/bin" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/bin/ytd"

echo "-> シンボリックリンクを作成しています..."
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/bin/ytd" "$BIN_DIR/ytd"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "  ⚠ $BIN_DIR がPATHに入っていません。使用しているシェルの設定ファイル"
    echo "    (~/.bashrc や ~/.zshrc など)に以下を追加し、シェルを再起動してください:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo "-> Config ディレクトリを準備しています..."
mkdir -p "$HOME/.config/ytd"
if [ ! -f "$HOME/.config/ytd/config.yml" ]; then
    cp "$SCRIPT_DIR/config.yml.example" "$HOME/.config/ytd/config.yml"
    echo "  ~/.config/ytd/config.yml を作成しました。中身を編集して使ってください。"
fi

echo ""
echo "✔ インストール完了。以下のコマンドで使えます:"
echo "    ytd \"VIDEO_URL\""
echo "    ytd --help"

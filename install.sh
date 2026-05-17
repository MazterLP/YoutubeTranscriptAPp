#!/usr/bin/env bash
# YouTube Transcript Downloader — Linux/macOS Installer
# Usage (one-liner):
#   curl -fsSL https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.sh | bash
# Or run directly:
#   bash install.sh

set -e

REPO_URL="https://github.com/MazterLP/YoutubeTranscriptAPp.git"
INSTALL_DIR="$HOME/YoutubeTranscriptAPp"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo -e "\n${CYAN}==> $*${NC}"; }
ok()    { echo -e "    ${GREEN}OK  $*${NC}"; }
warn()  { echo -e "    ${YELLOW}WARN $*${NC}"; }
fail()  { echo -e "    ${RED}FAIL $*${NC}"; exit 1; }

echo -e "${CYAN}
  ┌─────────────────────────────────────────────┐
  │   YouTube Transcript Downloader — Installer  │
  └─────────────────────────────────────────────┘
${NC}"

# ── 1. Check Git ──────────────────────────────────────────────────────────────
step "Checking Git"
command -v git &>/dev/null || fail "Git not found. Install: sudo apt install git"
ok "$(git --version)"

# ── 2. Check Python 3.8+ ─────────────────────────────────────────────────────
step "Checking Python"
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || fail "Python 3 not found. Install: sudo apt install python3"
PYVER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" \
    || fail "Python $PYVER found but 3.8+ required."
ok "Python $PYVER at $PY"

# ── 3. Check python3-tk (Tkinter GUI) ────────────────────────────────────────
step "Checking Tkinter"
if $PY -c "import tkinter" &>/dev/null; then
    ok "Tkinter available"
else
    warn "Tkinter not found — installing python3-tk..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y python3-tk
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-tkinter
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm tk
    else
        warn "Could not auto-install Tkinter. Install manually: sudo apt install python3-tk"
    fi
fi

# ── 4. Check FFmpeg ───────────────────────────────────────────────────────────
step "Checking FFmpeg"
if command -v ffmpeg &>/dev/null; then
    ok "$(ffmpeg -version 2>&1 | head -1)"
else
    warn "FFmpeg not found — installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y ffmpeg
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y ffmpeg
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm ffmpeg
    else
        warn "Could not auto-install FFmpeg. Install manually: sudo apt install ffmpeg"
    fi
    command -v ffmpeg &>/dev/null && ok "$(ffmpeg -version 2>&1 | head -1)" || warn "FFmpeg install may have failed — Whisper fallback will not work"
fi

# ── 5. Clone or update repo ───────────────────────────────────────────────────
step "Setting up repository at $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "    Repo already exists — pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
ok "Repository ready"

# ── 6. Create virtual environment ─────────────────────────────────────────────
step "Creating Python virtual environment"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    $PY -m venv "$INSTALL_DIR/.venv"
    ok "Created $INSTALL_DIR/.venv"
else
    ok "venv already exists — skipping"
fi

# ── 7. Install dependencies ───────────────────────────────────────────────────
step "Installing dependencies (yt-dlp, faster-whisper, pandas)"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
ok "Dependencies installed"

# ── 8. Desktop launcher (.desktop file for GNOME/KDE) ─────────────────────────
step "Creating desktop launcher"
DESKTOP_FILE="$HOME/Desktop/youtube-transcript.desktop"
APPLICATIONS_FILE="$HOME/.local/share/applications/youtube-transcript.desktop"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"

ICO_FILE="$INSTALL_DIR/icons8-youtube-studio-100.ico"
ICON_LINE=""
[ -f "$ICO_FILE" ] && ICON_LINE="Icon=$ICO_FILE"

DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=YouTube Transcript
Comment=Download and transcribe YouTube channel videos
Exec=$VENV_PYTHON $INSTALL_DIR/app.py
Path=$INSTALL_DIR
Terminal=false
Categories=Utility;
$ICON_LINE"

mkdir -p "$HOME/.local/share/applications"
echo "$DESKTOP_CONTENT" > "$APPLICATIONS_FILE"
chmod +x "$APPLICATIONS_FILE"

if [ -d "$HOME/Desktop" ]; then
    echo "$DESKTOP_CONTENT" > "$DESKTOP_FILE"
    chmod +x "$DESKTOP_FILE"
    # Trust the launcher so GNOME lets users double-click it
    command -v gio &>/dev/null && gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    ok "Desktop launcher: $DESKTOP_FILE"
fi
ok "App launcher registered: $APPLICATIONS_FILE"

# ── 9. Done ────────────────────────────────────────────────────────────────────
echo -e "${GREEN}
  ┌──────────────────────────────────────────────────────────┐
  │  Installation complete!                                   │
  │                                                           │
  │  Run the app:                                             │
  │    Double-click 'YouTube Transcript' on your Desktop      │
  │  Or from terminal:                                        │
  │    cd $INSTALL_DIR
  │    ./.venv/bin/python3 app.py                             │
  │                                                           │
  │  (Optional) Put cookies.txt in $INSTALL_DIR               │
  │  for faster downloads and fewer rate-limits.              │
  └──────────────────────────────────────────────────────────┘
${NC}"

#!/usr/bin/env bash
# YouTube Transcript Downloader — Linux/macOS Installer
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.sh | bash

set -e

REPO_URL="https://github.com/MazterLP/YoutubeTranscriptAPp.git"
INSTALL_DIR="$HOME/YoutubeTranscriptAPp"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${CYAN}==> $*${NC}"; }
ok()   { echo -e "    ${GREEN}OK  $*${NC}"; }
warn() { echo -e "    ${YELLOW}WARN $*${NC}"; }
fail() { echo -e "    ${RED}FAIL $*${NC}"; exit 1; }

pkg_install() {
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y "$@"
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y "$@"
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm "$@"
    else
        warn "Cannot auto-install $* — install manually then re-run."
    fi
}

echo -e "${CYAN}
  ┌─────────────────────────────────────────────┐
  │   YouTube Transcript Downloader — Installer  │
  └─────────────────────────────────────────────┘
${NC}"

# ── 1. Git ────────────────────────────────────────────────────────────────────
step "Checking Git"
if ! command -v git &>/dev/null; then
    warn "Git not found — installing..."
    pkg_install git
fi
ok "$(git --version)"

# ── 2. Python 3.8+ ───────────────────────────────────────────────────────────
step "Checking Python"
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
    warn "Python 3 not found — installing..."
    pkg_install python3
    PY=$(command -v python3)
fi
$PY -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" \
    || fail "Python $($PY --version) found but 3.8+ is required."
ok "$($PY --version) at $PY"

# ── 3. Tkinter ────────────────────────────────────────────────────────────────
step "Checking Tkinter"
if ! $PY -c "import tkinter" &>/dev/null; then
    warn "Tkinter not found — installing..."
    pkg_install python3-tk
fi
ok "Tkinter available"

# ── 4. FFmpeg ─────────────────────────────────────────────────────────────────
step "Checking FFmpeg"
if ! command -v ffmpeg &>/dev/null; then
    warn "FFmpeg not found — installing..."
    pkg_install ffmpeg
fi
command -v ffmpeg &>/dev/null \
    && ok "$(ffmpeg -version 2>&1 | head -1)" \
    || warn "FFmpeg install may have failed — Whisper fallback will not work"

# ── 5. Clone or update repo ───────────────────────────────────────────────────
step "Setting up repository at $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "    Repo already exists — pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
ok "Repository ready"

# ── 6. Python venv ────────────────────────────────────────────────────────────
step "Creating Python virtual environment"

# Remove broken venv from a previous failed install
if [ -d "$INSTALL_DIR/.venv" ] && { [ ! -f "$INSTALL_DIR/.venv/bin/python3" ] || [ ! -f "$INSTALL_DIR/.venv/bin/pip" ]; }; then
    warn "Broken venv detected — removing..."
    rm -rf "$INSTALL_DIR/.venv"
fi

if [ ! -d "$INSTALL_DIR/.venv" ]; then
    # Ensure venv module is available
    if ! $PY -m venv --help &>/dev/null 2>&1; then
        warn "python3-venv not found — installing..."
        PYVER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y "python${PYVER}-venv" 2>/dev/null \
                || sudo apt-get install -y python3-venv
        else
            pkg_install python3-venv
        fi
    fi
    $PY -m venv "$INSTALL_DIR/.venv"
    ok "Created $INSTALL_DIR/.venv"
else
    ok "venv already exists — skipping"
fi

# ── 7. Python dependencies ────────────────────────────────────────────────────
step "Installing dependencies (yt-dlp, faster-whisper, pandas)"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
ok "Dependencies installed"

# ── 8. Desktop launcher ───────────────────────────────────────────────────────
step "Creating desktop launcher"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
APPLICATIONS_FILE="$HOME/.local/share/applications/youtube-transcript.desktop"
DESKTOP_FILE="$HOME/Desktop/youtube-transcript.desktop"
ICO_FILE="$INSTALL_DIR/icons8-youtube-studio-100.ico"

DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=YouTube Transcript
Comment=Download and transcribe YouTube channel videos
Exec=$VENV_PYTHON $INSTALL_DIR/app.py
Path=$INSTALL_DIR
Terminal=false
Categories=Utility;
$([ -f "$ICO_FILE" ] && echo "Icon=$ICO_FILE")"

mkdir -p "$HOME/.local/share/applications"
printf '%s\n' "$DESKTOP_CONTENT" > "$APPLICATIONS_FILE"
chmod +x "$APPLICATIONS_FILE"

if [ -d "$HOME/Desktop" ]; then
    printf '%s\n' "$DESKTOP_CONTENT" > "$DESKTOP_FILE"
    chmod +x "$DESKTOP_FILE"
    command -v gio &>/dev/null && gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    ok "Desktop launcher: $DESKTOP_FILE"
fi
ok "App launcher registered (app menu)"

# ── 9. Done ───────────────────────────────────────────────────────────────────
echo -e "${GREEN}
  ┌──────────────────────────────────────────────────────────┐
  │  Installation complete!                                   │
  │                                                           │
  │  Launch the app:                                          │
  │    Double-click 'YouTube Transcript' on your Desktop      │
  │  Or from terminal:                                        │
  │    $INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/app.py    │
  │                                                           │
  │  Tip: add cookies.txt to $INSTALL_DIR                     │
  │  to avoid YouTube rate-limits.                            │
  └──────────────────────────────────────────────────────────┘
${NC}"

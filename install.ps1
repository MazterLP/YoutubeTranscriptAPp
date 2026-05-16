# YouTube Transcript Downloader — Windows Installer
# Usage (one-liner):
#   irm https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.ps1 | iex
# Or run directly:
#   .\install.ps1

$ErrorActionPreference = "Stop"
$REPO_URL  = "https://github.com/MazterLP/YoutubeTranscriptAPp.git"
$INSTALL_DIR = Join-Path $HOME "YoutubeTranscriptAPp"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    WARN $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    FAIL $msg" -ForegroundColor Red; exit 1 }

Write-Host @"

  ┌─────────────────────────────────────────────┐
  │   YouTube Transcript Downloader — Installer  │
  └─────────────────────────────────────────────┘

"@ -ForegroundColor Cyan

# ── 1. Check Git ─────────────────────────────────────────────────────────────
Write-Step "Checking Git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "Git not found. Install from https://git-scm.com/download/win then re-run."
}
Write-OK (git --version)

# ── 2. Check Python 3.8+ ─────────────────────────────────────────────────────
Write-Step "Checking Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Fail "Python not found. Install from https://www.python.org/downloads then re-run."
}
$pyver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([float]$pyver -lt 3.8) {
    Write-Fail "Python $pyver found but 3.8+ required."
}
Write-OK "Python $pyver at $($py.Source)"

# ── 3. Check FFmpeg (needed for Whisper audio extraction) ────────────────────
Write-Step "Checking FFmpeg"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-OK (ffmpeg -version 2>&1 | Select-Object -First 1)
} else {
    Write-Warn "FFmpeg not found on PATH. The Whisper fallback phase will fail."
    Write-Warn "Install: https://ffmpeg.org/download.html and add to PATH."
}

# ── 4. Clone or update repo ──────────────────────────────────────────────────
Write-Step "Setting up repository at $INSTALL_DIR"
if (Test-Path (Join-Path $INSTALL_DIR ".git")) {
    Write-Host "    Repo already exists — pulling latest..." -ForegroundColor Gray
    Push-Location $INSTALL_DIR
    git pull --ff-only
    Pop-Location
} else {
    git clone $REPO_URL $INSTALL_DIR
}
Write-OK "Repository ready"

# ── 5. Create virtual environment ────────────────────────────────────────────
Write-Step "Creating Python virtual environment"
$venv = Join-Path $INSTALL_DIR ".venv"
if (-not (Test-Path $venv)) {
    & python -m venv $venv
    Write-OK "Created $venv"
} else {
    Write-OK "venv already exists — skipping"
}

# ── 6. Install dependencies ──────────────────────────────────────────────────
Write-Step "Installing dependencies (yt-dlp, faster-whisper, pandas)"
$pip = Join-Path $venv "Scripts\pip.exe"
& $pip install --upgrade pip -q
& $pip install -r (Join-Path $INSTALL_DIR "requirements.txt")
Write-OK "Dependencies installed"

# ── 7. Desktop shortcut ──────────────────────────────────────────────────────
Write-Step "Creating desktop shortcut"
$pythonw = Join-Path $venv "Scripts\pythonw.exe"
# Fallback: system pythonw if venv doesn't have it
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue)?.Source
}
if ($pythonw) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnk_path = Join-Path $desktop "YouTube Transcript.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($lnk_path)
    $s.TargetPath = $pythonw
    $s.Arguments = "`"$(Join-Path $INSTALL_DIR 'app.py')`""
    $s.WorkingDirectory = $INSTALL_DIR
    $s.Description = "YouTube Transcript Downloader"
    $ico = Join-Path $INSTALL_DIR "icons8-youtube-studio-100.ico"
    $s.IconLocation = if (Test-Path $ico) { "$ico,0" } else { "$pythonw,0" }
    $s.Save()
    Write-OK "Shortcut created: $lnk_path"
} else {
    Write-Warn "pythonw.exe not found — skipping shortcut. Launch manually with:"
    Write-Warn "  & `"$(Join-Path $venv 'Scripts\python.exe')`" `"$(Join-Path $INSTALL_DIR 'app.py')`""
}

# ── 8. Done ──────────────────────────────────────────────────────────────────
Write-Host @"

  ┌──────────────────────────────────────────────────────────┐
  │  Installation complete!                                   │
  │                                                           │
  │  Run the app:                                             │
  │    Double-click "YouTube Transcript" on your Desktop      │
  │  Or from terminal:                                        │
  │    cd $INSTALL_DIR
  │    .\.venv\Scripts\python.exe app.py                      │
  │                                                           │
  │  (Optional) Put cookies.txt in $INSTALL_DIR               │
  │  for faster downloads and fewer rate-limits.              │
  └──────────────────────────────────────────────────────────┘

"@ -ForegroundColor Green

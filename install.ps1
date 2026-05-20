# YouTube Transcript + Strategy Pipeline — Windows Installer
# Installs: Git, Python 3.11, FFmpeg, Ollama, pulls qwen3:14b, sets up the app.
#
# Usage (run once in PowerShell as normal user):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # allow scripts once
#   .\install.ps1
#
# Or one-liner from the internet:
#   irm https://raw.githubusercontent.com/MazterLP/YoutubeTranscriptAPp/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO_URL    = "https://github.com/MazterLP/YoutubeTranscriptAPp.git"
$INSTALL_DIR = Join-Path $HOME "YoutubeTranscriptAPp"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    WARN $msg" -ForegroundColor Yellow }
function Write-Info { param($msg) Write-Host "    ... $msg" -ForegroundColor Gray }
function Write-Fail { param($msg) Write-Host "    FAIL $msg" -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH","User")
}

function Winget-Install { param($id, $label)
    Write-Info "Installing $label via winget..."
    winget install --id $id --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

Write-Host @"

  ┌──────────────────────────────────────────────────────────┐
  │   YouTube Transcript + Strategy Pipeline — Installer      │
  └──────────────────────────────────────────────────────────┘

"@ -ForegroundColor Cyan

# ── 0. Require winget ────────────────────────────────────────────────────────
Write-Step "Checking winget (Windows Package Manager)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Fail "winget not found. Update Windows or install App Installer from the Microsoft Store, then re-run."
}
Write-OK "winget $(winget --version)"

# ── 1. Git ───────────────────────────────────────────────────────────────────
Write-Step "Checking Git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Winget-Install "Git.Git" "Git"
    Refresh-Path
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "Git still not found after install — open a new PowerShell window and re-run."
}
Write-OK (git --version)

# ── 2. Python 3.11 ───────────────────────────────────────────────────────────
Write-Step "Checking Python 3.8+"
$py = Get-Command python -ErrorAction SilentlyContinue
$need_python = $true
if ($py) {
    $ver_str = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($ver_str -match '^(\d+)\.(\d+)$') {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 8)) {
            Write-OK "Python $ver_str at $($py.Source)"
            $need_python = $false
        } else {
            Write-Warn "Python $ver_str is too old — installing 3.11."
        }
    }
}
if ($need_python) {
    Winget-Install "Python.Python.3.11" "Python 3.11"
    Refresh-Path
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Fail "Python still not found after install — open a new PowerShell window and re-run."
    }
    Write-OK "Python installed at $($py.Source)"
}

# ── 3. FFmpeg ────────────────────────────────────────────────────────────────
Write-Step "Checking FFmpeg (required for Whisper audio)"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Winget-Install "Gyan.FFmpeg" "FFmpeg"
    Refresh-Path
}
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-OK (ffmpeg -version 2>&1 | Select-Object -First 1)
} else {
    Write-Warn "FFmpeg install may need a new shell to take effect. Whisper fallback may fail until then."
}

# ── 4. Ollama ────────────────────────────────────────────────────────────────
Write-Step "Checking Ollama (local LLM for strategy extraction)"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Info "Downloading Ollama installer..."
    $ollamaExe = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $ollamaExe -UseBasicParsing
    Write-Info "Running Ollama installer (silent)..."
    Start-Process $ollamaExe -ArgumentList "/S" -Wait
    Refresh-Path
}
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-OK "Ollama $(ollama --version 2>$null)"
} else {
    Write-Warn "Ollama install may need a new shell to take effect. Re-run installer if needed."
}

# ── 5. Pull qwen3:14b model (~9 GB, one-time download) ──────────────────────
Write-Step "Checking qwen3:14b model"
$model_ok = $false
try {
    $list = & ollama list 2>$null
    if ($list -match "qwen3:14b") { $model_ok = $true }
} catch {}

if ($model_ok) {
    Write-OK "qwen3:14b already downloaded"
} else {
    Write-Host "    Pulling qwen3:14b (~9 GB). This may take a while..." -ForegroundColor Yellow
    Write-Host "    You can Ctrl+C and re-run later — progress is saved." -ForegroundColor Gray
    # Start ollama serve in background if not already running
    $serving = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $serving) {
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep 3
    }
    & ollama pull qwen3:14b
    Write-OK "qwen3:14b ready"
}

# ── 6. Clone or update repo ──────────────────────────────────────────────────
Write-Step "Setting up repository at $INSTALL_DIR"
if (Test-Path (Join-Path $INSTALL_DIR ".git")) {
    Write-Info "Repo already exists — pulling latest..."
    Push-Location $INSTALL_DIR
    git pull --ff-only
    Pop-Location
} else {
    git clone $REPO_URL $INSTALL_DIR
}
Write-OK "Repository ready"

# ── 7. Python virtual environment ────────────────────────────────────────────
Write-Step "Creating Python virtual environment"
$venv = Join-Path $INSTALL_DIR ".venv"
if (-not (Test-Path $venv)) {
    & python -m venv $venv
    Write-OK "Created $venv"
} else {
    Write-OK "venv already exists — skipping"
}

# ── 8. Install Python dependencies ───────────────────────────────────────────
Write-Step "Installing Python dependencies"
$pip = Join-Path $venv "Scripts\pip.exe"
& $pip install --upgrade pip -q
& $pip install -r (Join-Path $INSTALL_DIR "requirements.txt")
Write-OK "Dependencies installed"

# ── 9. Create desktop shortcut ───────────────────────────────────────────────
Write-Step "Creating desktop shortcut"
$pythonw = Join-Path $venv "Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue)?.Source
}
if ($pythonw) {
    $desktop  = [Environment]::GetFolderPath('Desktop')
    $lnk_path = Join-Path $desktop "YouTube Transcript.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $s  = $ws.CreateShortcut($lnk_path)
    $s.TargetPath      = $pythonw
    $s.Arguments       = "`"$(Join-Path $INSTALL_DIR 'app.py')`""
    $s.WorkingDirectory = $INSTALL_DIR
    $s.Description     = "YouTube Transcript + Strategy Pipeline"
    $ico = Join-Path $INSTALL_DIR "icons8-youtube-studio-100.ico"
    $s.IconLocation    = if (Test-Path $ico) { "$ico,0" } else { "$pythonw,0" }
    $s.Save()
    Write-OK "Shortcut created: $lnk_path"
} else {
    Write-Warn "pythonw.exe not found — launch manually:"
    Write-Warn "  & `"$(Join-Path $venv 'Scripts\python.exe')`" `"$(Join-Path $INSTALL_DIR 'app.py')`""
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host @"

  ┌──────────────────────────────────────────────────────────┐
  │  All done! Everything is installed.                       │
  │                                                           │
  │  Launch the app:                                          │
  │    Double-click "YouTube Transcript" on your Desktop      │
  │                                                           │
  │  Or from terminal:                                        │
  │    cd "$INSTALL_DIR"
  │    .\.venv\Scripts\python.exe app.py                      │
  │                                                           │
  │  Ollama runs automatically in the background.             │
  │  (Optional) Put cookies.txt in the install folder         │
  │  for faster downloads and fewer YouTube rate-limits.      │
  └──────────────────────────────────────────────────────────┘

"@ -ForegroundColor Green

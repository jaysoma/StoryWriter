# run-storywriter.ps1 — get the whole StoryWriter stack running NOW, with checks.
#
#   powershell -ExecutionPolicy Bypass -File .\run-storywriter.ps1
#
# What it does, in order:
#   1. verifies the 3.12 backend deps (pymongo, numpy, ffmpeg)
#   2. checks Ollama is up and the model is pulled   (hard requirement)
#   3. checks MongoDB                                 (OPTIONAL — only for opening-page
#      style exemplars; generation works without it)
#   4. frees :80 and :8000, then launches the gateway (3.14) and backend (3.12) hidden
#   5. waits, reports UP/DOWN, and opens the browser
#
# Flags:
#   -Model qwen2.5:7b   model tag to require/use (default qwen2.5:7b)
#   -NoOpen             don't auto-open the browser
#   -Foreground         run the backend in THIS window with logs (debugging)

param(
    [string]$Model = "qwen2.5:7b",
    [switch]$NoOpen,
    [switch]$Foreground
)

$ErrorActionPreference = 'SilentlyContinue'

$portfolio = "C:\Projects\GithubRoot\Portfolio"
$root      = "C:\Projects\GithubRoot\Portfolio\StoryWriter"

# server.py + the generator/extractor it spawns MUST run on the 3.12 that has
# pymongo + numpy + imageio-ffmpeg.
$backendPy    = "C:\Program Files\Python312\python.exe"      # console build, for checks
$backendPyw   = "C:\Program Files\Python312\pythonw.exe"     # windowless, for launch
$gatewayPy    = "C:\Users\Jay\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $gatewayPy)) { $gatewayPy = $backendPy }

$ok = $true
function Say($m,$c='Gray'){ Write-Host $m -ForegroundColor $c }
function Good($m){ Say "  OK    $m" Green }
function Warn($m){ Say "  WARN  $m" Yellow }
function Bad ($m){ Say "  FAIL  $m" Red; $script:ok = $false }

function Listening($port){ [bool](Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue) }
function Free-Port($port){
    Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
    for ($i = 0; $i -lt 20; $i++){
        if (-not (Listening $port)) { return }
        Start-Sleep -Milliseconds 250
    }
}

Say "`n=== 1. Backend Python deps (3.12) ===" Cyan
if (-not (Test-Path $backendPy)) {
    Bad "Python 3.12 not found at $backendPy"
} else {
    $probe = & $backendPy -c "import pymongo,numpy;print('deps-ok')" 2>&1
    if ($probe -match 'deps-ok') { Good "pymongo + numpy present" }
    else { Bad "missing backend deps -> & `"$backendPy`" -m pip install pymongo numpy imageio-ffmpeg" }

    $ff = & $backendPy -c "import shutil,sys; p=shutil.which('ffmpeg')`nif not p:`n try:`n  import imageio_ffmpeg as i; p=i.get_ffmpeg_exe()`n except Exception: p=None`nprint(p or 'NONE')" 2>&1
    if ($ff -and $ff -ne 'NONE') { Good "ffmpeg: $ff" }
    else { Bad "ffmpeg not found -> & `"$backendPy`" -m pip install imageio-ffmpeg" }
}

Say "`n=== 2. Ollama (required) ===" Cyan
$ollamaBase = if ($env:STORYWRITER_OLLAMA) { $env:STORYWRITER_OLLAMA } else { "http://localhost:11434" }
try {
    $tags = (Invoke-RestMethod -Uri "$ollamaBase/api/tags" -TimeoutSec 4).models | ForEach-Object { $_.name }
    if ($tags) {
        $hit = $tags | Where-Object { $_ -eq $Model -or ($_ -split ':')[0] -eq ($Model -split ':')[0] }
        if ($hit) { Good "model '$Model' present" }
        else { Bad "model '$Model' NOT pulled -> ollama pull $Model   (installed: $($tags -join ', '))" }
    } else { Warn "Ollama up but no models installed -> ollama pull $Model" }
} catch {
    Bad "Ollama not reachable at $ollamaBase -> start it (ollama serve) and: ollama pull $Model"
}

Say "`n=== 3. MongoDB (optional — opening-page style exemplars only) ===" Cyan
$mongoUp = $false
try {
    $probe = & $backendPy -c "from pymongo import MongoClient; MongoClient('mongodb://localhost:27017',serverSelectionTimeoutMS=2500).admin.command('ping'); print('mongo-ok')" 2>&1
    if ($probe -match 'mongo-ok') { $mongoUp = $true; Good "mongod reachable" }
    else { Warn "mongod not reachable — generation still works; openings disabled" }
} catch { Warn "mongod not reachable — generation still works; openings disabled" }

if (-not $ok) {
    Say "`nHard checks failed. Fix the FAILs above, then re-run." Red
    exit 1
}

Say "`n=== 4. Launch ===" Cyan
Say "Freeing :80 and :8000…"
Free-Port 80
Free-Port 8000

if ($Foreground) {
    Say "Starting backend server.py in the FOREGROUND (Ctrl-C to stop)…" Yellow
    Set-Location $root
    & $backendPy server.py
    exit 0
}

if (Test-Path "$portfolio\start-gateway.vbs") {
    Say "Starting gateway  app.py    -> :80    (3.14, hidden via start-gateway.vbs)"
    Start-Process "wscript.exe" -ArgumentList "`"$portfolio\start-gateway.vbs`""
} else {
    Warn "start-gateway.vbs not found — skipping the :80 gateway; backend still serves :8000 standalone."
}

Say "Starting backend  server.py -> :8000  ($backendPyw)"
Start-Process $backendPyw -ArgumentList 'server.py' -WorkingDirectory $root -WindowStyle Hidden

Say "`n=== 5. Health ===" Cyan
Start-Sleep -Seconds 4
$g = Listening 80
$b = Listening 8000
if ($g) { Good "gateway  :80    UP" } else { Warn "gateway  :80    DOWN (standalone :8000 still fine)" }
if ($b) { Good "backend  :8000  UP" } else { Bad  "backend  :8000  DOWN" }

if ($b) {
    $url = if ($g) { "http://localhost/storywriter" } else { "http://127.0.0.1:8000" }
    Say "`nRunning → $url" Green
    if (-not $NoOpen) { Start-Process $url }
} else {
    Say "`nBackend didn't bind. Run it in the foreground to see the error:" Yellow
    Say "    .\run-storywriter.ps1 -Foreground"
    exit 1
}

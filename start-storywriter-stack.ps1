# start-storywriter-stack.ps1 — start BOTH StoryWriter processes in the background.
#   gateway   app.py     -> :80     (front door, proxies /storywriter)
#   backend   server.py  -> :8000   (audio extraction + model-driven generation)
# Launched with pythonw (no console window) and detached, so they keep running after
# this shell closes.
#
#   powershell -ExecutionPolicy Bypass -File .\start-storywriter-stack.ps1

$ErrorActionPreference = 'SilentlyContinue'

$portfolio = "C:\Projects\GithubRoot\Portfolio"
$root      = "C:\Projects\GithubRoot\Portfolio\StoryWriter"

# server.py MUST run on the 3.12 that has pymongo + librosa + soundfile + numpy,
# because the generator inherits this interpreter.
$backendPy = "C:\Program Files\Python312\pythonw.exe"

# Gateway runs on your 3.14 — it's the front door for the wider set of apps.
# NOTE: use python.exe, NOT pythonw.exe — this pythoncore build's pythonw is broken
# (python.exe runs app.py fine). The -WindowStyle Hidden below keeps it windowless.
# Backend stays on 3.12 (pymongo + librosa live there).
$gatewayPy = "C:\Users\Jay\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $gatewayPy)) { $gatewayPy = $backendPy }

function Free-Port($port){
    Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
    for ($i = 0; $i -lt 20; $i++){
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 250
    }
}
function Listening($port){ [bool](Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue) }

Write-Host "Freeing :80 and :8000…"
Free-Port 80
Free-Port 8000

Write-Host "Starting gateway  app.py    -> :80   (3.14, hidden via start-gateway.vbs)"
# This pythoncore build's pythonw is broken and Start-Process -WindowStyle Hidden on
# its python.exe dies, so launch the gateway through a .vbs (no window, detached) —
# the same reliable trick as start-ngrok.vbs.
Start-Process "wscript.exe" -ArgumentList "`"$portfolio\start-gateway.vbs`""

Write-Host "Starting backend  server.py -> :8000  ($backendPy)"
Start-Process $backendPy -ArgumentList 'server.py' -WorkingDirectory $root      -WindowStyle Hidden

Start-Sleep -Seconds 4
$g = Listening 80
$b = Listening 8000
if ($g) { Write-Host "  gateway  :80    UP"   -ForegroundColor Green } else { Write-Host "  gateway  :80    DOWN" -ForegroundColor Red }
if ($b) { Write-Host "  backend  :8000  UP"   -ForegroundColor Green } else { Write-Host "  backend  :8000  DOWN" -ForegroundColor Red }

if ($g -and $b) {
    Write-Host "`nBoth running in the background → http://localhost/storywriter" -ForegroundColor Green
} else {
    Write-Host "`nSomething didn't bind. Run the failed one in the FOREGROUND to see the error:" -ForegroundColor Yellow
    if (-not $g) { Write-Host ("    cd $portfolio ; & `"" + ($gatewayPy -replace 'pythonw\.exe','python.exe') + "`" app.py") }
    if (-not $b) { Write-Host ("    cd $root ; & `"" + ($backendPy -replace 'pythonw\.exe','python.exe') + "`" server.py") }
}

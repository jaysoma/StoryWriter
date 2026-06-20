# restart-storywriter.ps1 — stop whatever holds :8000, relaunch the StoryWriter backend hidden.
#   Right-click → "Run with PowerShell", or:  powershell -ExecutionPolicy Bypass -File .\restart-storywriter.ps1
$ErrorActionPreference = 'SilentlyContinue'
$root = "C:\Projects\GithubRoot\Portfolio\StoryWriter"
$py   = "C:\Program Files\Python312\pythonw.exe"   # the interpreter StoryWriter runs on

# Kill the current listener on 8000 (the old server.py), if any.
$pids = Get-NetTCPConnection -LocalPort 8000 -State Listen |
        Select-Object -ExpandProperty OwningProcess -Unique
foreach ($p in $pids) { Stop-Process -Id $p -Force }

Start-Sleep -Milliseconds 400
Start-Process $py -ArgumentList 'server.py' -WorkingDirectory $root
Write-Host "StoryWriter restarted -> http://127.0.0.1:8000  (behind the gateway at /storywriter)"

# Needs in this Python 3.12: numpy + imageio-ffmpeg (audio extraction) and a running
# Ollama model (qwen2.5:7b). pymongo + mongod are optional (opening-page exemplars only).
#
# Debugging? swap the pythonw line for python.exe with logs:
#   Start-Process "C:\Program Files\Python312\python.exe" -ArgumentList 'server.py' -WindowStyle Hidden `
#     -WorkingDirectory $root -RedirectStandardOutput "$root\server.log" -RedirectStandardError "$root\server.err"

# demo-prep.ps1 — one-shot "make the next run fast" prep for StoryWriter.
# Frees RAM, restarts the backend clean, warms librosa while cutting a short
# clip, pre-warms the model, and prints what to upload.
#
#   powershell -ExecutionPolicy Bypass -File .\demo-prep.ps1
#   powershell -ExecutionPolicy Bypass -File .\demo-prep.ps1 "C:\Music\song.mp3"
param([string]$Source)

$ErrorActionPreference = 'SilentlyContinue'
$root = "C:\Projects\GithubRoot\Portfolio\StoryWriter"
$py   = "C:\Program Files\Python312\python.exe"
$pyw  = "C:\Program Files\Python312\pythonw.exe"
Set-Location $root

Write-Host "[1/5] Freeing RAM (unloading idle Ollama models)..." -ForegroundColor Cyan
foreach ($m in 'qwen2.5:3b','qwen2.5:latest','llama3.1:latest','codellama:latest','mistral:latest','llama2:latest') {
    ollama stop $m 2>$null
}

Write-Host "[2/5] Restarting backend clean (clears any stuck jobs)..." -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep -Milliseconds 700
Start-Process $pyw -ArgumentList 'server.py' -WorkingDirectory $root

Write-Host "[3/5] Warming librosa + cutting a 45s demo clip (the one-time slow step)..." -ForegroundColor Cyan
if ($Source) { & $py .\make_clip.py $Source 45 } else { & $py .\make_clip.py }

Write-Host "[4/5] Pre-warming llama3.2:3b into RAM..." -ForegroundColor Cyan
ollama run llama3.2:3b "ready" 2>$null | Out-Null

Write-Host "[5/5] Status:" -ForegroundColor Cyan
$b = [bool](Get-NetTCPConnection -LocalPort 8000 -State Listen)
$g = [bool](Get-NetTCPConnection -LocalPort 80   -State Listen)
Write-Host ("  backend :8000  {0}" -f $(if ($b) {'UP'} else {'DOWN'}))
Write-Host ("  gateway :80    {0}" -f $(if ($g) {'UP'} else {'DOWN'}))
ollama ps
Write-Host ""
Write-Host "READY -> open http://localhost/storywriter, hard-refresh (Ctrl+Shift+R), then upload:" -ForegroundColor Green
Write-Host "        $root\demo_clip.wav" -ForegroundColor Green

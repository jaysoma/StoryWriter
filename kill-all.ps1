# kill-all.ps1 — stop EVERYTHING StoryWriter is running (backend, gateway, extractors,
# generators, orphans) and free its ports + unload Ollama models. Clean slate.
#   powershell -ExecutionPolicy Bypass -File .\kill-all.ps1
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "Killing StoryWriter processes..." -ForegroundColor Yellow

# 1. free ports 80 (gateway) and 8000 (backend) by killing their listeners
foreach ($port in 80, 8000) {
    Get-NetTCPConnection -LocalPort $port -State Listen |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
}

# 2. kill every python / pythonw — backend, gateway, extraction, generation, orphans
Get-Process python, pythonw | Stop-Process -Force

# 3. unload Ollama models + stop its runner (Ollama relaunches itself on next call)
Get-Process ollama, "ollama app", ollama_llama_server | Stop-Process -Force

Start-Sleep -Seconds 1

# 4. report what (if anything) survived
Write-Host "`nRemaining python/ollama processes (want none):" -ForegroundColor Yellow
Get-Process python, pythonw, ollama, ollama_llama_server -EA SilentlyContinue |
    Select-Object Id, ProcessName, CPU | Format-Table -Auto
Write-Host "Listeners on 80/8000 (want none):" -ForegroundColor Yellow
Get-NetTCPConnection -LocalPort 80, 8000 -State Listen -EA SilentlyContinue |
    Select-Object LocalPort, OwningProcess | Format-Table -Auto
Write-Host "Clean slate." -ForegroundColor Green

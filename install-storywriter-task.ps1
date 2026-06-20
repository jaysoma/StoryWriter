# install-storywriter-task.ps1 — register a boot task that auto-starts the StoryWriter
# backend on :8000, mirroring the existing PortfolioApp / PortfolioNgrok tasks.
#
# RUN ONCE, in an ELEVATED (Administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\install-storywriter-task.ps1
#
# Remove later:  Unregister-ScheduledTask -TaskName "PortfolioStoryWriter" -Confirm:$false

$root = "C:\Projects\GithubRoot\Portfolio\StoryWriter"
$py   = "C:\Program Files\Python312\pythonw.exe"   # no console, no logs (like the gateway)

$action  = New-ScheduledTaskAction -Execute $py -Argument 'server.py' -WorkingDirectory $root

# Fire ~10s after boot — after the gateway/ngrok 5s stagger so the front door is up first.
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT10S'

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
             -LogonType S4U -RunLevel Limited

$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -StartWhenAvailable `
             -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "PortfolioStoryWriter" -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings `
  -Description "StoryWriter audio->story backend on :8000 (behind the gateway /storywriter)" -Force

Write-Host "Registered scheduled task 'PortfolioStoryWriter'. Starts server.py ~10s after each boot."
Write-Host "Prereqs: numpy + imageio-ffmpeg in this Python 3.12, and a running Ollama"
Write-Host "         model (e.g. qwen2.5:7b). MongoDB is optional (opening-page exemplars)."
Write-Host "Start it now:  Start-ScheduledTask -TaskName 'PortfolioStoryWriter'"

<#
  verify-storywriter.ps1 — run StoryWriter's self-test with the SAME Python the
  backend uses (3.12), because that is where the deps (pymongo, numpy, ffmpeg)
  must live. Use this after any code change instead of trusting the agent's sandbox.

    .\verify-storywriter.ps1            # compile + imports + Mongo/Ollama checks
    .\verify-storywriter.ps1 -Smoke     # ALSO generate a real story end-to-end
    .\verify-storywriter.ps1 -Model "llama3.1:8b" -Smoke
#>
param(
  [switch]$Smoke,
  [string]$Model = "qwen2.5:7b"
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$py = "C:\Program Files\Python312\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "Python 3.12 not found at '$py' - falling back to 'python' on PATH." -ForegroundColor Yellow
  $py = "python"
}

$cliArgs = @((Join-Path $here "selftest.py"), "--model", $Model)
if ($Smoke) { $cliArgs += "--smoke" }

& $py @cliArgs
exit $LASTEXITCODE

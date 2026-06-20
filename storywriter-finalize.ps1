# storywriter-finalize.ps1 — finish the StoryWriter consolidation and stand it up.
#
#   powershell -ExecutionPolicy Bypass -File .\storywriter-finalize.ps1
#
# Idempotent: safe to run more than once. It removes the leftover resonator\ folder
# and dead files, syntax-checks the Python, installs deps, checks MongoDB (optional)
# and Ollama, and restarts both the backend (:8000) and the gateway (:80).

$ErrorActionPreference = 'Continue'
$root      = "C:\Projects\GithubRoot\Portfolio\StoryWriter"
$portfolio = "C:\Projects\GithubRoot\Portfolio"
$py  = "C:\Program Files\Python312\python.exe"
$pyw = "C:\Program Files\Python312\pythonw.exe"

function Step($m){ Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m){ Write-Host "  $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  $m" -ForegroundColor Yellow }
function Bad($m){ Write-Host "  $m" -ForegroundColor Red }

Set-Location $root

# 1 ── remove the old structure ───────────────────────────────────────────────
Step "Cleaning up the old structure"
if (Test-Path "$root\resonator") {
    Remove-Item "$root\resonator" -Recurse -Force
    Ok "removed resonator\"
} else { Ok "no resonator\ folder (already gone)" }
foreach ($f in 'dashboard.py','dashboard.html','_probe_host.txt','_probe_mount.txt') {
    if (Test-Path "$root\$f") { Remove-Item "$root\$f" -Force; Ok "removed $f" }
}

# 2 ── confirm the flat layout ────────────────────────────────────────────────
Step "Checking the flat layout"
$need = 'index.html','server.py','story_generator.py','extract_arcs_hpss.py'
$missing = $need | Where-Object { -not (Test-Path "$root\$_") }
if ($missing) { Bad ("MISSING: " + ($missing -join ', ')) } else { Ok "all expected files present" }

# 3 ── syntax-check the Python (on the real interpreter) ──────────────────────
Step "Compiling the Python"
& $py -m py_compile server.py story_generator.py extract_arcs_hpss.py
if ($LASTEXITCODE -eq 0) { Ok "python compiles clean" } else { Bad "python failed to compile (see above)"; }

# 4 ── dependencies in this interpreter ───────────────────────────────────────
Step "Installing Python dependencies"
& $py -m pip install --quiet --disable-pip-version-check pymongo numpy imageio-ffmpeg
if ($LASTEXITCODE -eq 0) { Ok "deps installed / up to date" } else { Warn "pip reported a problem (see above)" }

# 5 ── MongoDB (optional — opening-page style exemplars only) ─────────────────
Step "Checking MongoDB (optional)"
$ok5 = & $py -c "from pymongo import MongoClient; MongoClient('mongodb://localhost:27017/',serverSelectionTimeoutMS=4000).admin.command('ping'); print('ok')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Warn "MongoDB not reachable on :27017 — generation still works; opening-page exemplars disabled."
} else { Ok "mongod reachable (opening-page exemplars available via build_openings.py)" }

# 6 ── Ollama model ───────────────────────────────────────────────────────────
Step "Checking Ollama"
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 4
    Ok ("models: " + (($tags.models | ForEach-Object { $_.name }) -join ', '))
    Warn "any capable model works (qwen2.5, llama3.1/3.2, mistral-nemo)."
} catch { Warn "Ollama not reachable on :11434 — start it, then: ollama pull qwen2.5:7b" }

# 7 ── restart the backend (:8000) ────────────────────────────────────────────
Step "Restarting the StoryWriter backend (:8000)"
Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
Start-Sleep -Milliseconds 400
Start-Process $pyw -ArgumentList 'server.py' -WorkingDirectory $root
Ok "server.py started"

# 8 ── restart the gateway (:80) so the new /storywriter route takes effect ───
Step "Restarting the gateway (:80) for the /storywriter route"
Get-NetTCPConnection -LocalPort 80 -State Listen -EA SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
# Wait for the socket to actually release before rebinding — otherwise the new
# process loses the race and :80 is left half-open (a churning, non-serving port).
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort 80 -State Listen -EA SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}
Start-Process $pyw -ArgumentList 'app.py' -WorkingDirectory $portfolio
Start-Sleep -Seconds 2
if (Get-NetTCPConnection -LocalPort 80 -State Listen -EA SilentlyContinue) {
    Ok "gateway is listening on :80"
} else {
    Bad "gateway did NOT come up — run it in the foreground to see the error:"
    Write-Host "    cd $portfolio ; & `"$py`" app.py"
}

Step "Done"
Write-Host "Open  http://localhost/storywriter   (gateway)  or  http://localhost:8000  (standalone)."
Write-Host "Public URL path is now /storywriter (also accepts /StoryWriter)."

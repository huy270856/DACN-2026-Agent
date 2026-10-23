# Windows integration smoke tests for DACN-2026-Agent / Context Collector v1
# Run from the repository root after .\setup.cmd
param([switch]$IncludeLargeFile)
$ErrorActionPreference = "Stop"
$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$collector = Join-Path (Get-Location) "context_collector.py"
$work = Join-Path (Get-Location) "windows-tests"
$out = Join-Path $work "collections"
New-Item -ItemType Directory -Force -Path $out | Out-Null
if (-not (Test-Path $py) -or -not (Test-Path $collector)) {
    throw "Run this script from repository root after .\setup.cmd"
}
$script:passed = 0; $script:failed = 0
function Check([bool]$ok, [string]$label, [string]$detail = "") {
    if ($ok) { $script:passed++; Write-Host "[PASS] $label" -ForegroundColor Green }
    else { $script:failed++; Write-Host "[FAIL] $label $detail" -ForegroundColor Red }
}
function Collect([string]$kind, [string]$target) {
    $lines = & $py $collector "--$kind" $target --output $out 2>&1
    $exit = $LASTEXITCODE
    $raw = ($lines | Out-String)
    try { $result = $raw | ConvertFrom-Json -ErrorAction Stop }
    catch { throw "Collector did not output valid JSON (exit=$exit): $raw" }
    if (-not (Test-Path $result.context_path)) { throw "Missing context: $($result.context_path)" }
    return (Get-Content $result.context_path -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function ValueOf($ctx, [string]$facet) {
    return $ctx.facets.$facet.value
}

Write-Host "`n=== Windows Context Collector Integration Tests ==="
# 1: Plain text and SHA256 comparison
$file = Join-Path $work "sample.txt"
[System.IO.File]::WriteAllText($file, "DACN Windows integration test")
$c = Collect "file" $file
$expected = (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant()
Check ($c.facets.sha256.status -eq "SUCCESS" -and (ValueOf $c "sha256") -eq $expected) "SHA256 matches Windows Get-FileHash"
Check ($c.facets.pe_header.status -eq "SUCCESS" -and $c.facets.pe_header.value.is_pe -eq $false) "Text is not PE"
Check ($c.facets.metadata.value.size_bytes -eq (Get-Item $file).Length) "File size matches"

# 2: Windows PE
$exe = Join-Path $env:WINDIR "System32\notepad.exe"
if (Test-Path $exe) {
    $c = Collect "file" $exe
    Check ($c.facets.pe_header.status -eq "SUCCESS" -and $c.facets.pe_header.value.is_pe -eq $true) "Windows Notepad PE recognized"
    Check ((ValueOf $c "sha256") -eq (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()) "Notepad hash matches Windows"
}

# 3: Missing file must not crash or invent hash
$missing = Join-Path $work ("does-not-exist-" + [guid]::NewGuid().ToString() + ".exe")
$c = Collect "file" $missing
Check ($c.status -eq "FAILED" -and $null -eq $c.facets.sha256) "Missing file fails safely"

# 4: Stable, controlled process (avoid Notepad single-instance / handoff behavior)
$sleeper = Join-Path $work "collector_sleeper.py"
[System.IO.File]::WriteAllText($sleeper, "import time`ntime.sleep(30)`n")
$proc = Start-Process -FilePath $py -ArgumentList @($sleeper) -PassThru
try {
    Start-Sleep -Milliseconds 900
    $proc.Refresh()
    if ($proc.HasExited) { throw "Test fixture exited unexpectedly: PID $($proc.Id)" }
    $c = Collect "pid" ([string]$proc.Id)
    Check ($c.target.pid -eq $proc.Id -and $c.facets.start_time.status -eq "SUCCESS") "Live PID identity and start time"
    $win = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue
    if ($win) {
        Check ($c.facets.parent_pid.value -eq $win.ParentProcessId) "Parent PID matches CIM"
        Check ($c.facets.session_id.value -eq $win.SessionId) "Session ID matches CIM"
    } else { Write-Host "[SKIP] CIM could not retrieve process" -ForegroundColor Yellow }
    Check ($null -ne $c.backing_file_context -and $c.facets.executable_path.status -eq "SUCCESS") "Backing file context present"
    Check ($c.facets.process_identity_still_present.status -eq "SUCCESS" -and $c.facets.process_identity_still_present.value -eq $true) "Process identity remains stable"
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    try { $proc.WaitForExit(3000) | Out-Null } catch {}
}

# 5: Exited process, using controlled sleeper fixture
$proc2 = Start-Process -FilePath $py -ArgumentList @($sleeper) -PassThru
$deadPid = $proc2.Id
Stop-Process -Id $deadPid -Force -ErrorAction SilentlyContinue
try { $proc2.WaitForExit(3000) | Out-Null } catch {}
Start-Sleep -Milliseconds 500
if (-not (Get-Process -Id $deadPid -ErrorAction SilentlyContinue)) {
    $c = Collect "pid" ([string]$deadPid)
    Check ($c.status -eq "FAILED" -and @($c.errors | ForEach-Object { $_.code }) -contains "process_not_found") "Exited PID returns process_not_found"
} else { Write-Host "[SKIP] PID reused before check" -ForegroundColor Yellow }

# 6: System process (may be protected or partially accessible)
$c = Collect "pid" "4"
Check ($c.target.pid -eq 4 -and $c.status -in @("SUCCESS","DEGRADED","FAILED")) "PID 4 handled without crash"

# 7: Optional large file - 256 MiB, not multiple GB by default
if ($IncludeLargeFile) {
    $large = Join-Path $work "large-256MiB.bin"
    $stream = [System.IO.File]::Create($large)
    try { $stream.SetLength(256MB) } finally { $stream.Dispose() }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $c = Collect "file" $large
    $timer.Stop()
    Check ((ValueOf $c "sha256") -eq (Get-FileHash $large -Algorithm SHA256).Hash.ToLowerInvariant()) "256 MiB hash matches"
    Write-Host ("Large-file elapsed: {0:N2}s" -f $timer.Elapsed.TotalSeconds)
}
Write-Host "`nResults: $script:passed PASS / $script:failed FAIL"
Write-Host "Evidence JSON: $out"
if ($script:failed -gt 0) { exit 1 } else { exit 0 }

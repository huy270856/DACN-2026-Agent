param(
    [Parameter(Mandatory=$true)][string]$GhidraHome,
    [Parameter(Mandatory=$true)][string]$JavaHome
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$manifest = Get-Content (Join-Path $root 'build/manifest.json') -Raw | ConvertFrom-Json
$sample = $manifest.samples | Where-Object id -eq 'hello'
$binary = Join-Path $root $sample.binary
if ((Get-FileHash -LiteralPath $binary).Hash.ToLower() -ne $sample.binary_sha256) { throw 'Binary SHA256 mismatch' }
$launcher = Join-Path (Resolve-Path $GhidraHome).Path 'support/analyzeHeadless.bat'
$jdk = (Resolve-Path $JavaHome).Path
$out = Join-Path $root 'build/ghidra'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$project = 'hello_' + [guid]::NewGuid().ToString('N')
# Stage under an ASCII path: the Windows Java/batch launcher fails on this machine's accented workspace path.
$stage = Join-Path ([IO.Path]::GetTempPath()) "dacn-$project"
if ($stage -match '[^\x00-\x7F]' -or $launcher -match '[^\x00-\x7F]' -or $jdk -match '[^\x00-\x7F]') {
    throw 'Use ASCII-only Ghidra/JDK/TEMP paths for this Windows launcher.'
}
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath $binary -Destination (Join-Path $stage 'hello.exe')
Copy-Item -LiteralPath (Join-Path $root 'ghidra/ExportEvidence.java') -Destination $stage
$evidence = Join-Path $stage "$project.json"
$log = Join-Path $stage "$project.log"
$oldJava = $env:JAVA_HOME
$oldPath = $env:PATH
$oldOptions = $env:GHIDRA_HEADLESS_JAVA_OPTIONS
try {
    $env:JAVA_HOME = $jdk
    $env:PATH = (Join-Path $jdk 'bin') + ';' + $oldPath
    $env:GHIDRA_HEADLESS_JAVA_OPTIONS = "-Dapplication.settingsdir=$stage/settings -Dapplication.cachedir=$stage/cache"
    & $launcher $stage $project -import (Join-Path $stage 'hello.exe') -scriptPath $stage -postScript ExportEvidence.java $evidence -analysisTimeoutPerFile 180 -max-cpu 2 -log $log -deleteProject
    if ($LASTEXITCODE -ne 0) { throw "Ghidra failed: $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $evidence)) { throw 'No evidence exported; inspect Ghidra log' }
    $result = Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
    if ($result.analysis_timed_out) { throw 'Ghidra analysis timed out; evidence is partial' }
    if ($result.binary_sha256 -ne $sample.binary_sha256) { throw 'Evidence target hash mismatch' }
    Copy-Item -LiteralPath $evidence -Destination (Join-Path $out 'hello-evidence.json')
    Copy-Item -LiteralPath $log -Destination (Join-Path $out 'hello-headless.log')
    Write-Output "Evidence/log: $out"
    Write-Output "Temporary staging retained for diagnosis: $stage"
} finally {
    $env:JAVA_HOME = $oldJava
    $env:PATH = $oldPath
    $env:GHIDRA_HEADLESS_JAVA_OPTIONS = $oldOptions
}

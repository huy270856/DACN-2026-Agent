# TASK 07B S8 — frozen live run (Owner runs this in a SEPARATE PowerShell window, outside Claude).
# Prerequisites: Ollama 0.40.16 headless (`ollama serve`) on 127.0.0.1:11434; desktop app quit;
# repository at the pre-run freeze commit; Python 3.12 on PATH.
# Run ONLY after the pre-run freeze commit. Owner-approved S8 authorization: DACN_OWNER_07B_EVAL_GO
# Usage:  powershell -ExecutionPolicy Bypass -File evaluation\task07b\run_s8.ps1
param([string]$AuthorizedBy = "DACN_OWNER_07B_EVAL_GO")
$ErrorActionPreference = "Continue"  # native stderr must not abort (PS 5.1); exit codes are checked explicitly
Set-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$manifest = "evaluation\task07b\results\cohort\cases_v2_EVALUATOR_ONLY.json"
$root = "evaluation\task07b\results\frozen"
New-Item -ItemType Directory -Force $root | Out-Null
$log = Join-Path $root "run_stdout.txt"
$version = (Invoke-RestMethod http://127.0.0.1:11434/api/version).version
if ($version -ne "0.40.16") { throw "Ollama version $version is not 0.40.16" }
foreach ($spec in @("BASE:42", "V4_NOQ:42", "V4:42", "BASE:7", "V4_NOQ:7", "V4:7")) {
    $arm, $seed = $spec.Split(":")
    $out = Join-Path $root "$($arm)_s$seed"
    "=== $(Get-Date -Format o) $arm s$seed" | Tee-Object -FilePath $log -Append
    if (-not (Test-Path (Join-Path $out "arm.json"))) {
        python -m evaluation.task07b.harness prepare --arm $arm --seed $seed --out $out --manifest $manifest --kind DEV_EVALUATION_FRESH_COHORT 2>&1 | Tee-Object -FilePath $log -Append
        if ($LASTEXITCODE -ne 0) { throw "prepare failed: $arm s$seed" }
    }
    python -m evaluation.task07b.harness run --out $out --authorized-by $AuthorizedBy 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw "run failed: $arm s$seed (see $log); do NOT re-prepare this directory" }
}
"=== ALL_DONE $(Get-Date -Format o)" | Tee-Object -FilePath $log -Append

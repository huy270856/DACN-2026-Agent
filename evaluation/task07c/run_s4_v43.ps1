# TASK 07C S4 (rev 3, V4_3) — frozen live run (Owner runs this in a SEPARATE PowerShell window, outside Claude).
# Prerequisites: Ollama 0.40.16 headless (`ollama serve`) on 127.0.0.1:11434; desktop app quit;
# repository checked out AT the pre-run freeze commit with a clean tracked tree; Python 3.12 on PATH.
# Owner-approved S4 authorization: DACN_OWNER_07C_EVAL_GO
# Usage:  powershell -ExecutionPolicy Bypass -File evaluation\task07c\run_s4_v43.ps1 -FreezeCommit <40-hex SHA of the freeze commit>
# Stopping rules (PROTOCOL §6): any guard/drift/prepare/run failure stops the WHOLE script (no later arm runs).
# Re-running the script resumes: existing run directories are not re-prepared and finished cases are skipped.
param([Parameter(Mandatory = $true)][string]$FreezeCommit,
      [string]$AuthorizedBy = "DACN_OWNER_07C_EVAL_GO")
$ErrorActionPreference = "Continue"  # native stderr must not abort (PS 5.1); exit codes are checked explicitly
Set-Location (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

# --- guards (review Medium-1, High-2) ---------------------------------------------------------
$head = (git rev-parse HEAD).Trim()
if ($head -ne $FreezeCommit) { throw "HEAD $head is not the freeze commit $FreezeCommit" }
$dirty = git status --porcelain --untracked-files=no
if ($dirty) { throw "Tracked files modified; refuse to run on a non-frozen tree:`n$dirty" }
$expectedDigest = "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
$version = (Invoke-RestMethod http://127.0.0.1:11434/api/version).version
if ($version -ne "0.40.16") { throw "Ollama version $version is not 0.40.16" }
$model = (Invoke-RestMethod http://127.0.0.1:11434/api/tags).models | Where-Object { $_.name -eq "qwen3.5:4b" }
if (-not $model -or $model.digest -ne $expectedDigest) { throw "qwen3.5:4b digest is not the PROTOCOL digest $expectedDigest" }

$manifest = "evaluation\task07b\results\cohort\cases_v2_EVALUATOR_ONLY.json"
$root = "evaluation\task07c\results\frozen_v43"
New-Item -ItemType Directory -Force $root | Out-Null
$log = Join-Path $root "run_stdout.txt"
"=== $(Get-Date -Format o) START freeze=$FreezeCommit ollama=$version digest=$($model.digest)" | Tee-Object -FilePath $log -Append
foreach ($spec in @("V4_3:42", "V4_3:7")) {
    $arm, $seed = $spec.Split(":")
    $out = Join-Path $root "$($arm)_s$seed"
    "=== $(Get-Date -Format o) $arm s$seed" | Tee-Object -FilePath $log -Append
    if (-not (Test-Path (Join-Path $out "arm.json"))) {
        python -m evaluation.task07b.harness prepare --arm $arm --seed $seed --out $out --manifest $manifest --kind DEV_DIAGNOSTIC_CONSUMED_COHORT 2>&1 | Tee-Object -FilePath $log -Append
        if ($LASTEXITCODE -ne 0) { throw "prepare failed: $arm s$seed (see $log). Report to Planner; do not delete or re-prepare $out" }
    }
    python -m evaluation.task07b.harness run --out $out --authorized-by $AuthorizedBy 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { throw "run stopped: $arm s$seed (see $log). Report to Planner; do NOT re-prepare $out" }
}
"=== ALL_DONE $(Get-Date -Format o)" | Tee-Object -FilePath $log -Append

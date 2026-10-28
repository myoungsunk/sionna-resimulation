# Runs only Stage 2 cached statistics, Stage 3 population factorial,
# and Stage 5 independent Fisher verification. Never reruns Stage 1/4/6.
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$CodeRoot,
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [Parameter(Mandatory=$true)][string]$ArtifactsRoot,
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [ValidateSet('preflight','2','3','5','all')][string]$Step='all'
)
$ErrorActionPreference = 'Stop'
$Runner = Join-Path $CodeRoot 'run_selective.py'
if (-not (Test-Path -LiteralPath $Runner)) { throw "Missing patched runner: $Runner. Run APPLY_PATCH first." }
& python $Runner --repo-root $RepoRoot --source-root $SourceRoot `
  --artifacts-root $ArtifactsRoot --output-root $OutputRoot --step $Step
if ($LASTEXITCODE -ne 0) { throw "STAGE $Step HARD STOP (exit=$LASTEXITCODE); do not publish outputs." }
Write-Host "[PASS] Selected Stage $Step completed."

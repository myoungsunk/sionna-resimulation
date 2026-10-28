# One-shot guarded workflow. A failed prerequisite stops all subsequent steps.
# All destinations must be new and OUTSIDE the original Git checkout.
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$CodeOut,
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [Parameter(Mandatory=$true)][string]$ArtifactsRoot,
  [Parameter(Mandatory=$true)][string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'APPLY_PATCH.ps1') -RepoRoot $RepoRoot -CodeOut $CodeOut
if ($LASTEXITCODE -ne 0) { throw 'Patch apply failed' }
& (Join-Path $PSScriptRoot 'RUN_VALIDATION.ps1') -RepoRoot $RepoRoot -CodeRoot $CodeOut `
  -SourceRoot $SourceRoot -ArtifactsRoot $ArtifactsRoot -OutputRoot $OutputRoot -Step preflight
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed' }
& (Join-Path $PSScriptRoot 'RUN_VALIDATION.ps1') -RepoRoot $RepoRoot -CodeRoot $CodeOut `
  -SourceRoot $SourceRoot -ArtifactsRoot $ArtifactsRoot -OutputRoot $OutputRoot -Step all
if ($LASTEXITCODE -ne 0) { throw 'Execution failed' }
$Verdict = Join-Path $OutputRoot 'PATCH_V2_FINAL.json'
if (-not (Test-Path -LiteralPath $Verdict)) { throw 'PATCH_V2_FINAL.json missing; no scientific evaluation' }
$FinalRecord = Get-Content -LiteralPath $Verdict -Raw | ConvertFrom-Json
if ($FinalRecord.status -ne 'TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION' -or (($FinalRecord.completed_steps -join ',') -ne '2,3,5')) { throw 'Incomplete final verdict' }
Write-Host '[COMPLETE] Technical QA report: ' $Verdict

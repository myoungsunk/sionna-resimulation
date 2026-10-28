param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$ArtifactsRoot,
    [Parameter(Mandatory=$true)][string]$OutputRoot
)
$ErrorActionPreference = 'Stop'
$CodeRoot = Join-Path $RepoRoot 'research\DS_RF_CAUSAL_STAGE7_8_V1_20261028\code'
python (Join-Path $PSScriptRoot 'ds_info_audit.py') --mode real `
    --repo-root $RepoRoot --source-root $SourceRoot `
    --artifacts-root $ArtifactsRoot --code-root $CodeRoot --output-root $OutputRoot
if($LASTEXITCODE -ne 0) { throw "DS_INFO_REAL_FAILED (exit=$LASTEXITCODE)" }

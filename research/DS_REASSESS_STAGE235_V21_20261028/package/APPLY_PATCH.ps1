# Windows PowerShell 5.1+; run from the extracted ZIP folder.
# Copies the exact GitHub 450a21f code to a NEW external folder and applies the
# hash-locked patch THERE. Does not change git, old results or original sources.
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$CodeOut
)
$ErrorActionPreference = 'Stop'
$Runner = Join-Path $PSScriptRoot 'APPLY_PATCH.py'
& python $Runner --repo-root $RepoRoot --code-out $CodeOut
if ($LASTEXITCODE -ne 0) { throw "PATCH HARD STOP (exit=$LASTEXITCODE); see console error." }
Write-Host '[PASS] A separately patched code directory is ready.'

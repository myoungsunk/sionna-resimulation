<#
Run only on a clean folder after checkout EXACT commit 4d2414a.
Copies code; verifies; executes preflight, stage7, stage8, verify.
Does NOT modify the repository, old results, RF data, or trained models.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [Parameter(Mandatory=$true)][string]$ArtifactsRoot,
  [Parameter(Mandatory=$true)][string]$CodeOut,
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [string]$PythonExe = 'python',
  [string]$Cases = 'all',
  [string]$Biases = 'B0,L2'
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function RunPy([string[]]$ArgsArray) {
  & $PythonExe @ArgsArray
  if ($LASTEXITCODE -ne 0) { throw "PYTHON_EXIT_$LASTEXITCODE $($ArgsArray -join ' ')" }
}
if (Test-Path -LiteralPath $CodeOut) { throw "CodeOut must not exist: $CodeOut" }
if (Test-Path -LiteralPath $OutputRoot) { throw "OutputRoot must not exist: $OutputRoot" }
RunPy @((Join-Path $PSScriptRoot 'VERIFY_PACKAGE.py'))
RunPy @((Join-Path $PSScriptRoot 'APPLY_PATCH.py'),'--repo-root',$RepoRoot,'--code-out',$CodeOut)
$commonArgs=@('--repo-root',$RepoRoot,'--source-root',$SourceRoot,'--artifacts-root',$ArtifactsRoot,'--output-root',$OutputRoot,'--cases',$Cases,'--biases',$Biases)
RunPy (@((Join-Path $CodeOut 'run_causal.py')) + $commonArgs + @('--step','preflight'))
RunPy (@((Join-Path $CodeOut 'run_causal.py')) + $commonArgs + @('--step','all'))
RunPy (@((Join-Path $CodeOut 'run_causal.py')) + $commonArgs + @('--step','verify'))
Write-Host "TECHNICAL_QA completed. Read $OutputRoot\CAUSAL_FINAL_QA.json" -ForegroundColor Green

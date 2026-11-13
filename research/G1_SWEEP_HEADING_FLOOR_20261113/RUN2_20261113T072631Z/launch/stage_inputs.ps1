param([string]$Dest)
$ErrorActionPreference='Stop'
$inputs=Join-Path ([IO.Path]::GetTempPath()) 'g1-floor-inputs-e787e35b4b76/extracted'
$archive=Join-Path 'D:/codex/raytracing_modules/rt_cp_uwb/research/G1_SWEEP_HEADING_FLOOR_20261113/RUN2_20261113T072631Z' 'inputs.tar'
tar.exe -cf $archive -C $inputs .
if($LASTEXITCODE){exit $LASTEXITCODE}
scp -B -o ConnectTimeout=10 $archive "Snowball:$Dest/inputs.tar"
if($LASTEXITCODE){exit $LASTEXITCODE}
ssh -o BatchMode=yes -o ConnectTimeout=10 Snowball "tar -xf $Dest/inputs.tar -C $Dest/inputs"
exit $LASTEXITCODE

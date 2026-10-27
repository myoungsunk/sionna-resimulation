# Change these three paths to existing frozen inputs. OUTPUT must be a NEW folder
# OUTSIDE the Git checkout and original p2 snapshot.
$Repo = "D:\SLAM_bot\sionna-resimulation"
$Frozen = "D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849"
$Out = "D:\SLAM_bot\DS_REASSESS_RUN_20261027"
$Base = @('--repo-root',$Repo,'--source-root',"$Frozen\p2",'--artifacts-root',"$Frozen\p2_artifacts",'--output-root',$Out)

python -m pytest -q .\tests
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }
python .\run.py @Base --step preflight
if ($LASTEXITCODE -ne 0) { throw "Preflight failed" }
# Run one stage at a time, reviewing OUTPUT_SHA256 and RUN_STATUS before continuing.
foreach ($i in 1..6) {
    python .\run.py @Base --step "$i"
    if ($LASTEXITCODE -ne 0) { throw "Stage $i failed. Inspect RUN_FAILURE.json. Stop." }
}

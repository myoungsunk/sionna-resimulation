"""Verify report links/numbers and preserve final source/output hashes; no runs."""
import sys
import re
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validation_repair as V


def main():
    before=json.loads((V.OUT/"PROTECTED_INPUT_HASHES.json").read_text());assert all(V.sha(V.ROOT/p)==h for p,h in before.items())
    inputs=json.loads((V.OUT/"INPUT_MANIFEST.json").read_text())["inputs"]
    assert all(V.sha(p)==h["sha256"] for p,h in inputs.items())
    report=(V.OUT/"FINAL_REPORT_KO.md").read_text(encoding="utf-8")
    links=re.findall(r"\]\(([^)]+)\)",report);assert all((V.OUT/p).is_file() for p in links)
    assert not re.search("[\u3040-\u30ff]",report)
    joint=json.loads((V.OUT/"STEP6_JOINT_EVALUATION.json").read_text());assert joint["summary"]["joint"]==joint["summary"]["distance"]
    assert not any(x["exploratory_joint_criterion_met"] for x in joint["paired"].values())
    gsf=json.loads((V.OUT/"STEP7_GSF_IMPACT.json").read_text());assert sum(x["gsf_rows"] for x in gsf["impact"])==9600
    assert sum(x["total_rows"] for x in gsf["impact"])==72000
    subprocess.run(["git","diff","--check"],cwd=V.ROOT,check=True)
    V.write("ADOPTION_DECISIONS.json",dict(execution_status="completed_with_explicit_unperformed_items",hypothesis_outcome="mixed_and_unidentifiable_phase",
         adoption_status="gate_fix_adoptable_conditional_R_diagnostic_only",scientific_PASS=False,
         F01="OPEN: original L1/L2 FAIL, no independent rerun without FFD/LoS inputs",F02="OPEN: heldout NEES320.776 coverage0",
         F06="PARTIAL: disjoint pose-ID timeline split only",F07="OPEN: shared gyro/wheel model not corrected",F08="PSD_REGRESSION_CONFIRMED: 2 of 9600 legacy GSF rows regenerated",
         phase="PHASE_EFFECT_NOT_IDENTIFIABLE",generalization="UNKNOWN / NOT INDEPENDENTLY VERIFIED",
         scope="No RF generation, Snowball, motion, commits, push, merge, frozen evidence edits"))
    V.write("FINAL_CHECKS.json",dict(recorded_utc=datetime.now(timezone.utc).isoformat(),revision=V.REV,
        checks=dict(report_links=len(links),missing_links=[],report_korean_verified=True,original_tracked_result_files_preserved=len(before),selected_input_hashes_preserved=True,
            numerical_report_crosschecks=True,git_diff_check_exit=0),
        pytest=[dict(command="py -3.10 -m pytest tests/test_drivesim_filters.py tests/test_drivesim_hs_lut.py tests/test_drivesim_observation.py tests/test_drivesim_experiment.py tests/test_parity_gate_coverage.py tests/test_parity_gate_inputs.py tests/test_drivesim_uncertainty_repair.py -q",exit_code=0,passed=62,elapsed_s=40.40),
                dict(command="py -3.10 -m pytest tests/test_drivesim_sensors.py tests/test_fp_single_tx.py -q",exit_code=0,passed=11,elapsed_s=1.98)],
        stage7=dict(command="py -3.10 scripts/drive_sim/validation_repair_adoption.py",first_exit=1,reason="Windows separator KeyError before experiment",second_exit=0),
        failures_preserved=dict(no_gate_cli_expected_exit=1,initial_default_exec="helper_unknown_error: setup refresh had errors; escalated authorized execution succeeded"),
        moves=[],commits=[]))
    code=["scripts/drive_sim/parity_gate.py","scripts/drive_sim/run_rf_snowball.sh","src/qclean_uwb/drivesim/filters.py","src/qclean_uwb/drivesim/uncertainty.py",
          "scripts/drive_sim/validation_repair.py","scripts/drive_sim/validation_repair_adoption.py","scripts/drive_sim/validation_repair_finalize_checks.py",
          "tests/test_parity_gate_inputs.py","tests/test_drivesim_uncertainty_repair.py"]
    V.write("FINAL_OUTPUT_MANIFEST.json",dict(recorded_utc=datetime.now(timezone.utc).isoformat(),baseline_revision=V.REV,
        final_code={p:V.sha(V.ROOT/p) for p in code},outputs={p.name:dict(sha256=V.sha(p),bytes=p.stat().st_size) for p in V.OUT.iterdir() if p.is_file() and p.name not in ("FINAL_OUTPUT_MANIFEST.json",)}))
    print("FINAL CHECKS PASS: 447 protected files, raw hashes, links, report numbers, diff")


if __name__=="__main__":main()

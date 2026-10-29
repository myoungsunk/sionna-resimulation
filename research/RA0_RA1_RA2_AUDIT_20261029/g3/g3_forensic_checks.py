#!/usr/bin/env python3
"""G3 root-cause capability audit: preserves 'unknown' without archived per-ray tau."""
from __future__ import annotations
import json, pathlib, sys, urllib.request
import numpy as np
from qclean_uwb.drivesim.paths import _classes, TIE_S
BASE="https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/f100a983cc389fcdef073592a254add61e7115da/results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/S2/G3_continuity_"
CASES=("R2_aA","R2_aB","R4_aA","R4_aB","R5_aA","R5_aB")
def main():
  out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
  table={("short",):1e-8,("long",):1e-8+8e-14}
  classes,labels=_classes(table)
  synthetic_tau=table[("long",)]
  collapsed=float(np.min(np.abs(classes-synthetic_tau)))
  uncollapsed=float(min(abs(x-synthetic_tau) for x in table.values()))
  assert len(classes)==1 and uncollapsed==0 and 5e-14<collapsed<2e-13
  rows=[]
  for case in CASES:
    with urllib.request.urlopen(BASE+case+".json",timeout=60) as f: j=json.load(f)
    n=j["stations"];strict=j["unmatched_paths_total"]["tol_5e-14"];relaxed=j["unmatched_paths_total"]["tol_2e-13"]
    assert n>0 and strict>0 and relaxed==0 and not j["missing_traces"] and not j["status_not_ok"]
    rows.append({"case":case,"n_locations":n,"strict_unmatched_paths":strict,"relaxed_unmatched_paths":relaxed,"max_residual_s":j["max_residual_s"],"max_residual_equivalent_mm":j["max_residual_s"]*299792458*1000,"min_class_gap_s":j["min_gap_between_distinct_image_delays_s"]})
  assert len(rows)==6 and sum(x["n_locations"] for x in rows)==5630 and sum(x["strict_unmatched_paths"] for x in rows)==26
  rep={"status":"MECHANISM_REPRODUCED_BUT_26_ROOT_NOT_PROVEN",
       "causal_counterexample":{"class_merge_tolerance_s":TIE_S,"strict_tol_s":5e-14,"raw_closest_s":uncollapsed,"grouped_closest_s":collapsed,"class_count":len(classes),"interpretation":"A ray exactly equal to a valid image delay can fail strict G3 after 1e-13 class merging, even though it passes 2e-13."},
       "six_cases":rows,
       "open_evidence":"The 26 raw per-ray tau/pose values are not included in existing G3 recheck receipts; do not label actual 26 due to class merging or float32 without the original traces.",
       "next_decisive_test":"For each strict mismatch compare raw tau with all unmerged image delays, merged representative delay, float32 rounding and pose coordinates. Classify and attach 26-row forensic ledger."}
  (out/"G3_FORENSIC_QA.json").write_text(json.dumps(rep,indent=2))
  print(json.dumps({"status":rep["status"],"strict_total":26,"merge_counterexample_residual_s":collapsed}))
if __name__=="__main__":main()

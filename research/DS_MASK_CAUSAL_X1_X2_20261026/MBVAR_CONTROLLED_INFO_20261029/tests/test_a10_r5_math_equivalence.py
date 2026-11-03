"""A18-04 independent math equivalence against ORIGINAL S1V2 decision path.

Runs only with pinned FFD inputs as part of real technical SMOKE job. The
two estimators compute H1/H2/H3/CAL/H4/H4_REPRO with different code paths,
same synthetic field-level observations and exact same bootstrap seed.
"""
import math
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))
import a10_r5 as R5

@pytest.mark.skipif(os.environ.get("MBVAR_A010_REQUIRE_INPUTS")!="1",
                    reason="requires pinned prior FFD scientific source for original V.decide_v2")
def test_a18_04_all_62_hypotheses_match_original_independent_v2_math():
    import s1v2 as V
    import s1_mc as M
    import s0v2 as S0
    cfg,_=R5.spec_with_sha()
    assert tuple(V.LH_CELLS)==R5.LH_CELLS
    assert tuple(S0.REV_CELLS)==R5.RV_CELLS
    assert set(S0.XMODEL)==set(R5.XMODEL_CELLS)
    fields=list(range(900,908))
    rows=[]
    familyids=["LOW","HIGH","REV60","FWD60"]
    stateids=R5.STATES
    for f in fields:
        for role in familyids:
            cells=R5.LH_CELLS if role in ("LOW","HIGH") else R5.RV_CELLS
            for cell in cells:
                arms=("IID_BATCH","ORACLE_CORR_BATCH") + (
                    ("XMODEL_BATCH",) if role in ("REV60","FWD60") and cell in R5.XMODEL_CELLS else ())
                for arm in arms:
                    ri=familyids.index(role)+1
                    ci=(R5.LH_CELLS if role in ("LOW","HIGH") else R5.RV_CELLS).index(cell)+1
                    ai={"IID_BATCH":1,"ORACLE_CORR_BATCH":2,"XMODEL_BATCH":3}[arm]
                    row=dict(field=f,role=role,cell=cell,sensor_seed=0,
                             arm=arm,status="OK")
                    for j,state in enumerate(stateids):
                        # Nonconstant field effects prevent a trivially equal
                        # zero-bootstrap CI from masking wrong H1–H4 formulas.
                        value=(.32 + .095*(f-900) + .021*ri+.017*ci +
                               .034*ai + .015*j + .008*((f*ri+j+ai)%3))
                        claim=.4+.04*j+.02*ri+.016*ci+.013*ai
                        row[f"e_{state}"]=value*(-1 if f%2 else 1)
                        row[f"P_{state}"]=claim
                    # Original frozen M.field_table aggregates these three
                    # diagnostics even when a given H1/H4 equation uses only
                    # squared error and post-fit covariance.
                    row["nees4"]=sum(row[f"e_{k}"]**2/row[f"P_{k}"] for k in stateids)
                    row["win_head_ms_deg2"]=(row["e_psi"]*180/math.pi)**2
                    row["win_xy_ms_cm2"]=1e4*(row["e_rad"]**2+row["e_tan"]**2)
                    rows.append(row)
    rows=pd.DataFrame(rows)
    assert len(rows)==len(fields)*36
    pred=pd.DataFrame([
        dict(role=r,cell=c,**{f"infl_iid_{st}":1.07+.04*i
                   for i,st in enumerate(stateids)},
             mse_ratio_oracle_iid_tan=.74,mse_ratio_oracle_iid_psi=.76)
        for r in ("LOW","HIGH") for c in R5.LH_CELLS
    ]).set_index(["role","cell"])
    did=pd.DataFrame([dict(state=st,quantity="infl_iid",
                            DID_log=.65 if st=="psi" else -.54)
                      for st in ("psi","tan")])
    rv=pd.DataFrame([
       dict(role=role,cell=cell,arm=arm,
            infl_tan=1.11,infl_psi=1.14)
       for role in ("REV60","FWD60") for cell in R5.RV_CELLS
       for arm in (("IID_BATCH","ORACLE_CORR_BATCH","XMODEL_BATCH") if cell in R5.XMODEL_CELLS
                   else ("IID_BATCH","ORACLE_CORR_BATCH"))
    ]).set_index(["role","cell","arm"])
    sep=pd.DataFrame([dict(cell=c,arm=arm,state=st,SEP_log=.41,
                           testable=True)
                       for c in R5.XMODEL_CELLS for arm in ("IID_BATCH","XMODEL_BATCH")
                       for st in ("psi","tan")])
    eff=dict(equivalence_factor=1.5,did_min_predicted_factor=1.2,
             did_min_fraction_of_prediction=.5,oracle_gain_ratio_max=.9)
    # Original source decision uses M.field_table, M.boot(B=4000), V._sided
    # with fresh seeded RNG on EACH test. R5 uses grouped arrays and one
    # shared bootstrap sample-index matrix for paired comparison.
    old=V.decide_v2(rows,pred,did,rv,sep,eff)
    new=R5.field_paired_conclusion_gate(rows,pd.DataFrame(),
        (pred,did,rv,sep,eff),cfg,
        registered_fields=fields,registered_sensor_seeds=(0,))
    assert new["status"]=="STABLE_ON_GRID_AND_CONSERVATIVE_BOUNDS"
    assert new["n_hypotheses"]==62
    assert {k:len(v) for k,v in new["hypotheses"].items()}==R5.REGISTERED_HYPOTHESIS_COUNTS
    assert new["baseline_overall_verdict"]==old["verdict"]
    for family in R5.REGISTERED_HYPOTHESIS_COUNTS:
        orig=old[family]
        fresh=new["hypotheses"][family]
        assert len(orig)==len(fresh)
        for r,t in zip(orig,fresh):
            expected_id="|".join(str(r[k]) for k in
                (("role","cell","state") if family in ("H1","CAL") else
                 ("state",) if family=="H2" else
                 ("role","state") if family=="H3" else
                 ("cell","arm","state") if family=="H4" else
                 ("role","cell","arm","state")))
            assert t["id"]==family+"|"+expected_id
            v=t["original"]
            if family=="H1":est=r["log_dev"]
            elif family=="H2":est=r["DID_S1"]
            elif family=="H3":est=math.log(r["ratio_S1"])
            elif family=="CAL":est=r["log_dev"]
            elif family=="H4":est=r["SEP_S1"]
            else:est=r["log_dev"]
            # Old H3 reports CI after exp(), while new contract uses log ratio.
            lo,hi=(math.log(r["lo"]),math.log(r["hi"])) if family=="H3" else (r["lo"],r["hi"])
            assert abs(v["est"]-est)<1e-12,(family,expected_id,"point",v["est"],est)
            assert abs(v["lo"]-lo)<1e-12,(family,expected_id,"low",v["lo"],lo)
            assert abs(v["hi"]-hi)<1e-12,(family,expected_id,"high",v["hi"],hi)
            assert v["verdict"]==r["verdict"],(family,expected_id)
            assert not t["witness_change"]
            assert not t["possible_change_by_conservative_bounds"]
    # Full registered inputs are not a guarantee that H1/H4 claims succeeded.
    # This test certifies equivalence of arithmetic, not scientific support.
    assert not new["science_release_allowed"]

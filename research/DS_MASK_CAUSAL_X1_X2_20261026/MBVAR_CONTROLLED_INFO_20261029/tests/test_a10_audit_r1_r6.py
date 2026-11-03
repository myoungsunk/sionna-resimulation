"""A010 independent-auditor REVISION_REQUIRED R1-R4 negative fixtures (synthetic only).

No DEV3, HOLDOUT2/reserve or RT data accessed. Numeric adversaries are
predefined and MUST fail closed; no historical threshold is relaxed.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"code"))
import a10_validation as AV


def k(field,arm):
    return (field,"LOW","POSE_HIGH",0,arm)


def test_r1_same_count_missing_offset_by_duplicate_rejected():
    expected=[k(900,"IID_BATCH"),k(900,"ORACLE_CORR_BATCH")]
    actual=[expected[0],expected[0]]
    assert len(actual)==len(expected)
    q=AV.exact_registered_keyset(actual,expected)
    assert not q["pass_"] and q["n_duplicate_keys"]==1 and q["n_missing_keys"]==1
    assert q["n_unexpected_keys"]==0 and q["n_actual"]==2


def test_r1_exact_set_duplicate_extra_and_missing():
    expected=[k(900,"IID_BATCH"),k(901,"IID_BATCH")]
    assert AV.exact_registered_keyset(expected,expected)["pass_"]
    assert not AV.exact_registered_keyset(expected+[expected[0]],expected)["pass_"]
    assert not AV.exact_registered_keyset(expected[:1],expected)["pass_"]
    assert not AV.exact_registered_keyset([expected[0],k(999,"IID_BATCH")],expected)["pass_"]
    with pytest.raises(ValueError,match="REGISTERED_KEY_DUPLICATE"):
        AV.exact_registered_keyset(expected,expected+expected[:1])


def test_r1_expected_c3_full_contract_keys_are_unique():
    keys=AV.expected_c3_row_keys([900,901],[0],
        ("LOWCORR","POSE_HIGH"),("LOWCORR","POSE_HIGH"),("POSE_HIGH",))
    assert len(keys)==2*(2*2*2+2*(2*2+1))
    assert len(keys)==len(set(keys))
    assert AV.exact_registered_keyset(keys,keys)["pass_"]


def test_r2_pooled_99_percent_can_mask_failed_arm():
    many=[dict(field=900,role="LOW",cell="POSE_HIGH",arm="A",
               n_alt_ambiguous=0,E_vs_best_dref=.2) for _ in range(101)]
    bad=dict(field=900,role="LOW",cell="POSE_HIGH",arm="B",
             n_alt_ambiguous=0,E_vs_best_dref=1.5)
    assert 101/102>=.99  # the old pooled-only gate would incorrectly pass
    v=AV.mode_identifiability(many+[bad])
    assert v["n_rows"]==102 and not v["clean_subset_stability_pass"]
    assert not v["legacy_full_rows_pass"]
    assert v["per_arm"]["A"]["clean_nonambiguous"]["pass_"]
    assert not v["per_arm"]["B"]["clean_nonambiguous"]["pass_"]
    assert v["status"]=="NOT_IDENTIFIABLE"


def test_r2_arm_with_only_ambiguous_rows_must_not_be_waived():
    rows=[dict(field=900,role="LOW",cell="POSE_HIGH",arm="A",
               n_alt_ambiguous=0,E_vs_best_dref=.2),
          dict(field=901,role="LOW",cell="POSE_HIGH",arm="B",
               n_alt_ambiguous=1,E_vs_best_dref=.2)]
    result=AV.mode_identifiability(rows)
    assert result["status"]=="MIXED" and not result["clean_subset_stability_pass"]
    assert result["per_arm"]["B"]["clean_nonambiguous"]["n"]==0
    assert result["all_rows_retained_in_science"]


@pytest.mark.parametrize("bad", [float("nan"),float("inf"),float("-inf")])
def test_r2_nonfinite_distance_or_count_rejected(bad):
    with pytest.raises(ValueError,match="MODE_NONFINITE"):
        AV.mode_identifiability([dict(field=900,role="LOW",cell="POSE_HIGH",
             arm="A",n_alt_ambiguous=0,E_vs_best_dref=bad)])
    with pytest.raises(ValueError,match="MODE_NONFINITE"):
        AV.mode_identifiability([dict(field=900,role="LOW",cell="POSE_HIGH",
             arm="A",n_alt_ambiguous=bad,E_vs_best_dref=0.1)])


def original_arrays():
    return dict(z=np.zeros((3,2),np.float64),x0=np.zeros(4,np.float64),
                ds_m=np.array([0.,1.,1.]),gy_m=np.array([0.,.01,.01]),
                Sigma_model=np.eye(6,dtype=np.float64)*.04,
                dts=np.array([.5,.5,.5]),taps=np.array([1,2,3],np.int64))


def test_r3_exact_receipt_arrays_at_optimizer_boundary():
    src=original_arrays()
    call={k:v.copy() for k,v in src.items()}
    before=AV.optimizer_boundary_attestation(src,call)
    after=AV.optimizer_boundary_attestation(src,call)
    assert before["pass_"] and after["pass_"] and before["digest"]==after["digest"]
    assert before["n_arrays"]==7
    assert set(before["original_array_sha256"])==set(AV.BOUNDARY_ARRAY_NAMES)


@pytest.mark.parametrize("attack",["ulp-z","wrong-sig","different-dts","changed-taps",
                                   "wrong-x0","wrong-shape","wrong-dtype","nonfinite"])
def test_r3_original_vs_optimizer_actual_perturbation_fails(attack):
    src=original_arrays()
    actual={k:v.copy() for k,v in src.items()}
    if attack=="ulp-z":actual["z"][0,0]=np.nextafter(0.,np.inf)
    if attack=="wrong-sig":actual["Sigma_model"][0,0]+=.01
    if attack=="different-dts":actual["dts"][1]+=.1
    if attack=="changed-taps":actual["taps"][2]=4
    if attack=="wrong-x0":actual["x0"][1]+=.01
    if attack=="wrong-shape":actual["gy_m"]=actual["gy_m"][:2]
    if attack=="wrong-dtype":actual["z"]=actual["z"].astype(np.float32)
    if attack=="nonfinite":actual["Sigma_model"][0,0]=np.nan
    with pytest.raises(ValueError,match="OPTIMIZER_BOUNDARY"):
        AV.optimizer_boundary_attestation(src,actual)


def test_r3_post_call_mutation_fails_on_second_attestation():
    src=original_arrays()
    args={k:v.copy() for k,v in src.items()}
    AV.optimizer_boundary_attestation(src,args)
    args["gy_m"][2]=np.nextafter(args["gy_m"][2],np.inf)
    with pytest.raises(ValueError,match="BYTE_MISMATCH"):
        AV.optimizer_boundary_attestation(src,args)


def test_r4_finite_guard_and_keyset_as_dataframe():
    pd=pytest.importorskip("pandas")
    df=pd.DataFrame([dict(field=900,role="LOW",cell="POSE_HIGH",sensor_seed=0,
                          arm="IID_BATCH",cost=1.,nees4_C10=4.)])
    assert AV.dataframe_row_keys(df)==[k(900,"IID_BATCH")]
    assert AV.enforce_finite_rows(df,["cost","nees4_C10"],"POSITIVE")["pass_"]
    for bad in (float("nan"),float("inf"),float("-inf")):
        df.loc[0,"nees4_C10"]=bad
        with pytest.raises(ValueError,match="NONFINITE"):
            AV.enforce_finite_rows(df,["cost","nees4_C10"],"NEGATIVE")
    df.loc[0,"nees4_C10"]=4.
    df.loc[0,"sensor_seed"]=np.nan
    with pytest.raises(ValueError,match="ROW_KEY_NONFINITE"):
        AV.dataframe_row_keys(df)


def synthetic_solver_row():
    P=np.diag([.001,.001,.0001,.000001])
    return dict(field=900,role="LOW",cell="POSE_HIGH",sensor_seed=0,
                arm="IID_BATCH",cost=1.234,class_v31="CONVERGED_SMOOTH",
                n_alt_ambiguous=0,
                **{f"xend_{i}":float(i) for i in range(4)},
                **{f"C10rot_{i}{j}":float(P[i,j]) for i in range(4)
                   for j in range(i,4)},
                nees4_C10=.5)


def test_r4_cross_runner_nonfinite_cost_state_nees_covariance_rejected():
    a=dict(source_git_sha="a"*40,manifest_sha256="b"*64,
           input_sha256="c"*64,runner_id="vm-a",environment={},
           rows=[synthetic_solver_row()])
    b={**a,"runner_id":"vm-b","rows":[synthetic_solver_row()]}
    assert AV.validate_two_runner_solver_receipts(a,b)["pass_"]
    for column in ("cost","xend_1","nees4_C10","C10rot_00"):
        for bad in (float("nan"),float("inf")):
            broken={**b,"rows":[dict(b["rows"][0])]}
            broken["rows"][0][column]=bad
            out=AV.validate_two_runner_solver_receipts(a,broken)
            assert not out["pass_"] and out["n_fail"]==1
            assert out["failure_details"][0]["reason"]=="NONFINITE_COST_STATE_C10_NEES"


def test_r4_comparison_difference_nonfinite_not_accepted():
    assert not AV.finite_scalar_check(float("nan"))
    assert not AV.finite_scalar_check(float("inf"))
    assert AV.finite_scalar_check(1e-8,0.)

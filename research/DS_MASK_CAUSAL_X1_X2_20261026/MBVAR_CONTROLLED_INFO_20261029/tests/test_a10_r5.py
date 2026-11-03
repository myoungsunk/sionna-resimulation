"""Prospective R5 precision/sensitivity contract fixtures (no DEV3/HOLDOUT/RT).
Includes negative cap/descent/nonfinite/duplicate/missing/SPD/arm and
a positive + conclusion-changing H/CAL field-bootstrap witness.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pytest
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
import a10_r5 as R5
import a10_validation as AV


def policy():
    p,h=R5.spec_with_sha()
    assert len(h)==64 and p["a010_science_frozen"] is False
    return p


def terminals():
    return [dict(start=s,cost=12.,dmin=-.0005,end_state=[0.,0.,0.,0.],
                 polish_steps=2,polish_hit_cap=False)
            for s in R5.SOLS]


def test_r5_proposer_spec_is_final_but_science_remains_draft():
    cfg=policy()
    assert len(R5.STARTS)==9 and len(R5.SOLS)==10
    assert cfg["decision"]=="FINAL_PRE_FREEZE"
    assert not cfg["independent_auditor_signed"]
    assert cfg["dev3"]==cfg["holdout2"]==cfg["rt"]=="NO-GO"
    assert cfg["polish"]["cost_descent_tol_chi2"]==.001
    assert cfg["field_sensitivity"]["field_bootstrap_B"]==4000


def test_r5_ten_terminals_positive():
    z=R5.validate_terminals(terminals(),policy())
    assert z["pass_"] and z["status"]=="PASS"
    assert z["n_expected"]==10 and z["n_solutions"]==10
    assert z["science_release_allowed"] is False


@pytest.mark.parametrize("bad",["cap","extra_descent","nan_cost","nan_state",
                                "inf_dmin","missing","duplicate","truth","invalid_steps"])
def test_r5_terminals_one_bad_solution_fail_closed(bad):
    q=terminals()
    if bad=="cap":q[4]["polish_hit_cap"]=True
    if bad=="extra_descent":q[1]["dmin"]=-.0010001
    if bad=="nan_cost":q[0]["cost"]=float("nan")
    if bad=="nan_state":q[3]["end_state"][2]=float("nan")
    if bad=="inf_dmin":q[4]["dmin"]=float("inf")
    if bad=="missing":q.pop()
    if bad=="duplicate":q[2]["start"]=q[3]["start"]
    if bad=="truth":q[2]["start"]="truth"
    if bad=="invalid_steps":q[1]["polish_steps"]=31
    result=R5.validate_terminals(q,policy())
    assert not result["pass_"],bad
    assert result["status"]=="UNRESOLVED_PRECISION"
    assert result["n_failures"]>0


def alt_row():
    return dict(delta_chi2=-.02,end_dref=2.2,nees4_alt=.7,
                delta_nees4=.8,delta_logdet_P=.10,
                covariance_alt_spd=True,
                **{f"delta_sq_err_{s}":.0005 for s in R5.STATES})


@pytest.mark.parametrize("attack",["low_cost","small_distance","nonspd","nan_nees","inf_logdet"])
def test_r5_alternative_fail_closed(attack):
    row=alt_row()
    if attack=="low_cost":row["delta_chi2"]=-1.2
    if attack=="small_distance":row["end_dref"]=1.99
    if attack=="nonspd":row["covariance_alt_spd"]=False
    if attack=="nan_nees":row["nees4_alt"]=float("nan")
    if attack=="inf_logdet":row["delta_logdet_P"]=float("inf")
    result=R5.checked_alternative(row,dict(status="PASS"),policy())
    assert not result["eligible"]


def test_r5_uncertified_terminal_never_becomes_admissible():
    row=alt_row()
    result=R5.checked_alternative(row,dict(status="UNRESOLVED_PRECISION"),policy())
    assert result["status"]=="UNRESOLVED_PRECISION" and not result["eligible"]


def test_r5_numeric_material_thresholds():
    a=alt_row()
    assert R5.numeric_flags(a,policy())["material_numeric_sensitivity"]
    a["delta_nees4"]=0.
    a["delta_logdet_P"]=0.
    for st in R5.STATES:a[f"delta_sq_err_{st}"]=0.
    assert not R5.numeric_flags(a,policy())["material_numeric_sensitivity"]
    a["delta_sq_err_tan"]=float("nan")
    assert not R5.numeric_flags(a,policy())["numeric_finite"]


def fixture_science(n_fields=4,changed=False):
    fields=list(range(900,900+n_fields))
    rows=[];alts=[]
    roles={r:("LOWCORR","POSE_HIGH") for r in ("LOW","HIGH")}
    roles.update({r:("POSE_HIGH",) for r in ("REV60","FWD60")})
    for f in fields:
        for role,cells in roles.items():
            for cell in cells:
                arms=("IID_BATCH","ORACLE_CORR_BATCH")
                if role.startswith(("REV","FWD")):arms+=("XMODEL_BATCH",)
                for arm in arms:
                    row=dict(field=f,role=role,cell=cell,sensor_seed=0,arm=arm,
                             status="OK",**{f"e_{s}":1. for s in R5.STATES},
                             **{f"P_{s}":1. for s in R5.STATES})
                    rows.append(row)
                    if changed and f==fields[0] and role=="LOW" and cell=="POSE_HIGH" and arm=="IID_BATCH":
                        alt=dict(field=f,role=role,cell=cell,sensor_seed=0,
                                 arm=arm,alt_start="psi-1",R5_ALTERNATIVE_ADMISSIBLE=True,
                                 **{f"alt_end_error_{s}":10. for s in R5.STATES},
                                 **{f"delta_P_{s}":0. for s in R5.STATES})
                        alts.append(alt)
    pred=pd.DataFrame([dict(role=role,cell=cell,
                            infl_iid_psi=1.,infl_iid_tan=1.,
                            mse_ratio_oracle_iid_psi=.8,mse_ratio_oracle_iid_tan=.8)
                       for role in ("LOW","HIGH") for cell in ("LOWCORR","POSE_HIGH")]).set_index(["role","cell"])
    did=pd.DataFrame([dict(state=s,quantity="infl_iid",DID_log=1.) for s in ("psi","tan")])
    rv=pd.DataFrame([dict(role=r,cell="POSE_HIGH",arm=a,infl_psi=1.,infl_tan=1.)
                     for r in ("REV60","FWD60")
                     for a in ("IID_BATCH","ORACLE_CORR_BATCH","XMODEL_BATCH")]).set_index(["role","cell","arm"])
    sep=pd.DataFrame([dict(cell="POSE_HIGH",arm=a,state=s,SEP_log=1.,testable=True)
                     for a in ("IID_BATCH","XMODEL_BATCH") for s in ("psi","tan")])
    eff=dict(equivalence_factor=1.5,did_min_predicted_factor=1.2,
             did_min_fraction_of_prediction=.5,oracle_gain_ratio_max=.9)
    return pd.DataFrame(rows),pd.DataFrame(alts),(pred,did,rv,sep,eff)


def test_r5_field_bootstrap_all_registered_families_with_no_alternatives():
    rows,alts,ref=fixture_science()
    r=R5.field_paired_conclusion_gate(rows,alts,ref,policy())
    assert r["status"]=="STABLE_ON_GRID_AND_CONSERVATIVE_BOUNDS"
    assert r["n_fields"]==4 and r["bootstrap_replicates"]==4000
    assert r["bootstrap_seed"]==20261029
    assert not r["alternative_changes_conclusion"]
    assert not r["witness_changed_hypotheses"]
    assert set(("H1","H2","H3","CAL","H4","H4_REPRO")).issubset(r["hypotheses"])
    assert not r["science_release_allowed"]


def test_r5_field_paired_conclusion_change_requires_review():
    rows,alts,ref=fixture_science(changed=True)
    r=R5.field_paired_conclusion_gate(rows,alts,ref,policy())
    assert r["status"]=="ALTERNATIVE_CHANGES_CONCLUSION",r
    assert r["alternative_changes_conclusion"]
    assert r["n_alternative_rows"]==1
    assert any(x.startswith("H1|") for x in r["witness_changed_hypotheses"])
    assert r["hypotheses"]["H1"][0]["by_start"]["psi-1"] is not None
    assert not r["science_release_allowed"]


def test_r5_ambiguous_start_cannot_be_treated_as_extra_field():
    rows,alts,ref=fixture_science(changed=True)
    alt_more=alts.copy()
    alt_more["alt_start"]="psi+2"
    alt_more["alt_end_error_tan"]=11.
    r=R5.field_paired_conclusion_gate(rows,pd.concat([alts,alt_more]),ref,policy())
    assert r["n_fields"]==4 and r["n_alternative_rows"]==2
    assert r["bootstrap_replicates"]==4000


def test_r5_missing_registered_group_fail_closed_not_science_success():
    rows,alts,ref=fixture_science()
    missing=rows[~((rows.role=="HIGH")&(rows.cell=="LOWCORR"))]
    r=R5.field_paired_conclusion_gate(missing,alts,ref,policy())
    assert r["status"]=="NOT_EVALUATED_INCOMPLETE"
    assert not r["science_release_allowed"]


def test_r5_nonspd_or_uncertified_alternative_fails_closed():
    rows,alts,ref=fixture_science(changed=True)
    z=alts.copy();z.loc[0,"delta_P_tan"]=-3.
    with pytest.raises(ValueError,match="ERR_R5_ALT_NONSPD"):
        R5.field_paired_conclusion_gate(rows,z,ref,policy())
    z=alts.copy();z.loc[0,"R5_ALTERNATIVE_ADMISSIBLE"]=False
    with pytest.raises(ValueError,match="ERR_R5_ALT_NOT_CERTIFIED"):
        R5.field_paired_conclusion_gate(rows,z,ref,policy())


def test_r5_arm_stratification_existing_legacy_hard_gate():
    def row(arm,d):
        return dict(arm=arm,field=900,role="LOW",cell="POSE_HIGH",
                    n_alt_ambiguous=0,E_vs_best_dref=d)
    r=AV.mode_identifiability([row("A",.1)]*101+[row("B",1.5)])
    assert not r["legacy_full_rows_pass"]
    assert not r["per_arm"]["B"]["legacy_all_rows"]["pass_"]


def test_r5_csv_roundtrip_preserves_positive_terminal_certificate(tmp_path):
    """Real C3V5 terminal CSV serializes end_state as '[x,y,psi,bg]' text."""
    records=terminals()
    csv=tmp_path/"R5_CERT.csv"
    pd.DataFrame(records).to_csv(csv,index=False,float_format="%.17g")
    observed=pd.read_csv(csv).to_dict("records")
    assert isinstance(observed[0]["end_state"],str)
    assert R5.validate_terminals(observed,policy())["pass_"]
    assert R5.validate_terminals(records,policy())["pass_"]


def test_r5_csv_roundtrip_explicit_false_is_not_cap(tmp_path):
    """A raw csv.DictReader caller receives 'False' TEXT, not Python False."""
    import csv as csvlib
    source=tmp_path/"R5_RAW.csv"
    pd.DataFrame(terminals()).to_csv(source,index=False)
    with source.open() as fh:
        raw=list(csvlib.DictReader(fh))
    assert raw[0]["polish_hit_cap"]=="False"
    assert R5.validate_terminals(raw,policy())["pass_"]


@pytest.mark.parametrize("attack",[
    ("polish_hit_cap","True"),
    ("polish_hit_cap","unknown"),
    ("polish_hit_cap",""),
    ("polish_steps","NaN"),
    ("polish_steps","31"),
    ("end_state","[]"),
    ("end_state","[1, 2, 3]"),
    ("end_state","[1, 2, 3, NaN]"),
    ("end_state","not-json"),
    ("end_state","[1, 2, 3, Infinity]"),
    ("cost","inf"),
    ("dmin","-0.00101"),
])
def test_r5_csv_corrupted_terminals_rejected(tmp_path,attack):
    """String-record attacks all produce UNRESOLVED_PRECISION, not exception/PASS."""
    import csv as csvlib
    source=tmp_path/"R5_ATTACK.csv"
    pd.DataFrame(terminals()).to_csv(source,index=False)
    with source.open() as fh:
        records=list(csvlib.DictReader(fh))
    records[0][attack[0]]=attack[1]
    out=R5.validate_terminals(records,policy())
    assert out["status"]=="UNRESOLVED_PRECISION"
    assert not out["pass_"] and out["n_failures"]>0

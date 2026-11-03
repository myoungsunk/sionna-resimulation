"""Independent-auditor A18-02/A18-03 negative fixtures (no physical data)."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
import a10_r5 as R5

POLICY="a"*64
KEY=dict(field=900,role="LOW",cell="POSE_HIGH",sensor_seed=0,arm="IID_BATCH")
def independent_seed(*parts):
    return int(hashlib.sha256("|".join(map(str,parts)).encode()).hexdigest()[:15],16)

def evidence():
    seed=independent_seed("R5_CERT",900,"LOW","POSE_HIGH",0,"IID_BATCH")
    src=[dict(KEY,R5_POLICY_SHA256=POLICY,R5_CERT_SEED=seed)]
    cert=[dict(KEY,start=x,r5_policy_sha256=POLICY,r5_cert_seed=seed)
          for x in R5.SOLS]
    alt=[dict(KEY,alt_start="psi-1",R5_POLICY_SHA256=POLICY,r5_cert_seed=seed)]
    return src,cert,alt

def test_a18_02_positive_all_source_terminal_alternatives_sha_seed():
    src,cert,alt=evidence()
    out=R5.verify_stored_r5_provenance(src,cert,alt,POLICY,independent_seed)
    assert out["pass_"] and out["registered_rows"]==1
    assert out["verified_terminal_records"]==10
    assert out["verified_alternative_records"]==1

@pytest.mark.parametrize("target,field",[
    ("source","R5_POLICY_SHA256"),("source","R5_CERT_SEED"),
    ("terminal","r5_policy_sha256"),("terminal","r5_cert_seed"),
    ("alternative","R5_POLICY_SHA256"),("alternative","r5_cert_seed")
])
def test_a18_02_any_single_sha_or_seed_corruption_blocks(target,field):
    src,cert,alt=evidence()
    row={"source":src[0],"terminal":cert[3],"alternative":alt[0]}[target]
    if field.lower().endswith("sha256"):row[field]="b"*64
    else:row[field]=int(row[field])^1
    with pytest.raises(ValueError,match="ERR_R5_PROVENANCE"):
        R5.verify_stored_r5_provenance(src,cert,alt,POLICY,independent_seed)

def test_a18_02_float_seed_precision_loss_not_silent_acceptance():
    src,cert,alt=evidence()
    cert[0]["r5_cert_seed"]=float(cert[0]["r5_cert_seed"])
    with pytest.raises(ValueError,match="ERR_R5_PROVENANCE_TERMINAL_SEED"):
        R5.verify_stored_r5_provenance(src,cert,alt,POLICY,independent_seed)

@pytest.mark.parametrize("attack",["remove_terminal","duplicate_terminal",
                                    "unexpected_alt","remove_source","change_start"])
def test_a18_02_bad_provenance_key_sets_rejected(attack):
    src,cert,alt=evidence()
    if attack=="remove_terminal":cert.pop()
    if attack=="duplicate_terminal":cert.append(copy.deepcopy(cert[0]))
    if attack=="unexpected_alt":alt[0]["arm"]="SPOOF"
    if attack=="remove_source":src.clear()
    if attack=="change_start":cert[3]["start"]="truth"
    with pytest.raises(ValueError,match="ERR_R5_PROVENANCE"):
        R5.verify_stored_r5_provenance(src,cert,alt,POLICY,independent_seed)

ST=R5.STATES

def _matrix_fields(prefix,P):
    return {f"{prefix}_{i}{j}":float(P[i,j]) for i in range(4) for j in range(i,4)}

def covariance_fixtures():
    # Properly normalized 4D covariance, small offdiagonal (SPD).
    P0=np.array([[1.0,.07,0,0],[.07,1.5,0,0],
                 [0,0,.45,.06],[0,0,.06,.35]])
    P1=np.array([[1.2,.08,0,0],[.08,1.6,0,0],
                 [0,0,.50,.03],[0,0,.03,.40]])
    e0=np.array([.2,-.1,.3,.12])
    e1=np.array([.3,-.2,.2,.09])
    n0=float(e0@np.linalg.solve(P0,e0))
    n1=float(e1@np.linalg.solve(P1,e1))
    ld0=np.linalg.slogdet(P0)[1]
    ld1=np.linalg.slogdet(P1)[1]
    d=np.sqrt(np.diag(P1))
    cond=float(np.log10(np.linalg.cond(P1/d[:,None]/d[None,:])))
    row=dict(_matrix_fields("R5_C10E",P0),**_matrix_fields("R5_C10ALT",P1),
             R5_C10ALT_MIN_EIG=float(np.linalg.eigvalsh(P1)[0]),
             R5_C10ALT_LOG10_COND=cond, nees4_E=n0,nees4_alt=n1,
             delta_nees4=n1-n0,delta_logdet_P=ld1-ld0,
             covariance_alt_spd=True)
    row.update({f"R5_E_END_ERROR_{k}":float(e0[i]) for i,k in enumerate(ST)})
    row.update({f"alt_end_error_{k}":float(e1[i]) for i,k in enumerate(ST)})
    row.update({f"delta_P_{k}":float(P1[i,i]-P0[i,i]) for i,k in enumerate(ST)})
    row.update({f"delta_sq_err_{k}":float(e1[i]**2-e0[i]**2) for i,k in enumerate(ST)})
    source=dict(_matrix_fields("C10rot",P0),nees4_C10=n0)
    return row,source

def test_a18_03_positive_rederives_full_two_covariances_NEES_and_deltas():
    row,source=covariance_fixtures()
    out=R5.verify_stored_alternative_full_c10(row,source)
    assert out["full_c10_spd_verified"]
    assert out["upper_triangle_entries_checked"]==20
    assert abs(out["nees4_alt_independent"]-row["nees4_alt"])<1e-12

def test_a18_03_offdiagonal_indefinite_with_positive_diagonal_rejected():
    row,source=covariance_fixtures()
    # eigenvalues of 2x2 block = 3,-1; all diagonals positive.
    P=np.array([[1.,2.,0.,0.],[2.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])
    row.update(_matrix_fields("R5_C10ALT",P))
    assert np.all(np.diag(P)>0) and np.linalg.eigvalsh(P)[0]<0
    with pytest.raises(ValueError,match="ERR_R5_STORED_C10_NONSPD"):
        R5.verify_stored_alternative_full_c10(row,source)

@pytest.mark.parametrize("attack",[
    "nees4_alt","nees4_E","delta_nees4","delta_logdet_P",
    "R5_C10ALT_LOG10_COND","delta_P_tan","delta_sq_err_tan",
    "R5_C10E_01","C10rot_source","R5_C10ALT_01"
])
def test_a18_03_corrupted_stored_full_covariance_and_score_rejected(attack):
    row,source=covariance_fixtures()
    if attack=="C10rot_source":source["C10rot_01"]+=.2
    else:row[attack]=float(row[attack])+.2
    with pytest.raises(ValueError,match="ERR_R5_"):
        R5.verify_stored_alternative_full_c10(row,source)

@pytest.mark.parametrize("attack",["nonfinite","missing","not_spd"])
def test_a18_03_bad_or_missing_full_covariance_rejected(attack):
    row,source=covariance_fixtures()
    if attack=="nonfinite":row["R5_C10ALT_00"]=float("nan")
    if attack=="missing":row.pop("R5_C10ALT_33")
    if attack=="not_spd":row["covariance_alt_spd"]=False
    with pytest.raises((ValueError,KeyError),match="ERR_R5_|R5_C10"):
        R5.verify_stored_alternative_full_c10(row,source)

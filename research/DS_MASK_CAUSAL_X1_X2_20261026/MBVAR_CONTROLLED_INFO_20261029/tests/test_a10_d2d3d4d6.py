"""Prospective A010 negative and invariant tests. Synthetic fixtures only, no DEV3 data."""
import json
import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "code"))
import a10_validation as A
import contract_lock as CL


def sig(n=6):
    x = np.arange(1, n*n+1, dtype=float).reshape(n, n)/100
    return x @ x.T + 3 * np.eye(n)


def matrices(right=None):
    return {"MAT|900|LOW|POSE_HIGH|Sig_true": sig(),
            "MAT|901|LOW|POSE_HIGH|Sig_true": sig() if right is None else right}


def test_cross_field_identical_and_ulp():
    d=A.covariance_equivalence(matrices(),expected_fields=[900,901])
    assert d["pass_"] and d["delta_max"]==0 and d["delta_F"]==0
    alt=sig();alt[0,0]=np.nextafter(alt[0,0],np.inf)
    d=A.covariance_equivalence(matrices(alt),expected_fields=[900,901])
    assert d["pass_"] and d["delta_max"]>0 and d["delta_F"]>0


@pytest.mark.parametrize("attack",["1e-7","missing-field","wrong-shape","wrong-dtype","nonspd","asym"])
def test_cross_field_rejects_difference(attack):
    a=sig()
    if attack=="1e-7": a[0,0]+=1e-7
    if attack=="wrong-shape": a=np.eye(4)
    if attack=="wrong-dtype": a=a.astype(np.float32)
    if attack=="nonspd": a=-a
    if attack=="asym": a[0,1]+=.2
    data=matrices(a)
    if attack=="missing-field": del data["MAT|901|LOW|POSE_HIGH|Sig_true"]
    if attack in ("wrong-shape","wrong-dtype","asym"):
        with pytest.raises(ValueError): A.covariance_equivalence(data,expected_fields=[900,901])
    else:
        assert not A.covariance_equivalence(data,expected_fields=[900,901])["pass_"]


def fixture(tmp, changed=None):
    prefix="900|LOW|POSE_HIGH|0"
    data={prefix+"|z":np.zeros((3,2)),prefix+"|x0":np.zeros(4),
          prefix+"|ds_m":np.zeros(3),prefix+"|gy_m":np.zeros(3),
          prefix+"|taps":np.array([1,2,3],dtype=np.int64),
          "MAT|900|LOW|POSE_HIGH|Sig_true":sig()}
    if changed: data.update(changed)
    z=tmp/"S1V5_INPUTS_SMOKE_900.zip"
    with open(z,"wb") as f: np.savez_compressed(f,**data)
    j=tmp/"S1V5_INPUT_HASHES_SMOKE_900.json"
    j.write_text(json.dumps(A.make_array_index(data,[900],z)))
    hashes={p.name:A._sha_file(p) for p in (z,j)}
    return z,j,hashes,data


def test_receipt_sha_positive(tmp_path):
    z,j,hashes,data=fixture(tmp_path)
    loaded,proof=A.verify_receipt_index(z,j,hashes)
    assert proof["n_arrays"]==len(data)
    assert A.array_sha(loaded["900|LOW|POSE_HIGH|0|z"])==A.array_sha(data["900|LOW|POSE_HIGH|0|z"])


@pytest.mark.parametrize("attack",["zip-bit","index-sha","dtype","zero-row","negative-tap","wrong-field","duplicate-member"])
def test_receipt_sha_rejects_corrupt_or_swapped(tmp_path,attack):
    key="900|LOW|POSE_HIGH|0"
    z,j,hashes,data=fixture(tmp_path)
    if attack=="zip-bit":
        raw=bytearray(z.read_bytes());raw[-1]^=1;z.write_bytes(raw)
    elif attack=="index-sha":
        idx=json.loads(j.read_text());idx["array_sha256"][key+"|z"]="0"*64
        j.write_text(json.dumps(idx));hashes[j.name]=A._sha_file(j)
    else:
        if attack=="dtype":data[key+"|z"]=data[key+"|z"].astype(np.float32)
        if attack=="zero-row":data[key+"|z"]=data[key+"|z"][:0]
        if attack=="negative-tap":data[key+"|taps"][0]=-1
        if attack=="wrong-field":data["MAT|901|LOW|POSE_HIGH|Sig_true"]=data.pop("MAT|900|LOW|POSE_HIGH|Sig_true")
        with open(z,"wb") as f: np.savez_compressed(f,**data)
        if attack=="duplicate-member":
            stream=io.BytesIO();np.save(stream,np.zeros((3,2)))
            with zipfile.ZipFile(z,"a") as f: f.writestr(key+"|z.npy",stream.getvalue())
        j.write_text(json.dumps(A.make_array_index(data,[900],z)))
        hashes={p.name:A._sha_file(p) for p in (z,j)}
    with pytest.raises((ValueError,zipfile.BadZipFile)):
        A.verify_receipt_index(z,j,hashes)


def test_estimator_inputs_exact_bytes_no_field_swap():
    k="900|LOW|POSE_HIGH|0"
    inp=dict(z=np.zeros((3,2)),x0=np.zeros(4),ds_m=np.zeros(3),gy_m=np.zeros(3))
    model=sig()
    rec={k+"|"+n:a.copy() for n,a in inp.items()}
    rec[k+"|taps"]=np.array([1,2,3])
    rec["MAT|900|LOW|POSE_HIGH|IID_BATCH|Sig_model"]=model
    assert A.verify_estimator_inputs(rec,k,inp,model,rec[k+"|taps"],"IID_BATCH")["pass_"]
    other=model.copy();other[0,0]+=1e-12
    assert not A.verify_estimator_inputs(rec,k,inp,other,rec[k+"|taps"],"IID_BATCH")["pass_"]
    swapped={x.replace("900","901"):v for x,v in rec.items()}
    assert not A.verify_estimator_inputs(swapped,k,inp,model,rec[k+"|taps"],"IID_BATCH")["pass_"]


def test_generator_law_full_sigma_and_ou():
    c=dict(alphas=(.45,.35,.20),c=.2,tau=1.5)
    s=dict(pose_corr_length_m=2.,pose_corr_yaw_deg=15.,sigma_r_m=.08,sigma_s=.04)
    w=dict(poses=np.array([[0.,0.,0.],[1.,0.,0.],[0.,0.,0.]]),t=np.arange(3,dtype=float))
    full,kp,kt=A.independent_sigma(w,c,s)
    assert abs(kp[0,2]-1)<1e-14 and abs(kt[0,2]-np.exp(-2/1.5))<1e-14
    assert A.generator_law(w,dict(cells={"POSE_HIGH":c},s1=s),"POSE_HIGH",full)["pass_"]
    broken=full.copy();broken[0,0]+=1e-7
    assert not A.generator_law(w,dict(cells={"POSE_HIGH":c},s1=s),"POSE_HIGH",broken)["pass_"]


def row(P,ne=1.):
    return {**{f"C10rot_{i}{j}":float(P[i,j]) for i in range(4) for j in range(i,4)},"nees4_C10":ne}


def test_full_c10_spd_and_condition():
    P=np.array([[2.,.1,0,0],[.1,3,0,0],[0,0,4,.1],[0,0,.1,5.]])
    assert A.c10_diagnostics(row(P))["pass_"]
    assert A.covariance_replay_check(row(P),row(P),scaled_difference=lambda *_:0)["pass_"]
    other=P.copy();other[0,0]*=1.2
    assert not A.covariance_replay_check(row(other),row(P),scaled_difference=lambda *_:0)["pass_"]
    bad=P.copy();bad[3,3]=-1
    assert not A.c10_diagnostics(row(bad))["pass_"]


def test_two_verdicts_no_suffix_heuristic():
    c={k:{"pass_":True} for k in A.G5_NUMERIC_GATE_IDS}
    c["STATE_STABILITY_FIXED_LEGACY"]={"pass_":False}
    assert A.gate_verdict(c)["status"]=="PASS"
    c["GENERATOR_LAW"]["pass_"]=False
    assert A.gate_verdict(c)["status"]=="FAIL"
    del c["FULL_C10_REPRO"]
    assert A.gate_verdict(c)["status"]=="BLOCKED"
    sample=dict(field=900,role="LOW",cell="POSE_HIGH",arm="IID_BATCH",E_vs_best_dref=.1)
    mode=A.mode_identifiability([dict(sample,n_alt_ambiguous=0),dict(sample,n_alt_ambiguous=1)])
    assert mode["status"]=="MIXED" and mode["n_rows"]==2 and not mode["scientific_release"]


def test_full_split_overlay_draft_preserves_existing_tracks():
    old=CL.effective_lock()["splits"]["S_field"]
    annex=(EXP/"contracts"/"AMENDMENT-010-D2D3D4D6-DRAFT.md").read_text()
    fence=chr(96)*3
    candidate=json.loads(re.findall(re.escape(fence)+r"json\n(.*?)\n"+re.escape(fence),annex,re.S)[-1])
    assert candidate["status"]=="DRAFT" and not candidate["can_execute"]
    assert A.split_diff(old,candidate["splits"]["S_field"])["pass_"]
    assert candidate["run_plan"]["S1V5"]["fields"]==list(range(20,30))
    assert candidate["run_plan"]["C3V5"]["fields"]==list(range(20,30))
    broken=dict(candidate["splits"]["S_field"]);broken["DEV2"]=[-1]
    assert not A.split_diff(old,broken)["pass_"]
    broken["HOLDOUT"]=[-1]
    assert not A.split_diff(old,broken)["pass_"]
    assert CL.amendment_lock("AMENDMENT-010") is None


def test_two_runner_strict_proof_positive_and_negative():
    P=np.diag([.001,.001,.0001,.000001])
    rr=dict(field=900,role="LOW",cell="POSE_HIGH",sensor_seed=0,arm="IID_BATCH",
            cost=1.234,class_v31="CONVERGED_SMOOTH",n_alt_ambiguous=0,
            **{f"xend_{i}":0.0 for i in range(4)},**row(P))
    base=dict(source_git_sha="a"*40,manifest_sha256="b"*64,
              input_sha256="c"*64,runner_id="runner-1",
              environment=dict(cpu="x86_64"),rows=[rr])
    other={**base,"runner_id":"runner-2"}
    result=A.validate_two_runner_solver_receipts(base,other)
    assert result["pass_"] and result["n_rows"]==1
    assert not A.validate_two_runner_solver_receipts(base,{**other,"runner_id":"runner-1"})["pass_"]
    assert not A.validate_two_runner_solver_receipts(base,{**other,"input_sha256":"d"*64})["pass_"]
    damaged=dict(rr);damaged["cost"]+=0.01
    assert not A.validate_two_runner_solver_receipts(base,{**other,"rows":[damaged]})["pass_"]
    damaged=dict(rr);damaged["C10rot_00"]*=1.02
    assert not A.validate_two_runner_solver_receipts(base,{**other,"rows":[damaged]})["pass_"]
    damaged=dict(rr);damaged["n_alt_ambiguous"]=1
    assert not A.validate_two_runner_solver_receipts(base,{**other,"rows":[damaged]})["pass_"]
    with pytest.raises(ValueError,match="DUPLICATE"):
        A.validate_two_runner_solver_receipts(base,{**other,"rows":[rr,rr]})

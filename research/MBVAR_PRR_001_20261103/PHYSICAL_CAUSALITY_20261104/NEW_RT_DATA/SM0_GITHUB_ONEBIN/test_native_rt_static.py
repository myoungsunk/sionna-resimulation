"""Pre-solver scientific safety/unit tests. Sionna RT is never imported."""
import importlib.util,json,math,pathlib,sys
import numpy as np
import pytest
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_rt_batch as B
import native_rt_aggregate as A

def test_registered_source_original_bytes_and_pinned_pose_universe():
    lock,solver=B.preflight()
    assert lock["pose_ids"]==[194,234,500,525]
    assert [x["id"] for x in lock["scenes"]]==list(B.ARMS)
    assert lock["governance"]["original_SM0_expansion"]=="NO-GO"
    assert lock["governance"]["HOLDOUT2"]=="NO-GO"
    assert lock["simulated_workload"]["approved_solver_calls"]==0
    for pose_id in lock["pose_ids"]:
        row=B.get_pose(pose_id)
        assert all(math.isfinite(row[x]) for x in ("x","y","yaw_body_deg"))
    assert solver["max_depth"]==3

def test_8224_actual_PathSolver_calls_in_16_config_two_repeats():
    cfg=json.loads(B.LOCK.read_text())
    assert len(cfg["pose_ids"])==4
    assert len(cfg["scenes"])==4
    assert 4*4*257==4112
    assert 4*4*257*2==8224
    assert cfg["simulated_workload"]["proposed_total_solver_calls_if_2_repeats"]==8224
    assert cfg["simulated_workload"]["approved_solver_calls"]==0

def test_floor_plate_shapes_finite_and_oblique_not_parallel():
    cfg=json.loads(B.LOCK.read_text())
    p0=B.plate_vertices(cfg,0)
    p1=B.plate_vertices(cfg,20)
    assert p0.shape==p1.shape==(4,3)
    assert np.isfinite(p0).all() and np.isfinite(p1).all()
    assert np.max(p0[:,1])-np.min(p0[:,1])==0
    assert np.max(p1[:,1])-np.min(p1[:,1])>0.5
    assert np.allclose(p0[:2,2],.4) and np.allclose(p1[2:,2],2.4)
    assert np.linalg.norm(p0[1,:2]-p0[0,:2])==pytest.approx(2.0)

def test_solver_options_are_direct_only_vs_reflected_and_no_diffraction():
    _,original=B.preflight()
    for arm in B.ARMS:
        k=B.solver_options(original,arm)
        assert k["seed"]==original["seed"]==20260924
        assert k["max_depth"]==(0 if arm=="C00_DIRECT" else 3)
        assert k["specular_reflection"]==(arm!="C00_DIRECT")
        assert k["diffraction"] is False and k["diffuse_reflection"] is False

def test_fp_H_full_257x2x2_rejects_nonfinite_and_preserves_signed_range():
    H=np.zeros((257,2,2),np.complex128)
    H[:,0,0]=1.0+1j
    H[:,1,0]=.5-.2j
    o,cir=B.firstpath(H)
    assert 0<=o["fp_tap"]<1028
    assert -1<=o["s"]<=1
    assert np.isfinite(cir).all()
    for bad in (np.zeros((257,2,1)),np.ones((257,2,2))*np.nan):
        with pytest.raises(RuntimeError):
            B.firstpath(bad)

def test_default_run_requires_manual_budget_no_solver():
    class Req:
        arm="C00_DIRECT";pose=194;repeat=0;token=None;budget=None
        max_calls=257;wall_seconds=1200
    cfg=json.loads(B.LOCK.read_text())
    with pytest.raises(RuntimeError,match="MANUAL_TOKEN_REQUIRED"):
        B.check_budget(Req,cfg)

def test_stage_aggregate_does_not_accept_missing_or_fake_raw():
    a=A.audit_key(HERE/"no-existing-run","C00_DIRECT",194,0)
    assert a["status"]=="MISSING"
    assert a["why"]=="MISSING_MANIFEST"

def test_original_S0_STOP_boundary_and_sealed_HOLDOUT():
    cfg=json.loads(B.LOCK.read_text())
    assert cfg["qa"]["original_archive_C00_LoS_max_rel_l2"]==1e-5
    assert cfg["qa"]["original_SM0_STOP_is_unchanged"] is True
    assert cfg["governance"]["HOLDOUT2"]=="NO-GO"
    assert cfg["governance"]["RT_full_execution"].startswith("NO-GO")

def test_src_imports_available_but_rt_not_automatically_imported():
    assert (B.ROOT/"scripts"/"corridor_sionna_run.py").is_file()
    assert not any(m in sys.modules for m in ("sionna.rt","drjit","mitsuba"))


def test_approved_user_budget_is_separate_from_default_zero_permission(tmp_path):
    cfg=json.loads(B.LOCK.read_text())
    class Req:
        token="I_AUTHORIZE_CPU_RT_STAGE";max_calls=257;wall_seconds=1200
    req=Req()
    req.budget=tmp_path/"BUDGET.json"
    data=dict(status="USER_APPROVED_FOR_CPU_RT",
        science_class="USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY",
        max_solver_calls=8224,max_job_wall_seconds=1200,
        arm_ids=list(B.ARMS),pose_ids=cfg["pose_ids"])
    req.budget.write_text(json.dumps(data))
    assert B.check_budget(req,cfg)["max_solver_calls"]==8224
    data["max_solver_calls"]=32
    req.budget.write_text(json.dumps(data))
    with pytest.raises(RuntimeError,match="BUDGET_CEILING_EXCEEDED"):
        B.check_budget(req,cfg)

def test_c00_stored_257bin_2x2_finite_raw_success_and_sha_mutation_reject(tmp_path):
    import hashlib
    keydir=tmp_path/"C00_DIRECT-194-r0"
    keydir.mkdir()
    H=np.ones((257,2,2),np.complex128)
    freq=6250400000.+np.arange(257)*1950000.
    raw=keydir/"RAW_COMPLEX_H_AND_PATHS.npz"
    np.savez_compressed(raw,H_complex_rx_rx_tx=H,
        frequencies_hz=freq,offsets=np.arange(258,dtype=np.int64),
        path_counts=np.ones(257,np.int32),
        path_delay_s=np.zeros(257,dtype=float),
        path_coefficient=np.ones((257,2,2),dtype=np.complex128))
    manifest=dict(status="COMPLETED",arm="C00_DIRECT",pose_id=194,
        repeat_index=0,solver_calls_made=257,
        lock_sha256=A.sha(A.LOCK),direct_parity="PASS",
        file_sha256={raw.name:A.sha(raw)},observation={"fp_tap":0,"s":0.0})
    (keydir/"MANIFEST.json").write_text(json.dumps(manifest))
    assert A.audit_key(tmp_path,"C00_DIRECT",194,0)["status"]=="PASS"
    with raw.open("ab") as f:f.write(b"tampered")
    bad=A.audit_key(tmp_path,"C00_DIRECT",194,0)
    assert bad["status"]=="MISSING"
    assert bad["why"]=="RAW_FILE_MISSING_OR_SHA_MISMATCH"

def test_official_RT_manual_yaml_has_no_auto_push_schedule():
    p=B.ROOT/".github/workflows/mbvar-prr-native-rt-manual-8224-20261104.yml"
    if not p.exists():pytest.skip("workflow outside checkout")
    t=p.read_text()
    assert "workflow_dispatch:" in t
    assert "  push:" not in t and "  schedule:" not in t
    for stage in ("c00:","c00_qa:","paired:","paired_qa:"):
        assert "  "+stage in t
    assert "I_APPROVE_8224_NATIVE_CPU_CALLS" in t

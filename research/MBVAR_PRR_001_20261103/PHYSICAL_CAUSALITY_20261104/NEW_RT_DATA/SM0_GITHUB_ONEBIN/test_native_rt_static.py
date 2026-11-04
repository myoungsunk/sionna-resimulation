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
    assert "  schedule:" not in t
    assert "  push:" in t
    assert "RT_EXECUTION_APPROVAL_EFFECTIVE.json" in t
    assert "    branches: [prepare/mbvar-prr-sm0-native-rt-runnable-20261104]" in t
    assert "native_rt_batch.py'" not in t.split("paths:",1)[1].split("  workflow_dispatch:",1)[0]
    for stage in ("c00:","c00_qa:","paired:","paired_qa:"):
        assert "  "+stage in t
    assert "I_APPROVE_8224_NATIVE_CPU_CALLS" in t


def test_mock_native_backend_exercises_full_257bin_output_without_sionna(monkeypatch,tmp_path):
    """Integration path mock, NOT a claim that physical PathSolver succeeded."""
    from types import SimpleNamespace
    cfg=json.loads(B.LOCK.read_text())
    original=dict(max_depth=3,seed=20260924,samples_per_src=100000,
                  max_num_paths_per_src=1000000,los=True,specular_reflection=True)
    bank=tmp_path/"banks";bank.mkdir()
    budget=tmp_path/"approved_budget.json"
    budget.write_text(json.dumps(dict(
        status="USER_APPROVED_FOR_CPU_RT",
        science_class="USER_AUTHORIZED_NONINDEPENDENT_EXPLORATORY",
        max_solver_calls=8224,max_job_wall_seconds=1200,
        arm_ids=list(B.ARMS),pose_ids=cfg["pose_ids"])))
    qa=tmp_path/"C00_QA.json"
    qa.write_text(json.dumps(dict(status="C00_257BIN_STRICT_PARITY_PASS",
                                  n_pass=8,lock_sha256=B.h(B.LOCK))))
    args=SimpleNamespace(arm="C01_FLOOR",pose=194,repeat=0,
                         bank=bank,budget=budget,token="I_AUTHORIZE_CPU_RT_STAGE",
                         max_calls=257,wall_seconds=1200,
                         c00_qa=qa,out=tmp_path/"C01_FLOOR-194-r0")
    monkeypatch.setattr(B,"preflight",lambda b:(cfg,original))
    monkeypatch.setattr(B,"check_runtime",lambda:{"mock_only":True})
    monkeypatch.setattr(B,"get_pose",lambda p:{"x":6.103209,"y":-.269105,"yaw_body_deg":-39.343083})
    import types
    class FakeCorridor:
        BANK_DIR=None
        @staticmethod
        def load_banks():
            x=np.load(B.ROOT/B.BLOCK/"freqs_hz.npy")
            return [{"freqs_hz":x},{"freqs_hz":x}]
        @staticmethod
        def make_ports(banks):return object(),object()
        @staticmethod
        def set_bin(scene,banks,tx,rx,i,f):return
    class FakeSolver:
        calls=0
        def __call__(self,scene,**kw):
            FakeSolver.calls+=1
            shape=(2,2,1)
            return SimpleNamespace(tau=np.array([5e-9]),
               a=(np.ones(shape,float),np.zeros(shape,float)),
               objects=np.zeros((1,1),int),
               interactions=np.zeros((1,1),int),
               valid=np.ones((1,1),bool))
    class FakeRT:
        PathSolver=FakeSolver
    monkeypatch.setattr(B,"imports",lambda:(FakeRT,FakeCorridor))
    monkeypatch.setattr(B,"build_scene",
        lambda *args:(object(),np.array([10.,0.,2.65]),
                      np.array([6.103209,-.269105,.45]),{"floor":"fake_mock"}))
    B.execute(args)
    assert FakeSolver.calls==257
    assert (args.out/"RAW_COMPLEX_H_AND_PATHS.npz").is_file()
    record=json.loads((args.out/"MANIFEST.json").read_text())
    assert record["solver_calls_made"]==257 and record["status"]=="COMPLETED"
    r=A.audit_key(tmp_path,"C01_FLOOR",194,0)
    assert r["status"]=="PASS"
    assert r["sum_path_count"]==257
    assert np.isfinite(r["signed_s"])

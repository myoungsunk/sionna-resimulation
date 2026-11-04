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

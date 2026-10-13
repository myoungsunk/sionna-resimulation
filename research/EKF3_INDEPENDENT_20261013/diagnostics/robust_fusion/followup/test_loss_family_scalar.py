"""Candidate scalar solver comparison; original kernel stays unchanged."""
import sys
import time
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import loss_family as old
import loss_family_scalar as scalar

@pytest.mark.parametrize('family,parameter',[('cauchy',.024),('cauchy',.1),('cauchy',1.),('cauchy',10.),
    ('student_t',3.),('student_t',10.),('student_t',100.)])
def test_random_parity(family,parameter):
    rng=np.random.default_rng(28451)
    for n in (1,2):
        for index in range(40):
            m=rng.normal(size=(3,3)); p=(m@m.T+np.eye(3))*.03
            h=rng.normal(size=(n,3))*10**rng.uniform(-2,1)
            if index==0: h[:]=0
            r=np.eye(n)*.01
            scale=old.student_scale(r,parameter) if family=='student_t' else r
            y=rng.normal(size=n)*.2
            reference=old.solve_map(y,h,p,scale,family,parameter)
            result=scalar.solve_map(y,h,p,scale,family,parameter)
            assert result['stationarity_norm']<=1e-7
            assert result['objective']<=reference['objective']+1e-10
            # Different nonconvex minima can yield better scalar objectives.
            if abs(result['objective']-reference['objective'])<1e-10:
                np.testing.assert_allclose(result['delta'],reference['delta'],atol=1e-6)

def test_100_solve_benchmark(capsys):
    rng=np.random.default_rng(726)
    examples=[]
    for i in range(100):
        n=1+i%2; family='cauchy' if i%3 else 'student_t'; parameter=1.5 if family=='cauchy' else 4.
        r=np.eye(n)*.01
        scale=old.student_scale(r,parameter) if family=='student_t' else r
        examples.append((rng.normal(size=n)*.15,rng.normal(size=(n,3)),np.diag([.03,.03,.02]),scale,family,parameter))
    t=time.perf_counter(); references=[old.solve_map(*args) for args in examples]; old_time=time.perf_counter()-t
    t=time.perf_counter(); results=[scalar.solve_map(*args) for args in examples]; scalar_time=time.perf_counter()-t
    max_objective=max(abs(a['objective']-b['objective']) for a,b in zip(references,results))
    assert max_objective<=1e-10
    with capsys.disabled():
        print(dict(old_100_s=old_time,scalar_100_s=scalar_time,speedup=old_time/scalar_time,max_objective_difference=max_objective))

def test_cached_rf_small_sample(capsys):
    from d6_d9_common import read_p0,original_lut,range_h,RS,RR
    from ekf3 import archived_direct_s_model
    cache_root=Path('D:/SLAM_bot/artifacts/EKF3_ROBUST_FUSION_20261013/M0')
    if not cache_root.is_dir(): pytest.skip('Frozen cache not present')
    p0=read_p0(); lut=original_lut(p0)
    case=next(c for c in p0['cases'] if c['id']=='R2_aA_m0')
    model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
        tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
    max_difference=0.; checked=0
    for channel in ('los','full'):
        with np.load(cache_root/(case['id']+'_'+channel+'.npz')) as cache:
            for k in np.linspace(0,len(cache['s'])-1,12,dtype=int):
                x=cache['truth'][k].copy()+np.array([.02,-.01,.01])
                hs,js=model(x); hr,jr=range_h(x,case['anchor'],case['robot_z_m'])
                for rm in ('B_OLD','E1_FULL_LORO'):
                    if rm not in cache: continue
                    y=np.array([cache['s'][k]-hs,cache[rm][k]-hr])
                    h=np.array([js,jr]); p=np.diag([.01,.01,.005]); r=np.diag([RS,RR])
                    if y@np.linalg.solve(h@p@h.T+r,y)>old.GATE_2D_99: continue
                    for family,parameter in (('cauchy',1.5),('student_t',4.)):
                        scale=old.student_scale(r,parameter) if family=='student_t' else r
                        reference=old.solve_map(y,h,p,scale,family,parameter)
                        result=scalar.solve_map(y,h,p,scale,family,parameter)
                        assert result['objective']<=reference['objective']+1e-10
                        difference=abs(result['objective']-reference['objective'])
                        max_difference=max(max_difference,difference); checked+=1
                        if difference<1e-10:
                            np.testing.assert_allclose(result['delta'],reference['delta'],atol=1e-6)
    assert checked>0
    with capsys.disabled(): print(dict(raw_rf_gated_solves=checked,max_objective_difference=max_difference))

"""Synthetic regression; does NOT claim real RF validation."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest

from dsreassess.causal_evidence import (
    centered_mean,get_windows,make_plan,replay_with_means,stage7,stage8,
    post_suffix_replay,score_suffix,CONTRACT_VERSION
)
from dsreassess.engine import replay
from dsreassess.io import CaseData,StageWriter,read_json
from dsreassess.numerics import transition,range_h


class FakeModel:
    def batch(self, X, case, gradient=True, return_diagnostics=False):
        X=np.asarray(X,float);n=len(X)
        a=np.asarray(case['anchor'],float);delta=X[:,:2]-a[:2]
        height=a[2]-case['robot_z_m']
        rr=np.sqrt((delta**2).sum(axis=1)+height**2)
        s=np.sin(X[:,2])+.025*X[:,0]-.015*X[:,1]
        h=np.column_stack([rr+case['b_old'],s]);H=np.zeros((n,2,4))
        H[:,0,:2]=delta/rr[:,None]
        H[:,1,0]=.025;H[:,1,1]=-.015;H[:,1,2]=np.cos(X[:,2])
        return (h,H) if gradient else (h,None)


class FakeCtx:
    def __init__(self,tmp_path):
        self.model=FakeModel()
        self.V=SimpleNamespace(INITIAL_POSE_STD=np.array([.1,.1,.02]),BIAS_PRIOR_STD=.005)
        self.cfg=SimpleNamespace(output_root=tmp_path,cases=('R2_aA_m45',),biases=('B0',))
        self.passes=pd.DataFrame([dict(case='R2_aA_m45',bias='B0',pass_id=1,start_s=7.4,end_s=12.6,
            window_start_s=0.,window_end_s=22.6,post_start_s=12.6,post_end_s=25.)])
        self._case=None
    def cases(self):yield self._case
    def first_pass(self,key,bias):
        z=self.passes[(self.passes.case==key)&(self.passes.bias==bias)&(self.passes.pass_id==1)]
        return z.iloc[0]
    def evidence_metadata(self):return {'synthetic':True}


def fake_data(tmp_path):
    ctx=FakeCtx(tmp_path)
    N=220;t=np.arange(N)*.2;truth=np.zeros((N,4));truth[0]=[0.,.15,.04,0.]
    controls={'ds_odom':np.r_[0.,np.full(N-1,.080)],
              'dtheta_gyro':np.zeros(N),'dt_s':np.r_[.2,np.full(N-1,.2)]}
    for k in range(1,N):
        truth[k],_,_=transition(truth[k-1],controls['ds_odom'][k],0.,.2)
    case={'id':'R2_aA_m45','route':'R2','anchor':[4.,0.,2.5],
          'robot_z_m':0.,'b_old':-.5315983906250129}
    h,_=ctx.model.batch(truth,case)
    er=.035*np.sin(.35*t)+.01*np.sin(4*t)
    es=.13*np.sin(.2*t)+.025*np.cos(2.*t)
    z=h+np.column_stack([er,es])
    R=np.zeros((N,2,2));R[:,0,0]=.06**2;R[:,1,1]=.15**2
    mask=np.ones(N,bool);mask[::17]=False
    d=CaseData(case,'B0',t,np.arange(N),truth,z,np.zeros(N),
               np.full(N,.018),np.full(N,.027),np.zeros(N),R,mask,controls,
               truth[0,:3].copy(),{},case['b_old'],{})
    # Real E1 store has 5 alphas. Reproduce only BB (0) and EXDS (4)
    bb=replay(ctx,d,'BB',mu_kind='BASE')
    mb=replay(ctx,d,'MB',mu_kind='EXDS')
    for field in ('x','P','prior','Pprior','K','H','h','nu','mu','R','acc'):
        v=getattr(bb,field);w=np.repeat(v[:,None,...],5,axis=1)
        w[:,4,...]=getattr(mb,field)
        d.ref[field]=w
    ctx._case=d
    return ctx,d


def test_centered_smoother_invariance():
    t=np.arange(41)*.2;r=np.sin(t)
    a,n=centered_mean(t,r,2.)
    assert a.shape==r.shape and np.all(n>=3)
    assert np.max(abs(a+(r-a)-r))<1e-14
    sel=(t>=2)&(t<=6)
    b,m=centered_mean(t,r,2.,eligibility=sel)
    assert np.all(b[~sel]==0) and np.all(m[~sel]==0)
    assert np.all(m[sel]>=3)
    with pytest.raises(ValueError):centered_mean(t,r,0.)


def test_windows_and_gt_oracle(tmp_path):
    ctx,d=fake_data(tmp_path);win=get_windows(ctx,d);plan=make_plan(ctx,d)
    assert win.post_start_k==win.exit_k+1
    assert np.all(win.post[win.post_start_k:win.end_k+1])
    assert np.array_equal(plan['windows'].core,win.core)
    assert np.max(abs(d.z[:,1]-plan['gt'][:,1]-plan['mu_s']['POL_CLEAN']))<1e-12
    assert np.max(abs(d.z[:,0]-plan['gt'][:,0]-plan['mu_r']['R_ORACLE']))<1e-12
    assert plan['nr'][win.expanded].min()>=3
    assert plan['slowr'][~win.expanded].max()==0


def test_factorial_baseline_parity_and_handoff(tmp_path):
    ctx,d=fake_data(tmp_path)
    w7=StageWriter(ctx,'07_rf_pol_factorial')
    stage7(ctx,w7)
    a=read_json(tmp_path/'07_rf_pol_factorial'/'RUN_STATUS.json')
    assert a['status']=='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION'
    assert len(read_json(tmp_path/'07_rf_pol_factorial'/'CHECKS.json'))>20
    s7=pd.read_csv(tmp_path/'07_rf_pol_factorial'/'SCORES.csv')
    assert s7.arm.nunique()==15 and len(s7)==60
    interactions=pd.read_csv(tmp_path/'07_rf_pol_factorial'/'FACTORIAL_INTERACTIONS.csv')
    assert len(interactions)==20
    for _,row in interactions.iterrows():
        assert abs(row['interaction']-(row['Y_A']-row['Y_B']-row['Y_C']+row['Y_D']))<1e-12
    w8=StageWriter(ctx,'08_post60_handoff')
    stage8(ctx,w8)
    s8=pd.read_csv(tmp_path/'08_post60_handoff'/'POST60_HANDOFF_SCORES.csv')
    assert len(s8)==24
    contrast=pd.read_csv(tmp_path/'08_post60_handoff'/'HANDOFF_STATE_P_INTERACTIONS.csv')
    assert len(contrast)==20
    assert contrast.metric.isin(['heading_rmse_deg','heading_signed_bias_deg','xy_rmse_m','e_tan_signed_cm','heading_nees']).all()
    assert len(read_json(tmp_path/'08_post60_handoff'/'CHECKS.json'))>8
    npz=tmp_path/'08_post60_handoff'/f'{d.key}_X_BASE_P_BASE_R_BASE_S_REAL_POST60.npz'
    with np.load(npz,allow_pickle=False) as tr:
        assert {'x','P','prior','Pprior','H','K','mu','nu','krnu','ksnu','R','dt_s','acc'}<=set(tr.files)
        np.testing.assert_allclose(tr['krnu']+tr['ksnu'],
            np.where(tr['acc'][:,None],np.einsum('nik,nk->ni',tr['K'],tr['nu']),0),atol=1e-11,rtol=0)


def test_original_mask_and_R_preserved(tmp_path):
    ctx,d=fake_data(tmp_path);p=make_plan(ctx,d)
    clone=replace(d,mu_b=p['mu_r']['NO_SLOW_R'],mu_s=p['mu_s']['POL_CLEAN'])
    assert np.array_equal(clone.z,d.z)
    assert np.array_equal(clone.R,d.R)
    assert np.array_equal(clone.mask,d.mask)
    assert clone.controls is d.controls
    assert clone.truth is d.truth
    assert clone.ref is d.ref


def test_post_suffix_matches_full_replay(tmp_path):
    ctx,d=fake_data(tmp_path);win=get_windows(ctx,d)
    for kind,mur in [('BASE',d.mu_b),('EXDS',d.mu_exds)]:
        original=replay(ctx,d,kind,mu_kind=kind)
        steps=post_suffix_replay(ctx,d,win.exit_k,win.end_k,
                                 original.x[win.exit_k],original.P[win.exit_k],mur,d.mu_s)
        ix=[a[0] for a in steps]
        np.testing.assert_allclose([a[1] for a in steps],original.x[ix],atol=1e-10,rtol=0)
        np.testing.assert_allclose([a[2] for a in steps],original.P[ix],atol=1e-10,rtol=0)
        sc=score_suffix(d,steps,arm='post')
        assert abs(sc['xy_rmse_m']**2-(sc['radial_rms_cm']**2+sc['tangential_rms_cm']**2)/10000)<1e-11


def test_next_gt_pass_truncates_post_window(tmp_path):
    ctx,d=fake_data(tmp_path)
    ctx.passes=pd.concat([ctx.passes,pd.DataFrame([dict(case='R2_aA_m45',bias='B0',
                              pass_id=2,start_s=19.,end_s=24.)])],ignore_index=True)
    win=get_windows(ctx,d)
    assert win.clip_reason=='NEXT_PASS'
    assert d.t[win.end_k]<19.
    assert all(d.t[np.flatnonzero(win.post)]>12.6)
    assert win.post.sum()>=10


def test_pass_clean_oracle_changes_only_first_crossing(tmp_path):
    ctx,d=fake_data(tmp_path)
    w=StageWriter(ctx,'07_rf_pol_factorial')
    stage7(ctx,w)
    win=get_windows(ctx,d);p=make_plan(ctx,d)
    with np.load(w.dir/f'{d.key}_PASS_CLEAN_BB.npz',allow_pickle=False) as z:
        mu=z['mu']
        np.testing.assert_allclose(mu[~win.core,0],d.mu_b[~win.core],atol=0,rtol=0)
        np.testing.assert_allclose(mu[~win.core,1],d.mu_s[~win.core],atol=0,rtol=0)
        np.testing.assert_allclose(mu[win.core,0],p['mu_r']['R_ORACLE'][win.core],atol=1e-12,rtol=0)
        np.testing.assert_allclose(mu[win.core,1],p['mu_s']['POL_CLEAN'][win.core],atol=1e-12,rtol=0)

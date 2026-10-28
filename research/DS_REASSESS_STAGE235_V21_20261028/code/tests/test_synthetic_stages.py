"""Synthetic end-to-end smoke; NOT a substitute for frozen RF/E1 real-data parity."""
from __future__ import annotations
from types import SimpleNamespace
from pathlib import Path
import numpy as np
import pandas as pd
from dsreassess.numerics import wrap,range_h
from dsreassess.io import CaseData,StageWriter
from dsreassess.engine import replay
from dsreassess.stage12 import stage1,stage2
from dsreassess.stage34 import stage3,stage4
from dsreassess.stage56 import stage5,stage6
from dsreassess.observability import fisher,first_pass_windows


class FakeSourceFFD:
    def batch(self,states,case,gradient=True,return_diagnostics=False):
        x=np.atleast_2d(states);n=len(x)
        h=np.zeros((n,2));H=np.zeros((n,2,4))
        dist=np.zeros(n)
        for i in range(n):
            h[i,0],H[i,0]=range_h(x[i,:2],case,b_old=0.)
            dist[i]=h[i,0]
        h[:,1]=.07*x[:,0]-.05*x[:,1]+.25*np.sin(x[:,2])
        H[:,1,0]=.07;H[:,1,1]=-.05;H[:,1,2]=.25*np.cos(x[:,2])
        if not gradient:H=None
        if return_diagnostics:
            return h,H,{'tap':np.floor(dist*3).astype(int),
                        'fp_margin':np.full(n,.5),'cells':np.zeros((n,3),int)}
        return h,H


class FakeCtx:
    def __init__(self,root):
        self.model=FakeSourceFFD()
        self.V=SimpleNamespace(INITIAL_POSE_STD=np.array([.1,.1,np.radians(5)]),BIAS_PRIOR_STD=np.radians(.1))
        self.cfg=SimpleNamespace(output_root=root,fd_stride=15,block_seconds=1.0,
                cov_shrink=.5,min_train_n=6,augmented_br_prior_std_m=.08,
                augmented_br_q_std_m_per_sqrt_s=0.,tangent_q_std_m_per_sqrt_s=.01,
                post_exit_seconds=3.)
        self._dataset=[]
    def cases(self):return iter(self._dataset)
    def native_fp(self,d):
        tap=np.arange(len(d.t))%6+20
        return {'tap':tap,'margin':np.full(len(d.t),.5),'s_fp':d.z[:,1],
                'raw_sample_index':np.arange(len(d.t),dtype=np.int64)}
    def first_pass(self,case,bias):
        return pd.Series({'window_start_s':8.,'window_end_s':17.,
                          'post_start_s':17.,'post_end_s':30.})
    def evidence_metadata(self):return {'synthetic_test_only':True}


def make_ctx(root):
    c=FakeCtx(root)
    rng=np.random.default_rng(8)
    for route,cid,xx in [('R2','R2_aA_m45',2.8),('R4','R4_aA_m0',3.1),('R5','R5_aA_m0',2.4)]:
        for bias in ('B0','L2'):
            n=42;t=np.arange(n)*1.0
            z0=np.column_stack([xx+.1*t,.2+.08*np.sin(t/2),.01*t,np.zeros(n)])
            case={'id':cid,'route':route,'anchor':[4.,0.,2.65],'robot_z_m':.45,'mount_deg':0}
            H0,_=c.model.batch(z0,case)
            meas=H0+rng.normal(size=H0.shape)*np.array([.02,.03])
            mu_b=np.full(n,.005);mu_ex=np.full(n,.004)
            mu_exds=np.full(n,.003);mu_s=np.zeros(n)
            R=np.zeros((n,2,2));R[:,0,0]=.02**2;R[:,1,1]=.03**2
            controls={'ds_odom':np.r_[0,np.diff(z0[:,0])],
                      'dtheta_gyro':np.r_[0,np.diff(z0[:,2])],
                      'dt_s':np.r_[1.,np.diff(t)]}
            d=CaseData(case,bias,t,np.arange(n),z0,meas,mu_b,mu_ex,mu_exds,mu_s,R,
                       (np.arange(n)%7)!=0,controls,np.array([xx,.2,0.]),{},0.,{})
            bb=replay(c,d,'BB',mu_kind='BASE')
            mb=replay(c,d,'MB',mu_kind='EXDS')
            fields=['x','P','prior','Pprior','K','H','h','nu','mu','R','acc']
            d.ref={key:np.stack([getattr(bb,key),getattr(bb,key),getattr(bb,key),getattr(bb,key),getattr(mb,key)],axis=1) for key in fields}
            c._dataset.append(d)
    return c


def test_six_stages_synthetic(tmp_path):
    ctx=make_ctx(tmp_path)
    for name,fn in [('01_range',stage1),('02_residuals',stage2),('03_RF_R_H',stage3),
                    ('04_CUT_RT_factorial',stage4),('05_full_observability',stage5),('06_layout_bias_Q',stage6)]:
        wr=StageWriter(ctx,name)
        fn(ctx,wr)
        assert (wr.dir/'RUN_STATUS.json').exists(),name
        assert not (wr.dir/'RUN_FAILURE.json').exists(),name


def test_geometry_gauge_not_spuriously_broken(tmp_path):
    ctx=make_ctx(tmp_path)
    d=next(ctx.cases())
    span=first_pass_windows(ctx,d)[0]
    r=fisher(ctx,d,span=span,nominal='GT',use_pol=False)
    assert r['rank']<4
    assert r['gauge_rayleigh_over_lambda_max']<1e-9
    assert r['sigma_terminal_tan_cm']==float('inf')
    p=fisher(ctx,d,span=span,nominal='GT',use_pol=True)
    assert p['gauge_rayleigh_over_lambda_max']>r['gauge_rayleigh_over_lambda_max']

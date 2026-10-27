from __future__ import annotations
import math
import numpy as np
import pytest
from dsreassess.numerics import transition,propagate,joint_update,augment,range_h,psd_check,wrap
from dsreassess.stage12 import acf_one,block_bootstrap_cov
from dsreassess.stage34 import fit_held_route_cov


def test_transition_jacobian_with_gyro_bias():
    x=np.array([2.1,0.3,0.7,0.015])
    y,F,G=transition(x,0.1,0.02,0.2)
    for k in range(4):
        e=np.zeros(4);e[k]=1e-6
        yp=transition(x+e,.1,.02,.2)[0]
        ym=transition(x-e,.1,.02,.2)[0]
        slope=(yp-ym)/(2e-6)
        slope[2]=wrap(yp[2]-ym[2])/(2e-6)
        assert np.allclose(slope,F[:,k],atol=2e-7,rtol=1e-6)
    for k in range(2):
        ds=[.1,.02]
        lo=ds.copy();hi=ds.copy();lo[k]-=1e-6;hi[k]+=1e-6
        slope=(transition(x,*hi,.2)[0]-transition(x,*lo,.2)[0])/(2e-6)
        assert np.allclose(slope,G[:,k],atol=2e-7,rtol=1e-6)


def test_predict_joseph_and_off_covariance():
    rng=np.random.default_rng(10)
    L=rng.normal(size=(4,4));P=L@L.T+.01*np.eye(4)
    x=np.array([4,0.2,.1,.003])
    xp,PP,F=propagate(x,P,.04,.003,.2)
    psd_check(PP)
    H=rng.normal(size=(2,4));R=np.array([[.015,.004],[.004,.08]])
    z=np.array([2.3,.3]);h=np.array([2,.1]);mu=np.array([.01,.02])
    accepted=joint_update(xp,PP,z,h,H,mu,R,True)
    rejected=joint_update(xp,PP,z,h,H,mu,R,False)
    assert np.array_equal(rejected.x,xp) and np.array_equal(rejected.P,PP)
    K=PP@H.T@np.linalg.inv(H@PP@H.T+R)
    assert np.allclose(accepted.K,K,atol=1e-12)
    assert np.allclose(accepted.x,xp+K@(z-h-mu),atol=1e-12)
    psd_check(accepted.P)
    assert np.min(np.linalg.eigvalsh(accepted.P))>-1e-11


def test_cut_only_tangent_range_column():
    P=np.eye(4);x=np.array([2.,1.,.3,0.]);h=np.zeros(2)
    H=np.array([[1,0,0,0],[.3,.1,1,0]])
    r=np.eye(2)*.1
    plain=joint_update(x,P,np.array([.1,.2]),h,H,np.zeros(2),r,True)
    ut=np.array([0.,1.])
    cut=joint_update(x,P,np.array([.1,.2]),h,H,np.zeros(2),r,True,tangent_cut_xy=ut)
    assert abs(cut.K[1,0])<1e-13
    assert np.allclose(plain.K[:,1],cut.K[:,1])
    assert np.allclose(plain.K[2:,0],cut.K[2:,0])
    assert np.linalg.eigvalsh(cut.P).min()>0


def test_augmented_range_bias_and_tangent_q():
    h=np.array([2.1,.04]);H=np.zeros((2,4))
    hh,HH=augment(h,H,.05)
    assert hh[0]==pytest.approx(2.15)
    assert HH[0,4]==1.0 and HH[1,4]==0
    x=np.array([3.,.5,0.,0.,.01]);P=np.eye(5)*.01
    a,_P,_=propagate(x,P,.02,0.,.2,tangent_q=1e-3,range_bias_q=1e-4,anchor_xy=np.array([4.,0.]))
    assert _P[4,4]>P[4,4]
    assert np.linalg.eigvalsh(_P).min()>0
    case={'anchor':[4.,0.,2.65],'robot_z_m':.45}
    h4,dr=range_h([3.,0.],case,b_old=-.531598390625)
    assert dr[2]==0 and dr[3]==0


def test_time_block_bootstrap_and_heldout_route():
    rng=np.random.default_rng(5);n=100
    ts=np.arange(n)*.2
    x=rng.normal(0,.1,size=n)
    y=.3*x+rng.normal(0,.02,size=n)
    assert acf_one(x,1)<1
    a,b,nb=block_bootstrap_cov(x,y,ts,seconds=2.,reps=50)
    assert nb>=4 and a<=b
    import pandas as pd
    rows=[]
    for route in ('R2','R4','R5'):
        for j in range(n):
            rows.append({'case':route,'route':route,'bias':'B0','arm':'BASE','sample':'all','distance_bin':'mid',
                         'er_m':x[j],'es':y[j]})
    df=pd.DataFrame(rows)
    cov,rec=fit_held_route_cov(df,target_route='R2',arm='BASE',dist_bin='mid',minimum=10)
    assert set(rec['train_routes'].split(','))=={'R4','R5'}
    assert np.linalg.eigvalsh(cov).min()>0


def test_correlated_R_equivalent_to_whitened_likelihood():
    rng=np.random.default_rng(100)
    B=rng.normal(size=(4,4));P=B@B.T+.5*np.eye(4)
    x=np.array([3.1,.4,.5,0.]);z=np.array([2.5,.12]);h=np.array([2.4,.08])
    H=np.array([[.8,.1,0.,0.],[.01,-.03,.3,0.]])
    R=np.array([[.04,.015],[.015,.09]])
    direct=joint_update(x,P,z,h,H,np.zeros(2),R,True)
    L=np.linalg.cholesky(R)
    # Fusing the Cholesky-whitened channels with identity noise must reproduce
    # exactly the posterior; the whitened K itself is not the native K.
    wh=joint_update(x,P,np.linalg.solve(L,z),np.linalg.solve(L,h),
                    np.linalg.solve(L,H),np.zeros(2),np.eye(2),True)
    assert np.allclose(direct.x,wh.x,atol=1e-12)
    assert np.allclose(direct.P,wh.P,atol=1e-12)

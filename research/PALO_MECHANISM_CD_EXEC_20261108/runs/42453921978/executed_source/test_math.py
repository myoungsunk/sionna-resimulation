"""Synthetic numerical QA only. No claim about PALO scientific performance."""
import json
import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from common import Engine, ALPHAS, DEG, RS, safe_path, checked_bytes, sha256, blob_sha, wrap, soften, allowed_intervals
from run_cd import initialize_arms, run_d_chunk, segment_end_index, ARMS


def fixture_engine():
    e=object.__new__(Engine)
    e.dt=2.;e.dp=2.;e.nt=46;e.np=180
    th=np.deg2rad(np.arange(46)*2)[:,None,None]
    a=np.deg2rad(np.arange(-180,180,2))[None,:,None]
    b=np.deg2rad(np.arange(-180,180,2))[None,None,:]
    e.lut=(.35*np.sin(th)*np.cos(a)+.30*np.cos(b)*np.cos(th)+.1*np.sin(a-b)).astype(float)
    e.case=dict(anchor=[10.,0.,2.65],robot_z_m=.3,mount_deg=0.)
    return e


def scalar_observe(e,x):
    u=x[0]-e.case['anchor'][0];v=x[1]-e.case['anchor'][1]
    h=e.case['anchor'][2]-e.case['robot_z_m'];rho2=max(u*u+v*v,1e-12);rho=math.sqrt(rho2)
    th=math.degrees(math.atan2(rho,h));tx=math.degrees(math.atan2(-v,u));rx=(math.degrees(math.atan2(-v,-u))-math.degrees(x[2])+180)%360-180
    fth=min(max(th/e.dt,0),e.nt-1-1e-9);fa=(tx+180)/e.dp;fb=(rx+180)/e.dp
    ii,jj,kk=math.floor(fth),math.floor(fa),math.floor(fb)
    ft,fx,fy=fth-ii,fa-jj,fb-kk
    val=0.;g=np.zeros(3)
    for di in (0,1):
        for dj in (0,1):
            for dk in (0,1):
                value=float(e.lut[ii+di,(jj+dj)%e.np,(kk+dk)%e.np])
                w0=ft if di else 1-ft;w1=fx if dj else 1-fx;w2=fy if dk else 1-fy
                val+=value*w0*w1*w2
                g[0]+=value*(1 if di else -1)*w1*w2/e.dt
                g[1]+=value*w0*(1 if dj else -1)*w2/e.dp
                g[2]+=value*w0*w1*(1 if dk else -1)/e.dp
    H=np.zeros(4)
    H[0]=g[0]*h/(rho2+h*h)*u/rho*DEG+g[1]*v/rho2*DEG-g[2]*v/rho2*DEG
    H[1]=g[0]*h/(rho2+h*h)*v/rho*DEG-g[1]*u/rho2*DEG+g[2]*u/rho2*DEG
    H[2]=-g[2]*DEG
    return val,H


class MathQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e=fixture_engine();cls.rng=np.random.default_rng(805109)
        cls.receipt=dict(scope='SYNTHETIC_ONLY; no frozen RF/NPZ scientific run',counts={},maximum_errors={})

    def test_01_scalar_batch_observation(self):
        x=self.rng.normal(size=(250,4));x[:,:2]*=4;x[:,2]*=3
        h,H,cl=self.e.observe(x)
        ref=[scalar_observe(self.e,v) for v in x]
        err=max(float(np.max(abs(h-np.array([r[0] for r in ref])))),float(np.max(abs(H-np.array([r[1] for r in ref])))))
        self.assertLess(err,1e-12)
        self.receipt['counts']['scalar_batch_observation']=250
        self.receipt['maximum_errors']['scalar_batch_observation']=err

    def test_02_soft_joseph_and_gain(self):
        n=200;x=self.rng.normal(size=(n,4));M=self.rng.normal(size=(n,4,4));P=M@M.transpose(0,2,1)+np.eye(4)*.01
        z=self.rng.normal(size=n)*.05;u,C,d=self.e.candidate(x,P,z)
        maximum=0.
        for alpha in ALPHAS:
            y,V=soften(x,P,u,C,d['step'],alpha)
            self.assertGreater(np.linalg.eigvalsh(V).min(),0)
            if alpha==0:
                self.assertTrue(np.allclose(V,P,atol=0,rtol=0));continue
            Ralpha=d['S']/alpha-(d['S']-RS)
            K=alpha*d['K'];A=np.eye(4)-K[:,:,None]*d['H'][:,None,:]
            direct=A@P@A.transpose(0,2,1)+Ralpha[:,None,None]*K[:,:,None]*K[:,None,:]
            maximum=max(maximum,float(np.max(abs(V-direct))))
            self.assertTrue(np.allclose(y[:,:2],x[:,:2]+K[:,:2]*d['nu'][:,None],atol=1e-12))
        self.assertLess(maximum,1e-11)
        self.receipt['counts']['soft_covariance_cases']=n*len(ALPHAS)
        self.receipt['maximum_errors']['soft_covariance']=maximum

    def test_03_intervals_and_circular_edges(self):
        cases=[]
        for _ in range(200):
            cases.append((self.rng.uniform(-np.pi,np.pi),self.rng.uniform(-4*np.pi,4*np.pi),self.rng.normal(size=2),self.rng.normal(size=2)))
        cases.extend([(np.deg2rad(170),np.deg2rad(40),np.array([1.,0]),np.array([-.2,0])),(0.,.1,np.ones(2),-np.ones(2))])
        checked=0
        for err,step,ep,dp in cases:
            hh,xx,both,best=allowed_intervals(err,step,ep,dp)
            for alpha in np.linspace(.00013,.99987,101):
                gh=err*err-float(wrap(err+alpha*step))**2
                gx=float(ep@ep-(ep+alpha*dp)@(ep+alpha*dp))
                if min(abs(gh),abs(gx))<1e-11:continue
                predicted=any(l<alpha<r for l,r in both)
                self.assertEqual(predicted,gh>0 and gx>0);checked+=1
            grid=np.linspace(0,1,2001)
            self.assertLessEqual(abs(float(wrap(err+best*step))),np.min(abs(wrap(err+grid*step)))+1e-12)
        self.receipt['counts']['interval_grid_checks']=checked

    def test_04_predict_mean_independent_of_P(self):
        x=self.rng.normal(size=(100,4));P=np.broadcast_to(np.eye(4),(100,4,4)).copy()
        y,V=self.e.advance(x,P,np.ones(100)*.04,np.linspace(-.05,.05,100),np.ones(100)*.2)
        y2,V2=self.e.advance(x,P*9,np.ones(100)*.04,np.linspace(-.05,.05,100),np.ones(100)*.2)
        self.assertTrue(np.array_equal(y,y2));self.assertGreater(np.linalg.eigvalsh(V).min(),0)
        self.receipt['counts']['motion_P_negative_controls']=100

    def test_05_arms_and_short_rollouts(self):
        e=fixture_engine();n=979;e.t=np.arange(n)*.2
        e.truth=np.c_[1+np.arange(n)*.04,np.zeros(n),np.zeros(n)]
        x=np.c_[e.truth,np.zeros(n)];x[:,2]=.02;x[:,1]=.05
        P=np.broadcast_to(np.diag([.01,.01,.01,.001]),(n,4,4)).copy()
        z=e.observe(np.c_[e.truth,np.zeros(n)])[0]
        e.trace={'full':{'z_s':z}}
        e.controls={('full','B0'):dict(ds_odom=np.full(n,.04),dtheta_gyro=np.zeros(n),dt_s=np.full(n,.2))}
        e.saved={('B0','s4'):dict(prior_X=x,prior_P=P)}
        X,C,d=initialize_arms(e,x[:3],P[:3],z[:3])
        self.assertTrue(np.array_equal(X[:,0],X[:,2]));self.assertTrue(np.array_equal(X[:,1],X[:,3]))
        with tempfile.TemporaryDirectory() as tmp:
            for future in ('off','s4'):
                rows,ex,qa=run_d_chunk(e,'B0','s4',[201,490,525,962,973],future,Path(tmp)/(future+'.npz'))
                self.assertGreater(len(rows),0);self.assertGreater(len(ex),0)
                self.assertGreater(qa['min_cov_eigenvalue'],0)
                if future=='off':self.assertEqual(qa['negative_control_max'],0.)
                # k490 at 98sec cannot get 5/10/20 sec labels across t=100.
                self.assertFalse(any(r['k']==490 and r['horizon_s']>=5 for r in rows))
                # End-of-file events never receive 10/20sec labels.
                self.assertFalse(any(r['k']==973 and r['horizon_s']>=5 for r in rows))
                self.receipt['counts']['synthetic_rollout_branches']=self.receipt['counts'].get('synthetic_rollout_branches',0)+5*len(ARMS)

    def test_06_manifest_and_path_fail_closed(self):
        b=b'test';rec=dict(bytes=len(b),sha256=sha256(b),git_blob=blob_sha(b))
        checked_bytes(b,rec,'test')
        with self.assertRaises(AssertionError):checked_bytes(b'evil',rec,'mutation')
        for rel in ('../../escape','/absolute'):
            with self.assertRaises(ValueError):safe_path(Path('/tmp'),rel)
        with self.assertRaises(ValueError):self.e.candidate(np.zeros(4),np.eye(4),np.nan)
        with self.assertRaises(ValueError):self.e.advance(np.zeros(4),np.eye(4),.1,.0,0.)
        self.receipt['counts']['manifest_and_input_negative_controls']=5

    @classmethod
    def tearDownClass(cls):
        Path('SYNTHETIC_QA.json').write_text(json.dumps(cls.receipt,indent=2)+'\n')

if __name__=='__main__':unittest.main(verbosity=2)

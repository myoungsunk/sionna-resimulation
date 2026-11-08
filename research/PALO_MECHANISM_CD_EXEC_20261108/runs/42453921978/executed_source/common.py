"""Pinned inputs and vectorized copies of the frozen scalar model.

Ground truth is never consumed by predict(), observe(), or candidate().
All angles are radians internally. Batch implementation must pass C0 parity
against pinned S4/DR4 arrays before scientific interventions run.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
import numpy as np

REPO = 'myoungsunk/sionna-resimulation'
INPUT_SHA = '4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5'
ORACLE_SHA = 'eaf9a386ec8da9cb58aaeec2e3481563de0c0a7f'
GAP_SHA = '16450dc14366ba4ed2cb4e151952493f0efc944f'
DESIGN_SHA = '657af33d5bd52c1fc706546b18c75a0a8901312b'
POL = 'research/POL_HEADING_RESEARCH_20261107/'
EXACT = 'research/PALO_EXACT_ORACLE_20261107/'
GAP = 'research/PALO_GAP_STUDY_20261107/'
FROZEN = 'experiments/POL_FGO_CORR_20261106_v1/frozen/repo'
LEVELS = ('B0', 'L0', 'L1', 'L2')
BIAS_DEG_S = dict(B0=0.0, L0=.01, L1=.05, L2=.20)  # scoring only
RS = .0081
GATE = 6.6348966010212145
ALPHAS = (0., .05, .10, .25, .50, 1.)
DEG = 180. / np.pi

def wrap(x):
    return (np.asarray(x) + np.pi) % (2*np.pi) - np.pi

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def blob_sha(b: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')

def get_bytes(sha: str, path: str) -> bytes:
    url = f'https://raw.githubusercontent.com/{REPO}/{sha}/{path}'
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as f:
                return f.read()
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f'FETCH_FAILED {sha}:{path}: {last}')

def safe_path(root: Path, rel: str) -> Path:
    parts = PurePosixPath(rel)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:
        raise ValueError(f'Unsafe manifest path: {rel}')
    return root.joinpath(*parts.parts)

def checked_bytes(b, rec, context):
    assert len(b) == rec['bytes'], (context, 'byte_count')
    assert sha256(b) == rec['sha256'], (context, 'sha256')
    assert blob_sha(b) == rec['git_blob'], (context, 'git_blob')
    assert not b.startswith(b'version https://git-lfs.github.com/spec'), (context, 'LFS_POINTER')

def download_inputs(cache: Path, output: Path):
    """Only immutable refs; every payload checked against its pinned manifest."""
    cache.mkdir(parents=True, exist_ok=True)
    manifest_b = get_bytes(ORACLE_SHA, EXACT+'INPUT_MANIFEST.json')
    assert blob_sha(manifest_b) == 'a0cd935157834fe815540685d32bf323b9182d11'
    manifest = json.loads(manifest_b)
    assert manifest['commit'] == INPUT_SHA
    delivery_b = get_bytes(GAP_SHA, GAP+'DELIVERY_MANIFEST.json')
    assert blob_sha(delivery_b) == 'ad88da9b73f8209a6b1c587d8e347d2590cee3d1'
    delivery = json.loads(delivery_b)['files']
    jobs = []
    for rec in manifest['files']:
        assert rec['path'].startswith(POL)
        rel = rec['path'][len(POL):]
        jobs.append((INPUT_SHA, rec['path'], 'pol/'+rel, rec))
    for lv in LEVELS:
        for donor in ('s4', 'dr', 'heading'):
            path = f'results/trajectories/baseline_{lv}_{donor}.npz'
            jobs.append((GAP_SHA, GAP+path, 'gap/'+path, delivery[path]))
    def one(job):
        sha, remote, local, rec = job
        dest = safe_path(cache, local)
        b = dest.read_bytes() if dest.exists() else get_bytes(sha, remote)
        checked_bytes(b, rec, remote)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b)
        return dict(commit=sha, path=remote, local=local, **{k:rec[k] for k in ('bytes','sha256','git_blob')})
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipt = list(pool.map(one, jobs))
    output.mkdir(parents=True, exist_ok=True)
    (output/'ORIGINAL_INPUT_MANIFEST.json').write_bytes(manifest_b)
    dump(output/'SOURCE_MANIFEST.json', dict(input_commit=INPUT_SHA, oracle_commit=ORACLE_SHA,
         gap_commit=GAP_SHA, design_commit=DESIGN_SHA, files=receipt))
    return receipt

def load_npz(p):
    with np.load(p, allow_pickle=False) as f:
        return {k:f[k] for k in f.files}

class Engine:
    def __init__(self, cache):
        self.root = Path(cache)/'pol'
        frozen = self.root/FROZEN
        mod = frozen/'research/EKF4_RANGE_S_STAGED_20261014'
        sys.path.insert(0, str(mod))
        self.core = importlib.import_module('core')
        adapter = importlib.import_module('p3_rf_adapter4')
        self.scalar_lut = adapter.FrozenLut(root=frozen)
        m = json.loads((frozen/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
        self.case = next(c for c in m['cases'] if c['id']=='R2_aB_m0')
        self.lut = self.scalar_lut.s
        self.dt = self.scalar_lut.dt
        self.dp = self.scalar_lut.dp
        self.nt, self.np, _ = self.lut.shape
        self.trace = {ch:load_npz(self.root/f'inputs/original_run/verified_inputs/R2_aB_m0_{ch}_seed0_ONE_STEP.npz')
                      for ch in ('los','full')}
        self.t = self.trace['full']['t_s']
        self.truth = self.trace['full']['truth_for_offline_scoring_only']
        assert len(self.t)==979 and np.all(np.diff(self.t)>0)
        assert np.allclose(np.diff(self.t), .2, rtol=0, atol=1e-12)
        for key in ('t_s','pose_id','truth_for_offline_scoring_only'):
            assert np.array_equal(self.trace['los'][key], self.trace['full'][key]), key
        self.controls = {(ch,lv):load_npz(self.root/f'experiments/POL_FGO_CORR_20261106_v1/outputs/controls_{ch}_{lv}.npz')
                         for ch in ('los','full') for lv in LEVELS}
        self.original = {(ch,lv):load_npz(self.root/f'inputs/original_run/results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz')
                         for ch in ('los','full') for lv in LEVELS}
        self.saved = {(lv,d):load_npz(Path(cache)/f'gap/results/trajectories/baseline_{lv}_{d}.npz')
                      for lv in LEVELS for d in ('s4','dr','heading')}
        for a in self.saved.values():
            for key, value in [('t',self.t),('truth',self.truth),('pose_id',self.trace['full']['pose_id'])]:
                assert np.array_equal(a[key],value), key
            assert np.array_equal(a['X'],np.where(a['accepted'][:,None],a['candidate_X'],a['prior_X']))
            assert np.array_equal(a['P'],np.where(a['accepted'][:,None,None],a['candidate_P'],a['prior_P']))
            assert np.linalg.eigvalsh(a['P']).min()>0

    def initial(self, ch, lv):
        x = np.r_[self.controls[ch,lv]['initial_pose'], 0.]
        P = np.diag(np.array([.1,.1,np.deg2rad(5.),np.deg2rad(.1)])**2)
        return x,P

    def observe(self, x):
        """Vectorized, exact trilinear interpolation/chain rule of FrozenLut."""
        x = np.asarray(x,float)
        if x.shape[-1]!=4 or not np.isfinite(x).all():raise ValueError('Invalid observation state')
        ax,ay,az = self.case['anchor']
        u,v = x[...,0]-ax, x[...,1]-ay
        height = az-self.case['robot_z_m']
        r2 = np.maximum(u*u+v*v,1e-12); r = np.sqrt(r2)
        theta = np.arctan2(r,height)*DEG
        tx = np.arctan2(-v,u)*DEG
        rx = (np.arctan2(-v,-u)*DEG-(x[...,2]*DEG+self.case['mount_deg'])+180.)%360.-180.
        traw = theta/self.dt
        clip = (traw<0)|(traw>self.nt-1-1e-9)
        t = np.clip(traw,0.,self.nt-1-1e-9)
        a,b = (tx+180.)/self.dp,(rx+180.)/self.dp
        i = np.floor(t).astype(int); jf,kf = np.floor(a),np.floor(b)
        ft,fa,fb = t-i,a-jf,b-kf
        j,k = jf.astype(int)%self.np,kf.astype(int)%self.np
        j1,k1 = (j+1)%self.np,(k+1)%self.np; i1=i+1
        S=self.lut
        c000,c001,c010,c011 = S[i,j,k],S[i,j,k1],S[i,j1,k],S[i,j1,k1]
        c100,c101,c110,c111 = S[i1,j,k],S[i1,j,k1],S[i1,j1,k],S[i1,j1,k1]
        c00,c01 = c000*(1-fb)+c001*fb,c010*(1-fb)+c011*fb
        c10,c11 = c100*(1-fb)+c101*fb,c110*(1-fb)+c111*fb
        c0,c1=c00*(1-fa)+c01*fa,c10*(1-fa)+c11*fa
        val=c0*(1-ft)+c1*ft
        gt=(c1-c0)/self.dt
        ga=((c01-c00)*(1-ft)+(c11-c10)*ft)/self.dp
        gb=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/self.dp
        H=np.zeros(x.shape,float)
        H[...,0]=gt*height/(r2+height*height)*u/r*DEG+ga*v/r2*DEG-gb*v/r2*DEG
        H[...,1]=gt*height/(r2+height*height)*v/r*DEG-ga*u/r2*DEG+gb*u/r2*DEG
        H[...,2]=-gb*DEG
        return val,H,clip

    def candidate(self,x,P,z):
        x=np.asarray(x,float);P=np.asarray(P,float)
        if P.shape[-2:]!=(4,4) or not np.isfinite(P).all() or not np.isfinite(z).all():raise ValueError('Invalid candidate inputs')
        h,H,clip=self.observe(x)
        nu=np.asarray(z)-h
        ph=np.einsum('...ij,...j->...i',P,H)
        S=np.einsum('...i,...i->...',H,ph)+RS
        if not np.isfinite(S).all() or np.any(S<=0):raise ValueError('Invalid innovation covariance')
        K=ph/S[...,None]
        step=K*nu[...,None]
        y=np.asarray(x)+step; y[...,2]=wrap(y[...,2])
        A=np.eye(4)-K[..., :,None]*H[...,None,:]
        C=A@P@np.swapaxes(A,-1,-2)+RS*K[..., :,None]*K[...,None,:]
        C=(C+np.swapaxes(C,-1,-2))/2
        if not np.isfinite(y).all() or not np.isfinite(C).all():raise ValueError('Nonfinite candidate output')
        return y,C,dict(h=h,H=H,nu=nu,S=S,K=K,step=step,nis=nu*nu/S,clip=clip)

    def advance(self,x,P,ds,gyro,dt):
        x=np.asarray(x);P=np.asarray(P)
        ds,gyro,dt=np.asarray(ds),np.asarray(gyro),np.asarray(dt)
        if not all(np.isfinite(v).all() for v in (x,P,ds,gyro,dt)) or np.any(dt<=0):raise ValueError('Invalid motion inputs')
        a=gyro-x[...,3]*dt
        small=np.abs(a)<1e-4
        h=np.where(small,1.,a/2)
        c=np.where(small,1-a*a/24+a**4/1920-a**6/322560,np.sin(h)/h)
        dc=np.where(small,-a/12+a**3/480-a**5/53760,(h*np.cos(h)-np.sin(h))/(2*h*h))
        ph=x[...,2]+a/2;co,si=np.cos(ph),np.sin(ph)
        dx,dy=ds*c*co,ds*c*si
        vx,vy=ds*(dc*co-c*si/2),ds*(dc*si+c*co/2)
        y=x.copy();y[...,0]+=dx;y[...,1]+=dy;y[...,2]=wrap(x[...,2]+a)
        F=np.broadcast_to(np.eye(4),P.shape).copy()
        F[...,0,2]=-dy;F[...,1,2]=dx;F[...,0,3]=-dt*vx;F[...,1,3]=-dt*vy;F[...,2,3]=-dt
        g0=np.zeros_like(x);g1=np.zeros_like(x)
        g0[...,0]=c*co;g0[...,1]=c*si
        g1[...,0]=vx;g1[...,1]=vy;g1[...,2]=1.
        q0=2e-5*np.abs(ds);q1=np.deg2rad(.015)**2*dt
        C=F@P@np.swapaxes(F,-1,-2)+q0[...,None,None]*g0[..., :,None]*g0[...,None,:]+q1[...,None,None]*g1[..., :,None]*g1[...,None,:]
        return y,(C+np.swapaxes(C,-1,-2))/2

def soften(x,P,candidate,C,step,alpha):
    """Increase observation variance; do not keep full-update P with scaled mean."""
    y=np.asarray(x)+alpha*np.asarray(step);y[...,2]=wrap(y[...,2])
    V=P-alpha*(P-C)
    return y,(V+np.swapaxes(V,-1,-2))/2

def errors(x,truth):
    e=np.asarray(x)[...,:3]-np.asarray(truth);e[...,2]=wrap(e[...,2])
    return e

def score(x,P,truth):
    e=errors(x,truth);h=e[...,2];xy2=np.sum(e[...,:2]**2,axis=-1)
    xynees=np.einsum('...i,...i->...',e[...,:2],np.linalg.solve(P[...,:2,:2],e[...,:2,None])[...,0])
    return dict(heading_error_rad=h,xy_error_m=np.sqrt(xy2),heading_nees=h*h/P[...,2,2],xy_nees=xynees,
                heading_sigma_rad=np.sqrt(P[...,2,2]),xy_cov_trace=np.trace(P[...,:2,:2],axis1=-2,axis2=-1))

def sign_label(g):
    return np.where(np.asarray(g)>1e-10,1,np.where(np.asarray(g)<-1e-10,-1,0))

def allowed_intervals(e,d,ep,dp):
    """Exact circular heading intervals, intersected with XY's quadratic interval.
    Bounds are open where gain is zero. Returned intervals are clipped to [0,1].
    Ground-truth errors are diagnostic inputs, never a real selector's inputs.
    """
    e=float(wrap(e));d=float(d);a=abs(e)
    if abs(d)<1e-15 or a<1e-15:
        hh=[]
    else:
        lo,hi=sorted([e,e+d])
        m0=math.ceil((lo-a)/(2*np.pi));m1=math.floor((hi+a)/(2*np.pi))
        if m1-m0>10000:raise RuntimeError('UNBOUNDED_CIRCULAR_CANDIDATE')
        hh=[]
        for m in range(m0,m1+1):
            u,v=sorted([(2*np.pi*m-a-e)/d,(2*np.pi*m+a-e)/d])
            u,v=max(0.,u),min(1.,v)
            if v-u>1e-14:hh.append((u,v))
    q=float(np.dot(dp,dp));p=float(np.dot(ep,dp))
    xx=[] if q<=1e-30 or p>=0 else [(0.,min(1.,-2*p/q))]
    both=[]
    for a0,a1 in hh:
        for b0,b1 in xx:
            u,v=max(a0,b0),min(a1,b1)
            if v-u>1e-14:both.append((u,v))
    candidates=[0.,1.]
    if abs(d)>1e-15:
        lo,hi=sorted([e,e+d])
        for m in range(math.ceil(lo/(2*np.pi)),math.floor(hi/(2*np.pi))+1):
            candidates.append(float((2*np.pi*m-e)/d))
    best=min(candidates,key=lambda alpha:(abs(float(wrap(e+alpha*d))),alpha))
    return hh,xx,both,best

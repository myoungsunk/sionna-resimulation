"""Frozen Office -> Corridor POWER/PCIR/PWIDE transfer primitives.

All functions are pure or explicitly separated by phase. Importing this module
NEVER downloads data, trains a model, or evaluates target routes.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

OFFSETS = (-8, -4, -2, -1, 1, 2, 4, 8)
C0 = 299792458.0
B_OLD = -0.5315983906250129
R0_R = .0068578637
R0_S = .0081
P_FEATURES = ['sF_+0','log_fp_power','fp_full'] + [f'sF_{o:+d}' for o in OFFSETS] + [f'ds_{o:+d}' for o in OFFSETS]


def load_lock(path: Path | str | None = None) -> dict:
    p = Path(path) if path else Path(__file__).with_name('lock.json')
    lock = json.loads(p.read_text(encoding='utf-8'))
    if set(lock['paths']) != {'O01','O02','O03'}: raise ValueError('LOCK_OFFICE_ROUTE_SET')
    return lock


def sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1024*1024),b''): h.update(buf)
    return h.hexdigest()


def verify_digest(path: Path | str, expected: str) -> str:
    actual = sha256(path)
    if actual != expected.removeprefix('sha256:').lower():
        raise ValueError(f'SHA256_MISMATCH: {Path(path).name}: expected={expected} actual={actual}')
    return actual


def download_release(route: str, cache_dir: Path, lock: dict) -> Path:
    """Explicitly invoked only by CLI 'fetch'; not on import or in 'train'."""
    meta = lock['paths'][route]
    dest = cache_dir / meta['archive']
    cache_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        verify_digest(dest,meta['archive_sha256']);return dest
    url = f"{lock['release_root']}/{meta['tag']}/{meta['archive']}"
    partial = dest.with_suffix(dest.suffix+'.partial')
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'office-corridor-frozen-transfer'}),timeout=90) as src, partial.open('wb') as out:
            while True:
                data=src.read(4*1024*1024)
                if not data: break
                out.write(data)
        verify_digest(partial,meta['archive_sha256'])
        partial.rename(dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest


def safe_extract_tar(tar_path: Path, output: Path, expected_sha: str) -> Path:
    """Tar extraction rejects links, traversal, devices and overwrite attempts."""
    verify_digest(tar_path,expected_sha)
    output.mkdir(parents=True,exist_ok=True)
    prefix=output.resolve()
    with tarfile.open(tar_path,mode='r:gz') as ar:
        for member in ar.getmembers():
            if not (member.isdir() or member.isfile()): raise ValueError('TAR_UNSUPPORTED_MEMBER:'+member.name)
            dest=(output/member.name).resolve()
            if dest == prefix or prefix not in dest.parents: raise ValueError('TAR_PATH_ESCAPE:'+member.name)
            if member.isdir():
                dest.mkdir(parents=True,exist_ok=True)
                continue
            if dest.exists(): raise FileExistsError('NO_OVERWRITE:'+str(dest))
            dest.parent.mkdir(parents=True,exist_ok=True)
            fin=ar.extractfile(member)
            if fin is None: raise ValueError('TAR_NO_CONTENT:'+member.name)
            with fin, dest.open('wb') as fdst:
                while True:
                    buf=fin.read(1024*1024)
                    if not buf: break
                    fdst.write(buf)
    return output


def import_official_loader(audit_checkout: Path):
    """Use exact audited 2026-10-20 T2 pose/receipt/clock implementation."""
    root=Path(audit_checkout).resolve()
    path=root/'research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py'
    if not path.is_file(): raise FileNotFoundError('PINNED_T2_PREPARE_MISSING:'+str(path))
    import importlib.util
    spec=importlib.util.spec_from_file_location('transfer_official_t2_prep',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def load_source_ffd(checkout: Path):
    """Frozen source-model with the RF PHY bank, never an Office-learned LUT."""
    root=Path(checkout).resolve()
    for item in [
        'research/EKF4_RANGE_S_STAGED_20261014',
        'research/FFD_P0P3_20261016',
        'research/R5_N4B_20261015',
        'research/PHYSICS_RS_STAGED_20261015/code',
        'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
    ]:
        p=str(root/item)
        if p not in sys.path:sys.path.insert(0,p)
    # Frozen FFD source-bank assets are external to Git; never silently
    # substitute new banks or a corridor-trained lookup table.
    bankroot=root.parent
    expected=['LP_plus45_bank.npz','LP_minus45_bank.npz','BANK_MANIFEST.json']
    missing=[str(bankroot/name) for name in expected if not (bankroot/name).is_file()]
    if missing:raise FileNotFoundError('PINNED_FFD_BANK_ASSETS_MISSING: '+', '.join(missing))
    (bankroot/'ffd_p0p3/out').mkdir(parents=True,exist_ok=True)
    from source_model import SourceFFD
    return SourceFFD()


def expected_frequencies(lock: dict) -> np.ndarray:
    return lock['frequency_start_hz']+np.arange(lock['frequency_count'])*lock['frequency_step_hz']


def observe_port(H: np.ndarray, freqs: np.ndarray) -> pd.DataFrame:
    """Frozen Hann 4N IFFT, strongest-port 30% detector and SAME FP on both RX.

    H is [radio,frequency,rx2], already selecting the original TX+ channel.
    Offset features are defined relative to Full FP, with NaN at unavailable taps.
    """
    h=np.asarray(H)
    f=np.asarray(freqs,dtype=float)
    if h.ndim!=3 or h.shape[1:]!=(len(f),2) or len(f)!=257:
        raise ValueError('H_PORT_SHAPE_OR_FREQUENCY_COUNT')
    if not np.isfinite(h).all() or np.any(np.diff(f)<=0) or not np.allclose(np.diff(f),np.diff(f)[0],rtol=1e-10,atol=1e-5):
        raise ValueError('H_FREQ_NONFINITE_OR_GRID')
    n,nf,_=h.shape
    win=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    cir=np.fft.ifft(h*win[None,:,None],n=4*nf,axis=1)*nf
    p=np.abs(cir)**2;a=np.abs(cir)
    row=np.arange(n)
    strong_port=np.argmax(np.max(a,axis=1),axis=1)
    strong=a[row,:,strong_port]
    peak=strong.max(axis=1)
    if np.any(peak<=0):raise ValueError('NO_FIRST_PATH_ENERGY')
    fp=np.argmax(strong>=.3*peak[:,None],axis=1)
    sum_fp=p[row,fp].sum(axis=1)
    if np.any(sum_fp<=0):raise ValueError('ZERO_FIRST_PATH_POWER')
    step=1/(4*nf*(f[1]-f[0]))
    data={'range_m':fp*step*C0,'s_fp':(p[row,fp,0]-p[row,fp,1])/sum_fp,
          'fp_full':fp.astype(int),'log_fp_power':np.log10(sum_fp)}
    data['sF_+0']=data['s_fp'].copy()
    for o in OFFSETS:
        at=fp+o
        good=(at>=0)&(at<4*nf)
        vals=np.full(n,np.nan,dtype=float)
        ii=np.where(good)[0]
        power=p[ii,at[ii]]
        den=power.sum(axis=1)
        vals[ii]=np.divide(power[:,0]-power[:,1],den,out=np.full(len(ii),np.nan),where=den>0)
        data[f'sF_{o:+d}']=vals
        data[f'ds_{o:+d}']=vals-data['s_fp']
    return pd.DataFrame(data)


def source_dataset_one(route_root: Path, route: str, audit_checkout: Path, model: Any, lock: dict) -> tuple[pd.DataFrame,dict]:
    """Visible-LoS Office FULL training rows, never blocked target oracle rows."""
    canon=import_official_loader(audit_checkout)
    prepared=canon.prepare_new_route(Path(route_root),route)
    m=lock['paths'][route]
    if prepared['metadata']['motion_n']!=m['motion_n'] or prepared['metadata']['rf_n']!=m['rf_n']:
        raise ValueError('OFFICIAL_POSE_COUNTS_CHANGED')
    assert len(prepared['cases'])==1 and prepared['cases'][0]['case_id']==f'{route}_O0_M45_FULL'
    case=prepared['cases'][0];pose=pd.read_csv(prepared['metadata']['radio_path'])
    for label in ('H_FULL.npy','H_DIRECT_LOS.npy','LOS_EXISTS.npy'):
        verify_digest(Path(case[{'H_FULL.npy':'full_path','H_DIRECT_LOS.npy':'los_path','LOS_EXISTS.npy':'los_exists_path'}[label]]),m['files'][label])
    verify_digest(Path(case['radio_path']),m['files']['RADIO_POSE.csv'])
    full=np.load(case['full_path'],mmap_mode='r',allow_pickle=False)
    los=np.load(case['los_path'],mmap_mode='r',allow_pickle=False)
    flags=np.asarray(case['los_exists'],bool)
    n=m['rf_n'];expected_shape=(n,257,2,2)
    if full.shape!=expected_shape or los.shape!=expected_shape: raise ValueError('SOURCE_RF_SHAPE_CHANGED')
    fpath=list(Path(case['full_path']).parent.glob('FREQUENCIES_HZ.npy'))
    if len(fpath)!=1:raise ValueError('SOURCE_FREQUENCY_ARRAY_MISSING')
    freqs=np.load(fpath[0],allow_pickle=False)
    if not np.array_equal(freqs,expected_frequencies(lock)):raise ValueError('SOURCE_FREQUENCY_GRID_NOT_FROZEN')
    if np.any(~np.isfinite(full)):raise ValueError('SOURCE_FULL_NOT_FINITE')
    if np.any(~np.isfinite(los[flags])):raise ValueError('SOURCE_DIRECT_LOS_NOT_FINITE_ON_VISIBLE')
    obs=[]
    for j in range(0,n,64):obs.append(observe_port(full[j:j+64,:,:,0],freqs))
    q=pd.concat(obs,ignore_index=True)
    q['case']=case['case_id'];q['route']=route;q['scene']='OFFICE_E'
    q['pose_id']=pose['pose_id'].to_numpy(int)
    q['t_s']=pose['t_s'].to_numpy(float);q['los_exists']=flags
    for col,src in [('x_eval','x_m'),('y_eval','y_m')]:q[col]=pose[src].to_numpy(float)
    q['yaw_body_deg']=pose['yaw_body_deg'].to_numpy(float)
    q['mount_deg']=45.;q['anchor_id']='O0';q['anchor_x_m']=5.;q['anchor_y_m']=2.2
    q['channel']='full'
    q['sample_hash']=m['archive_sha256']
    # In-source labels are built ONLY on physically LoS-visible RF snapshots.
    states=np.c_[pose.x_m,pose.y_m,np.deg2rad(pose.yaw_body_deg),np.zeros(n)]
    conf={'id':case['case_id'],'anchor':lock['office_anchor_m'],'robot_z_m':.45,'mount_deg':45.}
    predicted=np.concatenate([model.batch(states[i:i+32],conf,gradient=False)[0] for i in range(0,n,32)])
    q['h_s_gt_source']=predicted[:,1]
    q['e_r']=q['range_m']-predicted[:,0]
    q['e_s']=q['s_fp']-predicted[:,1]
    q['d0_gt_source']=q['e_s']
    q.loc[~flags,['e_r','e_s','d0_gt_source','h_s_gt_source']]=np.nan
    # POWER only needs q and two labels; PWIDE offset NaNs use the pinned
    # training-fold median imputation, not sample deletion by CIR availability.
    finite_core=np.isfinite(q[['log_fp_power','s_fp','e_r','e_s']].to_numpy(float)).all(axis=1)
    q['valid_for_training']=flags & finite_core
    q['pwide_feature_imputations']=q[P_FEATURES].isna().sum(axis=1).to_numpy(int)
    # independent DIRECT-LOS reference is an audit comparator, never a PWIDE feature.
    s_direct=np.full(n,np.nan)
    for k in range(0,n,64):
        ii=np.arange(k,min(k+64,n));ii=ii[flags[ii]]
        if len(ii):s_direct[ii]=observe_port(los[ii,:,:,0],freqs)['s_fp'].to_numpy(float)
    q['s_direct_los_audit_only']=s_direct
    parity=np.abs(predicted[flags,1]-s_direct[flags]) if np.any(flags) else np.array([])
    qa={'route':route,'n_rf':n,'n_motion':m['motion_n'],'n_los_visible':int(flags.sum()),
        'n_los_blocked':int((~flags).sum()),'n_train_valid':int(q.valid_for_training.sum()),
        'model_vs_direct_los_max_abs':float(np.max(parity)) if len(parity) else None,
        'model_vs_direct_los_rmse':float(np.sqrt(np.mean(parity**2))) if len(parity) else None,
        'pwide_rows_needing_imputation':int(((q.pwide_feature_imputations>0)&q.valid_for_training).sum()),
        'radio_sha256':m['files']['RADIO_POSE.csv'],'release_sha256':m['archive_sha256'],
        'sensor_replay':'NOT_RUN','model_fitting':'NOT_RUN'}
    return q,qa


def site_weights(df: pd.DataFrame) -> np.ndarray:
    # Existing POWER site weighting; scene-specific coordinates, no cross-scene dedupe.
    keys=list(zip(df.scene,df.x_eval.round(5),df.y_eval.round(5)))
    counts=pd.Series(keys).value_counts();w=np.asarray([1/counts[k] for k in keys],float)
    return w/w.mean()


def row_cov(data: np.ndarray,weights: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    ww=np.asarray(weights,dtype=float);ww=ww/ww.sum()
    mu=np.einsum('n,ni->i',ww,data)
    diff=data-mu
    cov=np.einsum('n,ni,nj->ij',ww,diff,diff)
    return mu,cov


def fix_cov(c: np.ndarray, diagonal: bool=False) -> np.ndarray:
    x=np.asarray(c,float).copy();x=(x+x.T)*.5
    x[0,0]=max(float(x[0,0]),R0_R*.10)
    x[1,1]=max(float(x[1,1]),R0_S*.10)
    if diagonal:x[0,1]=x[1,0]=0
    else:
        rho=np.clip(x[0,1]/np.sqrt(x[0,0]*x[1,1]),-.9,.9)
        x[0,1]=x[1,0]=rho*np.sqrt(x[0,0]*x[1,1])
    if np.min(np.linalg.eigvalsh(x))<=0: raise ValueError('POWER_NON_PD')
    return x

@dataclass
class PowerTransfer:
    scaler:Any
    regressor:Any
    cuts:np.ndarray
    bin_mean:np.ndarray
    bin_cov:np.ndarray
    train_routes:tuple[str,...]
    training_scene:str='OFFICE_E'
    q_train_range:tuple[float,float]=(float('-inf'),float('inf'))

    @classmethod
    def fit(cls,train:pd.DataFrame):
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge
        if len(train)<60 or not (train.scene=='OFFICE_E').all():raise ValueError('POWER_SOURCE_OFFICE_ONLY')
        if not train[['log_fp_power','e_r','e_s']].notna().all().all():raise ValueError('POWER_NAN_TRAINING')
        w=site_weights(train)
        y=train[['e_r','e_s']].to_numpy(float)
        q=train[['log_fp_power']].to_numpy(float)
        scaler=StandardScaler().fit(q)
        a=scaler.transform(q)
        fit=Ridge(alpha=30.,fit_intercept=True).fit(a,y,sample_weight=w)
        residual=y-fit.predict(a)
        mu_global,cov_global=row_cov(residual,w);cov_global=fix_cov(cov_global,False)
        cuts=np.unique(np.quantile(q[:,0],[1/3,2/3]))
        index=np.searchsorted(cuts,q[:,0],side='right')
        bs=[];cs=[]
        for b in range(len(cuts)+1):
            mask=index==b
            if mask.sum()<15:raise ValueError('POWER_BIN_TOO_SMALL')
            mean_b,cov_b=row_cov(residual[mask],w[mask])
            effective=(w[mask].sum()**2)/(w[mask]**2).sum()
            alpha=effective/(effective+100.)
            bs.append(alpha*mean_b+(1-alpha)*mu_global)
            cs.append(fix_cov(alpha*cov_b+(1-alpha)*cov_global,False))
        return cls(scaler,fit,cuts,np.asarray(bs),np.asarray(cs),tuple(sorted(train.route.unique())),
                   q_train_range=(float(np.min(q)),float(np.max(q))))

    def predict(self,log_power:np.ndarray,diag:bool=True)->tuple[np.ndarray,np.ndarray]:
        v=np.asarray(log_power,dtype=float).reshape(-1,1)
        if not np.isfinite(v).all():raise ValueError('POWER_NONFINITE_INPUT')
        bins=np.searchsorted(self.cuts,v[:,0],side='right')
        mu=self.regressor.predict(self.scaler.transform(v))+self.bin_mean[bins]
        cov=self.bin_cov[bins].copy()
        if diag:cov[:,0,1]=cov[:,1,0]=0.
        return mu,cov


def as_pwide_features(frame:pd.DataFrame,medians:pd.Series | None=None)->tuple[pd.DataFrame,pd.Series]:
    d=frame.loc[:,P_FEATURES].replace([np.inf,-np.inf],np.nan).copy()
    if medians is None:medians=d.median().fillna(0)
    return d.fillna(medians).astype(float),medians


def augment_d0(frame:pd.DataFrame,model:Any,rng:np.random.Generator,reps:int=3)->tuple[np.ndarray,np.ndarray]:
    """Source-only heading perturbation up to +/-20 degrees; no target GT."""
    rows=np.tile(np.arange(len(frame)),reps)
    delta=rng.uniform(-20,20,len(rows))
    o=np.empty(len(rows),float)
    for route in sorted(frame.route.unique()):
        sel=frame.route.to_numpy()[rows]==route
        rr=rows[sel]
        state=np.c_[frame.x_eval.to_numpy()[rr],frame.y_eval.to_numpy()[rr],
                    np.deg2rad(frame.yaw_body_deg.to_numpy()[rr]+delta[sel]),np.zeros(len(rr))]
        case={'id':route+'_O0_M45_FULL','anchor':[5.,2.2,2.65],'robot_z_m':.45,'mount_deg':45.}
        chunks=[]
        for j in range(0,len(state),64):chunks.append(model.batch(state[j:j+64],case,gradient=False)[0][:,1])
        o[sel]=np.concatenate(chunks)
    return rows,frame['s_fp'].to_numpy()[rows]-o

@dataclass
class ResidualTransfer:
    pcir:Any
    pwide:Any
    medians:pd.Series
    gate_tau_d0:float
    training_routes:tuple[str,...]
    source_predictor_name:str='Full-CIR+prior-d0 P2 residual correction'

    @classmethod
    def fit(cls,frame:pd.DataFrame,model:Any,seed:int=20261022):
        from sklearn.ensemble import HistGradientBoostingRegressor
        train=frame.copy().reset_index(drop=True)
        if set(train.route.unique())!={'O01','O02','O03'}:raise ValueError('SOURCE_ALL_3_ROUTES_REQUIRED')
        if not (train.scene=='OFFICE_E').all():raise ValueError('PWIDE_NOT_OFFICE_ONLY')
        # Strict source-route OOF POWER pseudo-label for PWIDE residual, never
        # in-sample teacher labels or Corridor target labels.
        mu=np.full(len(train),np.nan)
        for route in sorted(train.route.unique()):
            a=train[train.route!=route].copy()
            b=train.route==route
            # Spatial embargo for an Office route sharing the same physical scene.
            # Never count an identical (x,y) pose in both teacher training and target.
            from scipy.spatial import cKDTree
            dist=cKDTree(train.loc[b,['x_eval','y_eval']].to_numpy(float)).query(a[['x_eval','y_eval']].to_numpy(float))[0]
            a=a.loc[dist>1e-4].copy()
            if len(a)<50:raise ValueError('INNER_SOURCE_NOT_ENOUGH')
            power=PowerTransfer.fit(a)
            mu[b]=power.predict(train.loc[b,'log_fp_power'].to_numpy())[0][:,1]
        if not np.isfinite(mu).all():raise AssertionError('INNER_OFFICE_POWER_INCOMPLETE')
        tr=train.copy();tr['delta']=tr.e_s.to_numpy()-mu
        base,med=as_pwide_features(tr)
        def make():return HistGradientBoostingRegressor(max_iter=160,learning_rate=.055,max_leaf_nodes=17,max_depth=5,
                                                        min_samples_leaf=20,l2_regularization=1.,random_state=20261022)
        pcir=make().fit(base,tr.delta.to_numpy(float))
        rows,d0=augment_d0(tr,model,np.random.default_rng(seed),3)
        x=base.iloc[rows].reset_index(drop=True).copy();x['d0']=d0
        pwide=make().fit(x,tr.delta.to_numpy(float)[rows])
        # Pre-registered simple source-only |d0| tail, NOT recalibrated on target;
        # scoring GT helps source calibration only, never in target prediction.
        tau=float(np.quantile(np.abs(tr.d0_gt_source.to_numpy(float)),.95))
        if not np.isfinite(tau) or tau<0:raise ValueError('GATE_TAU_SOURCE_BAD')
        return cls(pcir,pwide,med,tau,tuple(sorted(tr.route.unique())))

    def predict(self,frame:pd.DataFrame,d0:np.ndarray,kind:str)->np.ndarray:
        x,_=as_pwide_features(frame,self.medians)
        if kind=='PCIR':return np.asarray(self.pcir.predict(x),float)
        if kind=='PWIDE':
            x['d0']=np.asarray(d0,float)
            return np.asarray(self.pwide.predict(x),float)
        raise ValueError('UNKNOWN_RESIDUAL_ARM')


def gate_decision(d0:float,H_s:np.ndarray,P:np.ndarray,tau:float,policy:str='D0') -> bool:
    """Raw prior innovation used identically for POWER/PWIDE gate variants."""
    if policy=='NONE':return False
    if policy=='D0':return abs(d0)>tau
    if policy=='STATE':
        hph=max(0.,float(H_s@P@H_s))
        return float(d0*d0)>float(tau*tau+4*hph)
    raise ValueError('UNKNOWN_GATE_POLICY')

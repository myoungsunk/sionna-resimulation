"""Teacher-conditioned residual learners with explicit fit ancestry and grouped validation.

All labels live here, never in runtime_features. No hyperparameter search on held results.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from copy import deepcopy
import hashlib
import math
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy.spatial import cKDTree
from .common import (BASE_FEATURES, OFFSETS, CANDIDATES, Packet, require, BlockedError, digest,
                     file_hash, write_json, exact_rows)
from .runtime_features import Corrector, feature_names, build_features
from .native import NativeModel, spectrum_profile
from .numerics import moments

PARAMETERS = dict(max_iter=160, learning_rate=.055, max_leaf_nodes=17, max_depth=5,
                  min_samples_leaf=20, l2_regularization=1., random_state=20261022, early_stopping=False)


def stable_fold(group, n=3):
    return int.from_bytes(hashlib.sha256(str(group).encode()).digest()[:8], 'big') % n


def group_ids(xy, cell=.5):
    cells=np.floor(np.asarray(xy)/cell).astype(int)
    return np.array([f'{x}:{y}' for x,y in cells])


class FitLineage:
    def __init__(self, held, forbidden_keys=()):
        self.held=held;self.forbidden=set(map(str,forbidden_keys));self.events=[]

    def record(self, operation, frame, *, parents=(), details=None):
        keys=set(frame['key'].astype(str));routes=set(frame.route)
        require(self.held not in routes, f'Outer label leakage in {operation}')
        require(not keys & self.forbidden, f'Validation leakage in {operation}')
        row=dict(operation=operation, fit_keys=sorted(keys), fit_routes=sorted(routes), parents=list(parents), details=details or {})
        row['id']=digest(row);self.events.append(row);return row['id']

    def check(self):
        known=set()
        for e in self.events:
            require(set(e['parents']) <= known, 'Missing/unordered fit lineage parent')
            require(not set(e['fit_keys']) & self.forbidden and self.held not in e['fit_routes'], 'Leaked ancestry')
            known.add(e['id'])
        return True


@dataclass
class LearningData:
    frame: pd.DataFrame
    features: np.ndarray
    profiles: np.ndarray
    powers: np.ndarray
    state: np.ndarray
    grid_s: np.ndarray
    grid_g: np.ndarray
    models: dict

    def take(self, mask):
        ix=np.flatnonzero(mask) if np.asarray(mask).dtype==bool else np.asarray(mask)
        return LearningData(self.frame.iloc[ix].reset_index(drop=True),self.features[ix],self.profiles[ix],self.powers[ix],
                            self.state[ix],self.grid_s[ix],self.grid_g[ix],self.models)


def native_learning_data(assets, held):
    """Read only outer training rows. Never uses the held route to fit or fill a feature."""
    D=assets.P.prepare();D=D[D.route!=held].reset_index(drop=True)
    require(len(D)>0 and held not in set(D.route), 'Empty/contaminated training set')
    require(not D.duplicated(['case','pose_id']).any(),'Duplicate learning packet')
    obs=assets.obs[assets.obs.channel=='full'].copy()
    req=D[['case','pose_id']]
    O=exact_rows(obs,['case','pose_id'],req)
    D['x_eval']=O.x_eval;D['y_eval']=O.y_eval
    D['t_s']=np.nan
    D['group']=group_ids(D[['x_eval','y_eval']]);D['key']=D.case.astype(str)+':'+D.pose_id.astype(str)
    X=np.zeros((len(D),len(BASE_FEATURES)));q=np.full((len(D),len(OFFSETS)),np.nan);power=np.zeros_like(q);state=np.zeros((len(D),4));models={}
    for case_id in sorted(set(D.case)):
        case=assets.case(case_id);m=np.flatnonzero(D.case.to_numpy()==case_id)
        samples=pd.DataFrame(__import__('json').loads(assets.checked(assets.V.ROOT/case['samples_path']).read_text()))
        s=exact_rows(samples,['pose_id'],D.iloc[m][['pose_id']])
        state[m,:3]=np.column_stack([s.x,s.y,np.radians(s.yaw_body_deg)])
        with np.load(assets.checked(assets.V.one(f'{case_id}_full_B0_TRACE.npz')),allow_pickle=False) as trace:
            time_map=pd.Series(trace['t_s'],index=trace['pose_id'])
            D.loc[m,'t_s']=time_map.reindex(D.iloc[m].pose_id).to_numpy()
        models[case_id]=NativeModel(assets.source,assets.V,assets.core,case)
        positions=pd.Series(np.arange(len(samples)),index=samples.pose_id).loc[D.iloc[m].pose_id].to_numpy()
        H=np.load(assets.checked(assets.V.ROOT/case['full_path']),mmap_mode='r',allow_pickle=False)
        for i,k in zip(m,positions):
            qq,valid,fp,pp=spectrum_profile(H[k,:,:,0]);q[i]=qq;power[i]=pp
            X[i]=np.r_[qq[0],np.log10(max(pp[0],np.finfo(float).tiny)),fp,qq[1:],qq[1:]-qq[0]]
            require(abs(qq[0]-D.iloc[i]['sF_+0'])<1e-9,'Training RF observer mismatch')
    S=np.full((len(D),61),np.nan);G=np.full_like(S,np.nan)
    lookup={(c,int(p)):i for i,(c,p) in enumerate(zip(D.case,D.pose_id))}
    files=sorted(Path(assets.cfg['grid_root']).rglob('GRID_*.npz'))
    if not files:raise BlockedError('Missing original P1R GRID artifacts')
    for path in files:
        case=path.stem[5:].rsplit('_',1)[0]
        if case not in models:continue
        with np.load(assets.checked(path),allow_pickle=False) as z:
            cols=np.searchsorted(np.arange(-30,31),z['offsets'])
            require((cols>=0).all() and (cols<61).all(),'Grid offset out of range')
            rows=np.array([lookup[(case,int(p))] for p in z['pose_id']])
            require(not np.isfinite(S[np.ix_(rows,cols)]).any(),'Duplicate grid coverage')
            S[np.ix_(rows,cols)]=z['s'];G[np.ix_(rows,cols)]=z['g_deg']
    require(np.isfinite(S).all() and np.isfinite(G).all(),'Training grid incomplete')
    return LearningData(D,X,q,power,state,S,G,models)


def teacher_values(assets, data, held, lineage, *, crossfit=False, prediction_only=None):
    """Final/inner teacher refit on explicit eligible rows; evaluation rows never enter a fit."""
    F=data.frame;full=assets.obs[(assets.obs.channel=='full') & (assets.obs.route!=held)].copy()
    allowed=set(F.key);full['key']=full.case.astype(str)+':'+full.pose_id.astype(str)
    full=full[full.key.isin(allowed)].copy()
    # Existing upstream group columns must not create group_x/group_y and bypass split checks.
    full=full.drop(columns=['group'],errors='ignore').merge(F[['key','group']],on='key',validate='one_to_one')
    target=F if prediction_only is None else prediction_only
    mu=np.full(len(target),np.nan);vs=mu.copy();teacher_ids=np.empty(len(target),dtype=object)
    if prediction_only is not None:
        splits=[('validation',np.ones(len(target),bool),np.ones(len(full),bool))]
    elif crossfit:
        folds=F.group.map(stable_fold).to_numpy()
        splits=[(f'group_fold_{fold}',folds==fold,full.group.map(stable_fold).to_numpy()!=fold) for fold in range(3)]
    else:
        splits=[(f'leave_route_{r}',F.route.to_numpy()==r,full.route.to_numpy()!=r) for r in sorted(set(F.route))]
    for label,testmask,trainmask in splits:
        if not np.any(testmask):continue
        te=exact_rows(assets.obs[assets.obs.channel=='full'],['case','pose_id'],target.loc[testmask,['case','pose_id']])
        tr=full.loc[trainmask].copy()
        # Original POWER excludes exact repeated positions; group cross-fit additionally excludes shared blocks.
        dist=cKDTree(te[['x_eval','y_eval']].to_numpy()).query(tr[['x_eval','y_eval']].to_numpy())[0]
        tr=tr[dist>1e-4].copy()
        if len(tr)<40:raise BlockedError(f'Insufficient isolated POWER data: {label}, {len(tr)}')
        lineage_frame=tr[['key','route']].copy()
        tid=lineage.record('POWER_'+label,lineage_frame,details={'label_teacher':'crossfit' if crossfit else 'legacy_route','exclusion_m':1e-4})
        values=assets.power_predict(tr.drop(columns=['key','group']),te)
        mu[testmask]=values.mu_s.to_numpy();vs[testmask]=values.Vs.to_numpy();teacher_ids[testmask]=tid
    require(np.isfinite(mu).all() and np.isfinite(vs).all() and (vs>0).all(),'Incomplete teacher predictions')
    return mu,vs,teacher_ids


def augmented_rows(data, held, seed_map=None):
    # Same P_D0 augmentation as p2_l4train: uniform +/-20, three copies of every packet.
    seeds=seed_map or {'R2':11,'R4':12,'R5':13};n=len(data.frame)
    idx=np.tile(np.arange(n),3);offset=np.random.default_rng(seeds[held]*1000+17).uniform(-20,20,len(idx))
    state=data.state[idx].copy();state[:,2]=wrap_angle(state[:,2]+np.radians(offset))
    # Original cubic Hermite interpolation: do not replace the legacy d0 augmentation silently.
    grid=np.arange(-30.,31.);j=np.clip(np.floor(offset-grid[0]).astype(int),0,59);v=offset-grid[j]
    y0=data.grid_s[idx,j];y1=data.grid_s[idx,j+1];m0=data.grid_g[idx,j];m1=data.grid_g[idx,j+1]
    hs=(2*v**3-3*v**2+1)*y0+(v**3-2*v**2+v)*m0+(-2*v**3+3*v**2)*y1+(v**3-v**2)*m1
    return idx,state,hs,offset


def wrap_angle(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi


def fit_omega(data,lineage):
    residual=[]
    for i,row in data.frame.iterrows():
        q,valid,_=data.models[row['case']].profile(data.state[i])
        residual.append(np.where(valid,np.asarray(data.profiles[i])-q,np.nan))
    R=np.array(residual);med=pd.DataFrame(R).median().fillna(0).to_numpy()
    Z=np.where(np.isfinite(R),R,med);mean,C,M=moments(Z)
    lid=lineage.record('OMEGA_CENTERED_RESIDUAL_METRIC',data.frame,details={'not_thermal_noise':True,'mean':mean.tolist(),'imputation':med.tolist()})
    require(np.linalg.matrix_rank(C)>0,'No profile metric rank')
    return C,lid


def design_matrix(data,mode,mu,vs,idx,state,hs,omega=None):
    X=[];flags=[]
    for j,i in enumerate(idx):
        row=data.frame.iloc[i]
        p=Packet(int(row.pose_id),0.,np.array([0.,data.features[i,0]]),np.array([0.,mu[i]]),np.diag([1.,vs[i]]),
                 data.features[i],data.profiles[i],np.isfinite(data.profiles[i]) & (data.powers[i]>0),int(data.features[i,2]),data.powers[i])
        vector,flag=build_features(p,state[j],np.array([0.,hs[j]]),data.models[row['case']],mode,omega)
        X.append(vector);flags.append(flag)
    return np.array(X),flags


def fit_one(assets,data,held,mode,lineage,*,out=None,prepared=None):
    if prepared is None:
        mu,vs,tids=teacher_values(assets,data,held,lineage,crossfit=mode=='P5_CROSSFIT')
        idx,state,hs,offset=augmented_rows(data,held)
    else:
        mu,vs,tids,idx,state,hs,offset=prepared
    y0=data.frame.e_true.to_numpy(float)-mu;y=y0[idx]
    omega=None;parents=list(dict.fromkeys(tids.tolist()))
    if mode in ('P4_PERP','P4_SHUFFLE'):
        omega,oid=fit_omega(data,lineage);parents.append(oid)
    X,flags=design_matrix(data,mode,mu,vs,idx,state,hs,omega)
    if mode=='P4_SHUFFLE':
        # Training-only grouped shuffle. All augmented copies of a packet use the same donor packet.
        rng=np.random.default_rng(20261023);perm=rng.permutation(len(data.frame));n=len(data.frame)
        grouped=X[:,-len(OFFSETS):].reshape(3,n,-1).copy()
        X[:,-len(OFFSETS):]=grouped[:,perm,:].reshape(len(X),-1)
    med=pd.DataFrame(X).median().fillna(0).to_numpy();filled=np.where(np.isfinite(X),X,med)
    mid=lineage.record('IMPUTER_'+mode,data.frame,parents=parents,details={'columns':feature_names(mode)})
    model=HistGradientBoostingRegressor(**PARAMETERS).fit(pd.DataFrame(filled,columns=feature_names(mode)),y)
    fid=lineage.record('RESIDUAL_'+mode,data.frame,parents=[mid],details={'parameters':PARAMETERS,'augmentation_rows':len(y)})
    lineage.check()
    result=Corrector(mode,model,mode,med,omega,model_hash=fid)
    if out:
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        file=out/f'{held}__{mode}.joblib';joblib.dump(result,file,compress=3)
        write_json(file.with_suffix('.json'),dict(held=held,mode=mode,feature_names=feature_names(mode),model_sha256=file_hash(file),
                   lineage=lineage.events,seed=20261022,augmentation_seed={'R2':11,'R4':12,'R5':13}[held]*1000+17,
                   target='e_true_minus_teacher_mu',target_teacher_ids=tids.tolist(),training_keys=data.frame.key.tolist(),
                   representation='own_fp',fixed_design_no_test_selection=True))
    return result,dict(mu=mu,vs=vs,teacher_id=tids,idx=idx,state=state,hs=hs,offset=offset,y=y)


def load_candidate(root,held,mode):
    path=Path(root)/f'{held}__{mode}.joblib';meta=__import__('json').loads(path.with_suffix('.json').read_text())
    require(meta['held']==held and meta['mode']==mode,'Candidate contract mismatch')
    require(meta['model_sha256']==file_hash(path),'Candidate hash changed')
    require(all(held not in e['fit_routes'] for e in meta['lineage']),'Candidate lineage includes held route')
    return joblib.load(path)


def train_route(assets,held,out,*,modes=CANDIDATES):
    """Fixed design final fits plus nested spatial-block evaluation (never test-selected)."""
    data=native_learning_data(assets,held);outputs=[];lineage_rows=[];oof=[]
    # Final legacy teacher must match the original S.power_fit before claiming one-factor P1--P4 changes.
    audit_lineage=FitLineage(held);mu_check,vs_check,_=teacher_values(assets,data,held,audit_lineage)
    for route in sorted(set(data.frame.route)):
        legacy=assets.S.power_fit(assets.obs,[r for r in sorted(set(data.frame.route)) if r!=route],route)
        legacy=legacy[legacy.channel=='full']
        mask=data.frame.route==route
        reference=exact_rows(legacy,['case','pose_id'],data.frame.loc[mask,['case','pose_id']])
        require(np.allclose(mu_check[mask],reference.mu_s,atol=1e-10,rtol=0) and np.allclose(vs_check[mask],reference.Vs,atol=1e-10,rtol=0),'New legacy teacher differs from frozen teacher; single-factor claim blocked')
    # Identical old P0 design refit is an additional baseline-regeneration QA, never a new candidate.
    p0_lineage=FitLineage(held);p0,p0prep=fit_one(assets,data,held,'P0',p0_lineage)
    p0X,_=design_matrix(data,'P0',p0prep['mu'],p0prep['vs'],p0prep['idx'],p0prep['state'],p0prep['hs'])
    p0X=np.where(np.isfinite(p0X),p0X,p0.medians)
    frozen=assets.models[held][0]['models']['P_D0']
    raw=pd.DataFrame(p0X,columns=feature_names('P0'))
    dpar=float(np.max(abs(frozen.predict(raw)-p0.estimator.predict(raw))))
    require(dpar<1e-7,'P0 frozen/refit parity failed before candidate learning')
    outputs.append(dict(held=held,arm='P0_REFIT_QA',status='PASS',max_prediction_difference=dpar))
    fixed_target_hash=None;fixed_aug_hash=None
    for mode in modes:
        lineage=FitLineage(held);model,prep=fit_one(assets,data,held,mode,lineage,out=out)
        target_hash=digest(prep['y']);aug_hash=digest({'idx':prep['idx'],'offset':prep['offset']})
        if mode!='P5_CROSSFIT':
            if fixed_target_hash is None:fixed_target_hash=target_hash;fixed_aug_hash=aug_hash
            require(target_hash==fixed_target_hash and aug_hash==fixed_aug_hash,'P1--P4 comparison changed target or augmentation')
        for i,row in data.frame.iterrows():
            lineage_rows.append(dict(held=held,mode=mode,key=row.key,case=row['case'],route=row.route,t_s=row.t_s,group=row.group,mu=prep['mu'][i],Vs=prep['vs'][i],target=float(row.e_true-prep['mu'][i]),
                                     label_teacher=prep['teacher_id'][i],feature_teacher=prep['teacher_id'][i],
                                     model_hash=model.model_hash,target_hash=target_hash,augmentation_hash=aug_hash,scope='outer_training'))
        outputs.append(dict(held=held,arm=mode,status='FIT_COMPLETE',n_packets=len(data.frame),n_augmented=len(prep['y']),model_hash=model.model_hash))
        folds=data.frame.group.map(stable_fold).to_numpy()
        for fold in range(3):
            valmask=folds==fold;trainmask=~valmask
            if not valmask.any():continue
            # Spatial buffer and group isolation across all mounts/routes of repeated locations.
            distances=cKDTree(data.frame.loc[valmask,['x_eval','y_eval']]).query(data.frame[['x_eval','y_eval']])[0]
            trainmask &= distances>.2
            td=data.take(trainmask);vd=data.take(valmask)
            if len(td.frame)<80 or set(td.frame.route)!=set(data.frame.route):
                oof.append(dict(held=held,arm=mode,fold=fold,status='BLOCKED',reason='insufficient isolated nested-training roles'));continue
            lin=FitLineage(held,vd.frame.key)
            inner,_=fit_one(assets,td,held,mode,lin)
            mu,vs,tids=teacher_values(assets,td,held,lin,prediction_only=vd.frame)
            idx,st,hs,off=augmented_rows(vd,held);X,_=design_matrix(vd,mode,mu,vs,idx,st,hs,inner.omega)
            X=np.where(np.isfinite(X),X,inner.medians)
            pred=inner.estimator.predict(pd.DataFrame(X,columns=feature_names(mode)))
            target=vd.frame.e_true.to_numpy()[idx]-mu[idx]
            lin.check()
            write_json(Path(out)/f'{held}__{mode}__fold{fold}_lineage.json',dict(forbidden_keys=vd.frame.key.tolist(),events=lin.events))
            for j,i in enumerate(idx):
                oof.append(dict(held=held,arm=mode,fold=fold,key=vd.frame.iloc[i].key,group=vd.frame.iloc[i].group,
                                offset_deg=off[j],target=target[j],prediction=pred[j],residual=target[j]-pred[j],
                                D_s=target[j]**2-(target[j]-pred[j])**2,status='PASS',
                                note='spatial-block development validation, not independent environments'))
    return outputs,lineage_rows,oof

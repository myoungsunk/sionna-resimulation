#!/usr/bin/env python3
"""Execute separate Range/s conditional errors vs frozen source POWER1.
No online GT, source LoS, future observations, or coherent cross-port features.
Everything below is a developmental one-corridor held-route experiment.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,sys,time,traceback
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import chi2
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT=Path(os.environ['PJ_SOURCE_ROOT']).resolve()
OUT=Path(os.environ['PJ_OUT']).resolve();OUT.mkdir(parents=True,exist_ok=True)
for path in ['research/EKF4_RANGE_S_STAGED_20261014','research/FFD_P0P3_20261016','research/R5_N4B_20261015','research/PHYSICS_RS_STAGED_20261015/code','results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0,str(ROOT/path))
import p0_initial
p0_initial.OUT=OUT
from source_model import SourceFFD
import source_model
source_model.OUT=OUT
from features import extract,FEATURES,GROUPS
import n4b_rf_errors as B
from r2_bias_replay import build_positive_bias_controls,predict_one,BIAS_LEVELS,INITIAL_POSE_STD,BIAS_PRIOR_STD
from core import gaussian_update,sequential_affine,wrap
from p3_rf_adapter4 import R0
MANIFEST=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
QR=['log_fp_power','delay_rms_ns','peak_diff_ns']
QS=['log_fp_power','delay_rms_ns','detector_s_span','s_diff4']
ARMS=['JOINT4','POWER1','POWER_DIAG','SEP_DIAG','SEP_GLOBAL','SEP_BIN','SEP_MU_PWR_COV','PWR_MU_SEP_COV','SEP_BIN_BOX_GATE']
G2=float(chi2.ppf(.99,2));GBOX=float(chi2.ppf(.995,1));C1=float(chi2.ppf(.95,1));C2=float(chi2.ppf(.95,2))

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def wcov(Y,w):
    w=np.asarray(w,float);w=w/w.sum();m=np.sum(w[:,None]*Y,axis=0);e=Y-m
    return m,np.einsum('n,ni,nj->ij',w,e,e)
def wrho(Y,w):
    m,C=wcov(Y,w);q=C[0,1]/np.sqrt(max(C[0,0]*C[1,1],1e-24))
    return float(np.clip(q,-.85,.85)),m

def update(x,P,z,h,H,mu,R,box=False,mask=None):
    v=z-h-mu
    S=H@P@np.swapaxes(H,-1,-2)+R;S=(S+np.swapaxes(S,-1,-2))*.5
    K=np.swapaxes(np.linalg.solve(S,H@P),-1,-2)
    nis=np.einsum('ni,ni->n',v,np.linalg.solve(S,v[...,None])[...,0])
    yes=nis<=G2
    if box:yes=np.all(v*v/np.diagonal(S,axis1=-2,axis2=-1)<=GBOX,axis=1)
    if mask is not None:yes=np.broadcast_to(mask,yes.shape).copy()
    dx=np.einsum('nij,nj->ni',K,v)
    candidate=x+dx;candidate[:,2]=wrap(candidate[:,2])
    A=np.eye(4)[None]-K@H
    C=A@P@np.swapaxes(A,-1,-2)+K@R@np.swapaxes(K,-1,-2);C=(C+np.swapaxes(C,-1,-2))*.5
    return np.where(yes[:,None],candidate,x),np.where(yes[:,None,None],C,P),nis,yes,K,v,S,candidate,C

def math_qa():
    rng=np.random.default_rng(20261020);maxd=0.;gatediff=0
    for _ in range(100):
        x=rng.normal(size=4)*.1;a=rng.normal(size=(4,4));P=a@a.T+.1*np.eye(4)
        b=rng.normal(size=(2,2));R=b@b.T+.05*np.eye(2);H=rng.normal(size=(2,4));h=H@x;z=h+rng.normal(size=2);mu=rng.normal(size=2)*.1
        out=update(x[None],P[None],z[None],h[None],H[None],mu[None],R[None],mask=True)
        direct=gaussian_update(x,P,z-mu,lambda _: (h,H),R)
        seq=sequential_affine(x,P,z-mu,h,H,R)
        L=np.linalg.cholesky(R);wh=gaussian_update(x,P,np.linalg.solve(L,z-mu),lambda _: (np.linalg.solve(L,h),np.linalg.solve(L,H)),np.eye(2))
        for y,C in [direct[:2],seq[:2],wh[:2]]:
            maxd=max(maxd,float(np.max(abs(y-out[0][0]))),float(np.max(abs(C-out[1][0]))))
        q=R[1,1]-R[0,1]**2/R[0,0];assert q>0
        LS=np.linalg.cholesky(out[6][0]);white=np.linalg.solve(LS,out[5][0]);assert abs(np.sum(white*white)-out[2][0])<1e-10
        assert np.linalg.eigvalsh(out[1]).min()>0
    assert maxd<1e-10,maxd
    # online feature lists do not contain truth/source/pose/mount/phase attributes.
    banned=['truth','eval','pose','yaw','anchor','los','jones','freq_s']
    assert not any(any(b in q for b in banned) for q in QR+QS)
    dump(OUT/'MATH_QA.json',{'status':'PASS','random_SPD_cases':100,'joint_whitened_sequential_maxdiff':maxd,'conditional_Jacobian_required':True,'predictive_S_whitened_NIS':'PASS','feature_allowlist':[QR,QS],'not_a_formal_likelihood_normalization_proof':True})

def build_dataset(model):
    output=[];sourceaudit=[]
    for c in MANIFEST['cases']:
        samples=pd.DataFrame(json.loads((ROOT/c['samples_path']).read_text()))
        pose=samples[['x','y','yaw_body_deg']].to_numpy(float);pose[:,2]=np.radians(pose[:,2]);ids=samples.pose_id.to_numpy(int)
        pred=np.vstack([model.batch(pose[k:k+64],c,gradient=False)[0] for k in range(0,len(pose),64)])
        for ch,key in [('full','full_path'),('los','los_path')]:
            fp=ROOT/c[key];H=np.load(fp,mmap_mode='r',allow_pickle=False);assert tuple(H.shape)==tuple(c['H_shape'])
            blocks=[extract(np.asarray(H[k:k+64,:,:,0]),model.freqs) for k in range(0,len(H),64)]
            q={name:np.concatenate([b[name] for b in blocks]) for name in blocks[0]};assert np.all(q['valid'])
            d=pd.DataFrame({'case':c['id'],'route':c['route'],'channel':ch,'pose_id':ids,'x_eval':pose[:,0],'y_eval':pose[:,1],'yaw_eval_rad':pose[:,2],'e_r':q['range_m']-pred[:,0],'e_s':q['s_fp']-pred[:,1],'s_fp':q['s_fp'],'range_m':q['range_m']})
            for f in FEATURES:d[f]=q[f]
            d['fp_tap']=q['tap'];output.append(d)
            sourceaudit.append({'case':c['id'],'channel':ch,'bytes':fp.stat().st_size,'sha256':sha(fp),'rows':len(d)})
            print('DATA',c['id'],ch,len(d),flush=True)
    d=pd.concat(output,ignore_index=True);assert len(d)==19038 and not d.duplicated(['case','channel','pose_id']).any()
    assert np.isfinite(d[QR+QS+['e_r','e_s']]).all().all()
    d.to_csv(OUT/'OBSERVATION_FEATURES_LABELS.csv.gz',index=False,compression='gzip')
    dump(OUT/'INPUT_PROVENANCE.json',{'source_git':os.getenv('GITHUB_SHA'),'sources':sourceaudit,'feature_source_sha':sha(ROOT/'research/PHYSICS_RS_STAGED_20261015/code/features.py'),'FFD_source_sha':sha(ROOT/'research/FFD_P0P3_20261016/source_model.py'),'one_physical_corridor':True,'new_Sionna_runs':0})
    return d

def marginal(train,test,w,target,features,binfield,floor):
    sc=StandardScaler().fit(train[features].to_numpy(float));X=sc.transform(train[features].to_numpy(float));Z=sc.transform(test[features].to_numpy(float))
    y=train[target].to_numpy(float);reg=Ridge(alpha=30.).fit(X,y,sample_weight=w)
    mt=reg.predict(X);mu=reg.predict(Z);e=y-mt
    gm=float(np.average(e,weights=w));gv=max(float(np.average((e-gm)**2,weights=w)),floor)
    cuts=np.unique(np.quantile(train[binfield],[1/3,2/3]));bt=np.searchsorted(cuts,train[binfield],side='right');be=np.searchsorted(cuts,test[binfield],side='right')
    vt=np.empty(len(train));ve=np.empty(len(test));stats=[]
    for b in range(len(cuts)+1):
        sel=bt==b;ws=w[sel];ne=float(ws.sum()**2/(ws@ws));a=ne/(ne+100.)
        mean=float(np.average(e[sel],weights=ws));var=float(np.average((e[sel]-mean)**2,weights=ws))
        correction=a*mean+(1-a)*gm;variance=max(a*var+(1-a)*gv,floor)
        mt[sel]+=correction;mu[be==b]+=correction;vt[sel]=variance;ve[be==b]=variance
        stats.append({'bin':b,'train_n':int(sel.sum()),'n_eff':ne,'variance':variance,'mean_adjustment':correction})
    info={'features':features,'binfield':binfield,'train_cuts':cuts.tolist(),'ridge_alpha':30,'coefs_scaled':reg.coef_.tolist(),'intercept':float(reg.intercept_),'scaler_mean':sc.mean_.tolist(),'scaler_scale':sc.scale_.tolist(),'bins':stats}
    return mt,vt,mu,ve,info

def covariance_arrays(vr,vs,rho=0.):
    a=np.zeros((len(vr),2,2));a[:,0,0]=vr;a[:,1,1]=vs;a[:,0,1]=a[:,1,0]=np.asarray(rho)*np.sqrt(vr*vs)
    assert np.linalg.eigvalsh(a).min()>0
    return a

def fit_models(data):
    full=data[data.channel=='full'].copy();predrows=[];measscores=[];aud=[]
    for held in ('R2','R4','R5'):
        te=data[data.route==held].copy();testxy=te[['x_eval','y_eval']].to_numpy();dist=cKDTree(testxy).query(full[['x_eval','y_eval']].to_numpy())[0]
        tr=full[(full.route!=held)&(dist>1e-4)].copy();w=B.site_weights(np,pd,tr);assert held not in set(tr.route)
        mp,cp,ip=B.fit_model(np,tr,te,w,'POWER_BIN_JOINT',GROUPS)
        mr,vr,er,evr,ir=marginal(tr,te,w,'e_r',QR,'delay_rms_ns',float(R0[0,0]*.1))
        ms,vs,es,evs,iss=marginal(tr,te,w,'e_s',QS,'detector_s_span',float(R0[1,1]*.1))
        mse=np.column_stack([er,es]);std=np.column_stack([(tr.e_r.to_numpy()-mr)/np.sqrt(vr),(tr.e_s.to_numpy()-ms)/np.sqrt(vs)])
        rg,gm=wrho(std,w);rhot=np.full(len(te),rg);cutsr=np.unique(np.quantile(tr.delay_rms_ns,[1/3,2/3]));cutss=np.unique(np.quantile(tr.detector_s_span,[1/3,2/3]))
        br=np.searchsorted(cutsr,tr.delay_rms_ns,side='right');bs=np.searchsorted(cutss,tr.detector_s_span,side='right');xr=np.searchsorted(cutsr,te.delay_rms_ns,side='right');xs=np.searchsorted(cutss,te.detector_s_span,side='right');rhostats=[]
        for a in range(len(cutsr)+1):
            for b in range(len(cutss)+1):
                sel=(br==a)&(bs==b);target=(xr==a)&(xs==b);ne=float(w[sel].sum()**2/(w[sel]@w[sel])) if sel.any() else 0
                raw,sm=wrho(std[sel],w[sel]) if sel.sum()>=30 else (rg,gm)
                alpha=ne/(ne+200.) if sel.sum()>=30 else 0.;value=float(np.clip(alpha*raw+(1-alpha)*rg,-.85,.85));rhot[target]=value
                rhostats.append({'range_bin':a,'s_bin':b,'n_train':int(sel.sum()),'n_test':int(target.sum()),'rho':value,'rawrho':raw,'shrink':alpha,'standardized_residual_bin_mean':np.asarray(sm).tolist()})
        diag=covariance_arrays(evr,evs);joint=covariance_arrays(evr,evs,rhot);globalC=covariance_arrays(evr,evs,rg);powerdiag=cp.copy();powerdiag[:,0,1]=powerdiag[:,1,0]=0
        params={'JOINT4':(np.zeros_like(mp),np.tile(R0,(len(te),1,1))),'POWER1':(mp,cp),'POWER_DIAG':(mp,powerdiag),'SEP_DIAG':(mse,diag),'SEP_GLOBAL':(mse,globalC),'SEP_BIN':(mse,joint),'SEP_MU_PWR_COV':(mse,cp),'PWR_MU_SEP_COV':(mp,joint),'SEP_BIN_BOX_GATE':(mse,joint)}
        audit={'held_route':held,'train_n':len(tr),'test_n':len(te),'train_routes':sorted(tr.route.unique()),'POWER':ip,'range_model':ir,'s_model':iss,'rho_global':rg,'rho_global_residual_mean':gm.tolist(),'rho_bins':rhostats,'train_data_sha256':hashlib.sha256(tr[['case','pose_id','e_r','e_s']].to_csv(index=False).encode()).hexdigest()};aud.append(audit)
        for name,(mu,C) in params.items():
            assert np.isfinite(mu).all() and np.linalg.eigvalsh(C).min()>0
            q=te[['case','route','channel','pose_id']].copy();q['model']=name;q['mu_r']=mu[:,0];q['mu_s']=mu[:,1];q['Vr']=C[:,0,0];q['Vs']=C[:,1,1];q['Crs']=C[:,0,1];predrows.append(q)
            for (case,ch),ix in te.groupby(['case','channel']).indices.items():
                Y=te.iloc[ix][['e_r','e_s']].to_numpy()-mu[ix];CC=C[ix];white=np.linalg.solve(np.linalg.cholesky(CC),Y[...,None])[...,0];d2=np.sum(white**2,axis=1);nl=math.log(2*math.pi)+.5*(np.linalg.slogdet(CC)[1]+d2)
                measscores.append({'case':case,'channel':ch,'model':name,'n':len(ix),'bias_r_m':float(Y[:,0].mean()),'bias_s':float(Y[:,1].mean()),'r_rmse_m':float(np.sqrt(np.mean(Y[:,0]**2))),'s_rmse':float(np.sqrt(np.mean(Y[:,1]**2))),'range95':float(np.mean(Y[:,0]**2/CC[:,0,0]<=C1)),'s95':float(np.mean(Y[:,1]**2/CC[:,1,1]<=C1)),'joint95':float(np.mean(d2<=C2)),'mean_range_sigma_m':float(np.sqrt(CC[:,0,0]).mean()),'mean_s_sigma':float(np.sqrt(CC[:,1,1]).mean()),'conditional_error_nll':float(nl.mean()),'pred_rho_mean':float(np.mean(CC[:,0,1]/np.sqrt(CC[:,0,0]*CC[:,1,1]))),'empirical_corr':float(np.corrcoef(Y.T)[0,1]),'whitened_corr':float(np.corrcoef(white.T)[0,1])})
        print('FOLD',held,'TRAIN',len(tr),'TEST',len(te),'rho',rg,flush=True)
    pred=pd.concat(predrows,ignore_index=True);assert not pred.duplicated(['case','channel','pose_id','model']).any()
    pred.to_csv(OUT/'OOF_PARAMETERS.csv.gz',index=False,compression='gzip');pd.DataFrame(measscores).to_csv(OUT/'MEASUREMENT_SCORES.csv',index=False);dump(OUT/'TRAIN_FOLD_RECEIPTS.json',aud)
    return pred

def score(X,C,t,truth,bias):
    e=X[:,:,:3]-truth[:,None,:];e[:,:,2]=wrap(e[:,:,2]);mask=t>=30
    h=e[mask,:,2];s=C[mask,:,2,2];b=X[mask,:,3]-np.radians(BIAS_LEVELS[bias]);rows=[]
    for j in range(X.shape[1]):
        rows.append({'n':int(mask.sum()),'heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(h[:,j]**2)))),'heading_signed_bias_deg':float(np.degrees(h[:,j].mean())),'heading95':float(np.mean(h[:,j]**2/s[:,j]<=C1)),'heading_nees':float(np.mean(h[:,j]**2/s[:,j])),'heading_sigma_deg_mean':float(np.degrees(np.sqrt(s[:,j])).mean()),'xy_rmse_m':float(np.sqrt(np.mean(np.sum(e[mask,j,:2]**2,axis=1)))),'bias_rmse_dps':float(np.degrees(np.sqrt(np.mean(b[:,j]**2))))})
    return rows

def recursive(data,params,source,case,bias,ch):
    cm=case['id'];routem=next(x for x in MANIFEST['routes'] if x['id']==case['route']);timeframe=pd.read_csv(ROOT/routem['path']);t=timeframe.t_s.to_numpy(float);ids=timeframe.pose_id.to_numpy(int)
    assert len(t)==routem['samples'] and np.all(np.diff(t)>0)
    truth=timeframe[['x','y','yaw_body_deg']].to_numpy(float);truth[:,2]=np.radians(truth[:,2]);d=data[(data.case==cm)&(data.channel==ch)].set_index('pose_id').loc[ids]
    assert np.max(abs(d.x_eval.to_numpy()-truth[:,0]))<1e-9 and np.max(abs(wrap(d.yaw_eval_rad.to_numpy()-truth[:,2])))<1e-9
    z=d[['range_m','s_fp']].to_numpy();n=len(t);J=len(ARMS);mm=np.empty((n,J,2));RR=np.empty((n,J,2,2))
    for j,a in enumerate(ARMS):
        p=params[(params.case==cm)&(params.channel==ch)&(params.model==a)].set_index('pose_id').loc[ids];mm[:,j]=p[['mu_r','mu_s']];RR[:,j,0,0]=p.Vr;RR[:,j,1,1]=p.Vs;RR[:,j,0,1]=RR[:,j,1,0]=p.Crs
    controls,x0=build_positive_bias_controls(t,truth,bias);x=np.tile(np.r_[x0,0.],(J,1));P=np.tile(np.diag(np.r_[INITIAL_POSE_STD**2,BIAS_PRIOR_STD**2]),(J,1,1))
    X=np.empty((n,J,4));C=np.empty((n,J,4,4));accept=np.empty((n,J),bool);NIS=np.empty((n,J));fixedX=np.empty_like(X);fixedC=np.empty_like(C);one_step=[];checks=[];gatecounts=np.zeros(J,int)
    for k in range(n):
        if k:
            for j in range(J):x[j],P[j]=predict_one(x[j],P[j],float(controls['ds_odom'][k]),float(controls['dtheta_gyro'][k]),float(controls['dt_s'][k]))
        h,H=source.batch(x,case);zz=np.tile(z[k],(J,1));a=update(x,P,zz,h,H,mm[k],RR[k]);box=update(x[-1:],P[-1:],zz[-1:],h[-1:],H[-1:],mm[k,-1:],RR[k,-1:],box=True)
        a[0][-1]=box[0][0];a[1][-1]=box[1][0];a[2][-1]=box[2][0];a[3][-1]=box[3][0]
        # Independently verify original source joint and whitened sequential math at sampled real priors.
        if k%113==0:
            for j in [0,1,5]:
                yy,pp,dg=gaussian_update(x[j],P[j],z[k]-mm[k,j],lambda _,j=j:(h[j],H[j]),RR[k,j],gate_threshold=G2)
                dx=float(np.max(abs(yy-a[0][j])));dp=float(np.max(abs(pp-a[1][j])));assert max(dx,dp)<2e-10 and bool(dg['accepted'])==bool(a[3][j])
                checks.append({'case':cm,'bias':bias,'channel':ch,'step':k,'arm':ARMS[j],'max_x':dx,'max_P':dp})
        # Same POWER prior and common POWER mask, no new source-model call.
        j=1;fx=np.tile(x[j],(J,1));fp=np.tile(P[j],(J,1,1));fh=np.tile(h[j],(J,1));fH=np.tile(H[j],(J,1,1))
        fa=update(fx,fp,zz,fh,fH,mm[k],RR[k],mask=bool(a[3][j]));fixedX[k]=fa[0];fixedC[k]=fa[1]
        raw=update(fx,fp,zz,fh,fH,mm[k],RR[k]);gatecounts+=raw[3]!=a[3][j]
        if k%2==0 and ch=='full':
            for jj in [0,1,3,5,8]:
                one_step.append({'case':cm,'bias':bias,'t_s':float(t[k]),'model':ARMS[jj],'joint_nis':float(raw[2][jj]),'marginal_nis_r':float(raw[5][jj,0]**2/raw[6][jj,0,0]),'marginal_nis_s':float(raw[5][jj,1]**2/raw[6][jj,1,1]),'joint_accept':bool(raw[3][jj]),'range_to_yaw_deg':float(np.degrees(raw[4][jj,2,0]*raw[5][jj,0])),'s_to_yaw_deg':float(np.degrees(raw[4][jj,2,1]*raw[5][jj,1])),'r_nu':float(raw[5][jj,0]),'s_nu':float(raw[5][jj,1])})
        x,P=a[0],a[1];X[k]=x;C[k]=P;accept[k]=a[3];NIS[k]=a[2]
    assert np.isfinite(X).all() and np.linalg.eigvalsh(C).min()>0
    # Same marginal estimates and R as SEP_BIN, only gate is different in BOX arm.
    assert np.array_equal(mm[:,5],mm[:,8]) and np.array_equal(RR[:,5],RR[:,8])
    rows=[]
    for label,xx,cc in [('NATURAL_RECURSIVE',X,C),('FIXED_POWER_PRIOR_AND_GATE',fixedX,fixedC)]:
        scores=score(xx,cc,t,truth,bias)
        for j,r in enumerate(scores):
            r.update(case=cm,bias=bias,channel=ch,model=ARMS[j],mode=label,accepted_fraction=float(accept[t>=30,j].mean()) if label.startswith('NATURAL') else float(accept[t>=30,1].mean()),gate_disagreement_from_common_power_prior=int(gatecounts[j]),pre_gate_NIS_mean=float(NIS[t>=30,j].mean()) if label.startswith('NATURAL') else None)
            rows.append(r)
    # Independent scalar RMSE check, deliberately not calling score().
    for j in range(J):
        ee=np.arctan2(np.sin(X[t>=30,j,2]-truth[t>=30,2]),np.cos(X[t>=30,j,2]-truth[t>=30,2]));rm=math.sqrt(float(np.dot(ee,ee))/len(ee))*180/math.pi;assert abs(rm-rows[j]['heading_rmse_deg'])<1e-10
    if ch=='full' and bias=='B0':
        known={'R2_aA_m0':1.799,'R2_aA_m45':.983,'R2_aB_m0':1.516,'R4_aA_m0':.659,'R4_aB_m0':1.508,'R5_aA_m0':4.556,'R5_aB_m0':1.056}
        delta=abs(rows[1]['heading_rmse_deg']-known[cm]);checks.append({'case':cm,'bias':bias,'channel':ch,'historical_rounding_comparison_abs_deg':delta,'max_x':0.,'max_P':0.});assert delta<.02,('POWER_BASELINE_NOT_REPRODUCED',cm,rows[1])
    stem=f'{cm}_{ch}_{bias}'
    np.savez_compressed(OUT/(stem+'_TRACE.npz'),state=X,cov=C,accepted=accept,nis=NIS,arms=ARMS,t_s=t,pose_id=ids,truth_scoring_only=truth,mu=mm,R=RR,fixed_state=fixedX,fixed_cov=fixedC)
    pd.DataFrame(rows).to_csv(OUT/(stem+'_SCORES.csv'),index=False);pd.DataFrame(checks).to_csv(OUT/(stem+'_QA.csv'),index=False)
    if one_step:pd.DataFrame(one_step).to_csv(OUT/(stem+'_UPDATE_ORIGINS.csv.gz'),index=False,compression='gzip')
    print('REPLAY_DONE',cm,ch,bias,'POWER',round(rows[1]['heading_rmse_deg'],5),'SEPdiag',round(rows[3]['heading_rmse_deg'],5),'SEPrho',round(rows[5]['heading_rmse_deg'],5),flush=True)
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['prepare','replay','summary'],required=True);ap.add_argument('--case');args=ap.parse_args()
    math_qa()
    if args.phase=='prepare':
        model=SourceFFD();d=build_dataset(model);fit_models(d);print('PREPARE_ALL_PASS',flush=True)
    elif args.phase=='replay':
        model=SourceFFD();d=pd.read_csv(OUT/'OBSERVATION_FEATURES_LABELS.csv.gz');p=pd.read_csv(OUT/'OOF_PARAMETERS.csv.gz');c=next(c for c in MANIFEST['cases'] if c['id']==args.case)
        for bias in ['B0','L2']:
            for ch in ['full','los']:recursive(d,p,model,c,bias,ch)
    else:
        print('Use separate summary.py for aggregation')
if __name__=='__main__':main()

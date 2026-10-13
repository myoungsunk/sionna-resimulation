"""R2-3: E1 consistency improvement. Criteria/arms: R23_PREREG_KO.md (frozen before running). Online noisy-CIR E1 per seed, fold-wise residual models, GM-bias EKF.
usage: r23_run.py OUT_DIR FROZEN.json FREQS --h-full-dirs .. --dr-config {B0,F2_prior_matched,F1_known_eb,F1F2} [--snr 30] [--seeds 32] [--procs 4]"""
import argparse,json,math,sys,time
from multiprocessing import Pool
from pathlib import Path
import numpy as np,pandas as pd
from scipy.optimize import least_squares
from scipy.stats import chi2
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import p3_common as P,gm_ekf as G
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
ROOT=P.ROOT;B_OLD=P.B_OLD;DT=0.2;QUANT=(299792458.0/(1028*1.953125e6))**2/12.0
ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('frozen');ap.add_argument('freqs');ap.add_argument('--h-full-dirs',nargs='+',required=True);ap.add_argument('--dr-config',required=True)
ap.add_argument('--snr',type=int,default=30);ap.add_argument('--seeds',type=int,default=32);ap.add_argument('--procs',type=int,default=4);ap.add_argument('--n-train-seeds',type=int,default=4);A=ap.parse_args()
FZ=json.load(open(A.frozen));FOLD=FZ['loro_fold_params'];FREQ=np.load(A.freqs)
G7=ROOT/'research/V01B_CLOSURE_20261012/G7/out';LAB=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv',usecols=['case','pose_id','true_distance_m'])
CASES=sorted(LAB.case.unique());CIDX={c:i for i,c in enumerate(CASES)};from r22_adr_decomposition import load_motion
MOT={r:load_motion(r) for r in ('R2','R4','R5')}
DTRUE={c:g.sort_values('pose_id').true_distance_m.to_numpy() for c,g in LAB.groupby('case')}
find=lambda n:next(p for dd in A.h_full_dirs for p in [Path(dd)/n] if p.exists());HM={}
def hfile(c):
    if c not in HM:HM[c]=np.load(find(f'H_{c}.npy'),mmap_mode='r')
    return HM[c]
def anchor(c):return (4.0 if '_aA_' in c else 10.0,0.0,2.65)
DR={'B0':dict(),'F2_prior_matched':dict(prior=True),'F1_known_eb':dict(known=True),'F1F2':dict(known=True,prior=True)}[A.dr_config]
def noisy(case,tag,e1):
    nv=P.O.noise_var_from_snr(A.snr);thr=P.O.detection_threshold(nv);rng=np.random.default_rng([20261013,CIDX[case],tag,A.snr])
    mount=int(case.split('_m')[1]);r=P.predict(np.asarray(hfile(case)),mount,FREQ,{'chosen':'E1_on_B','params':{'E1':e1}},noise_var=nv,rng=rng,threshold=thr)
    return r['B_old'],r['chosen'],r['detected']      # offset-removed ranges (~distance)
# ---------------- fold-wise residual models (training routes only, separate noise seeds)
def fit_resid(series_list,L=10):
    allv=np.concatenate([s[np.isfinite(s)] for s in series_list]);mu=allv.mean();var=allv.var();num=np.zeros(L+1);den=np.zeros(L+1)
    for s in series_list:
        e=s-mu
        for l in range(0,L+1):
            a=e[:len(e)-l] if l else e;b=e[l:];ok=np.isfinite(a)&np.isfinite(b);num[l]+=np.sum(a[ok]*b[ok]);den[l]+=ok.sum()
    rho=(num/np.maximum(den,1))[1:]/(num[0]/den[0]);lags=np.arange(1,L+1)
    fit=least_squares(lambda p:rho-p[0]*p[1]**lags,[min(max(rho[0],0.05),0.95),0.9],bounds=([0.0,0.0],[1.0,0.9995]));a,phi=fit.x
    return dict(sigma2_tot=float(var),mean=float(mu),a=float(a),phi=float(phi),tau_s=float(-DT/math.log(phi)) if 0<phi<1 else 0.0,sigma_b2=float(a*var),sigma_w2=float(max((1-a)*var,QUANT)),iat=float(1+2*rho.sum()),rho=[float(x) for x in rho])
def train_models(held):
    out={}
    sE=[];sB=[]
    for case in CASES:
        if case[:2]==held:continue
        ids=MOT[case[:2]]['pose_id'];d=DTRUE[case]
        for j in range(A.n_train_seeds):
            rB,rE,det=noisy(case,90+j,FOLD[held]['E1']);eE=np.where(det[ids],rE[ids]-d[ids],np.nan);eB=np.where(det[ids],rB[ids]-d[ids],np.nan);sE.append(eE);sB.append(eB)
    out['E']=fit_resid(sE);out['B']=fit_resid(sB);return out
# ---------------- one (case, seed) task: noisy features once, 3 drifts x arms
ARMS=['A_DR','B0_fixed','E1_defR','E1_Rvar','E1_RIAT','E1_GM','B0_GM']
def make_cfg(level,known,extra_R=None):
    p0=[0.03,0.03,math.radians(2.),math.radians(0.12),0.0104,0.0064]
    if DR.get('prior'):
        L=DRIFT_LEVELS[level];p0[3]=math.radians(L.gyro_bias_dps);p0[4]=L.gyro_sf;p0[5]=L.wheel_ratio
    kw=dict(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=extra_R is not None,use_s=False,anchor_xyz=anchor_case[0],mount_deg=0.,robot_z=0.45,bias_rw_std=0.,known_wheelbase_error=known,p0_std=tuple(p0),range_offset=B_OLD)
    if extra_R is not None:
        kw['range_extra_sigma']=math.sqrt(max(extra_R-kw.get('range_sigma',0.05)**2-QUANT,0.0))
    return FilterConfig(**kw)
anchor_case=[None]
def run_arm(arm,case,level,sseed,inputs,known,truth,ids,z,det,models):
    anchor_case[0]=anchor(case);n=len(truth);x0=np.r_[truth[0],0.,0.,0.];x0[:3]+=V.rng(sseed,'initial').normal(size=3)*np.array([0.03,0.03,math.radians(2.)])
    m=models['E'] if arm in('E1_Rvar','E1_RIAT','E1_GM') else models['B']
    if arm=='A_DR':f=F.SensorV2Filter(make_cfg(level,known),None,x0);kind='6'
    elif arm in('B0_fixed','E1_defR'):f=F.SensorV2Filter(make_cfg(level,known,0.05**2+0.05**2+QUANT),None,x0);kind='6'      # default R = stored filter value
    elif arm=='E1_Rvar':f=F.SensorV2Filter(make_cfg(level,known,m['sigma2_tot']),None,x0);kind='6'
    elif arm=='E1_RIAT':f=F.SensorV2Filter(make_cfg(level,known,m['sigma2_tot']*m['iat']),None,x0);kind='6'
    else:
        cfg=make_cfg(level,known,0.0);f=G.GMEKF(cfg,x0,m['sigma_b2'],m['phi'],m['sigma_w2'],B_OLD);kind='7'
    nees=np.full(n,np.nan);pe=np.zeros(n);he=np.zeros(n);innov=[]
    for k in range(n):
        if k:f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
        if arm!='A_DR' and det[k]:
            if kind=='6':
                y,R,S,st=f.range_record(z[k])
                if st=='applied':innov.append(y/math.sqrt(S))
            else:
                r=f.range_update(z[k])
                if r:innov.append(r[0]/math.sqrt(r[1]))
        est,cov=f.mean_cov();e=truth[k]-est[:3];e[2]=V.wrap(e[2]);pe[k]=math.hypot(e[0],e[1]);he[k]=e[2];Pm=cov[:3,:3]
        if np.linalg.eigvalsh(Pm).min()>0:nees[k]=e@np.linalg.solve(Pm,e)
    iz=np.array(innov);ac=float(np.corrcoef(iz[:-1],iz[1:])[0,1]) if len(iz)>10 else np.nan
    return nees.astype(np.float32),pe.astype(np.float32),he.astype(np.float32),ac
MODELS={}
def task(args):
    case,s=args;route=case[:2];m=MOT[route];t=m['t'];truth=m['pose'];ids=m['pose_id'];rows=[]
    if route not in MODELS:MODELS[route]=train_models(route)
    models=MODELS[route];rB,rE,det=noisy(case,s,FOLD[route]['E1']);zB=(rB+B_OLD)[ids];zE=(rE+B_OLD)[ids];dets=det[ids]
    for level in (0,1,2):
        sseed=7000+s;inputs,ev=V.generate(t,m['ds'],m['dtheta'],V.SensorV2Config(level=level,condition='all'),sseed);known=float(ev['true_parameters'][3]) if DR.get('known') else 0.
        for arm in ARMS:
            z=zE if arm.startswith('E1') else zB
            nees,pe,he,ac=run_arm(arm,case,level,sseed,inputs,known,truth,ids,z,dets,models)
            rows.append((case,level,s,arm,nees,pe,he,ac))
    return rows,{route:models}
if __name__=='__main__':
    out=Path(A.out);out.mkdir(parents=True,exist_ok=True);tasks=[(c,s) for c in CASES for s in range(A.seeds)];t0=time.time();rows=[];models_all={}
    with Pool(A.procs) as pool:
        for i,(r,mm) in enumerate(pool.imap_unordered(task,tasks,chunksize=2)):
            rows+=r;models_all.update(mm)
            if i%24==0:print(i,len(tasks),'%.0fs'%(time.time()-t0),flush=True)
    # ---- aggregate
    recs=[];cellN={}
    for (case,level,s,arm,nees,pe,he,ac) in rows:
        t=MOT[case[:2]]['t'];keep=t>=30
        recs.append(dict(case=case,drift=level,seed=s,arm=arm,pos_rmse=float(np.sqrt(np.mean(pe[keep].astype(float)**2))),hd_rmse_deg=float(np.degrees(np.sqrt(np.mean(he[keep].astype(float)**2)))),innov_acf1=ac))
        cellN.setdefault((case,level,arm),[]).append(nees)
    R=pd.DataFrame(recs);cells=[]
    for (case,level,arm),L in cellN.items():
        t=MOT[case[:2]]['t'];keep=t>=30;arr=np.stack(L).astype(float)[:,keep];Ak=np.nanmean(arr,axis=0);cut=int(.75*keep.sum())
        cells.append(dict(case=case,drift=level,arm=arm,anees=float(np.nanmean(Ak)),anees_late25=float(np.nanmean(Ak[cut:])),coverage95=float(np.nanmean(arr<=chi2.ppf(.95,3)))))
    C=pd.DataFrame(cells);R.to_csv(out/'R23_RUNS.csv',index=False);C.to_csv(out/'R23_CELLS.csv',index=False)
    rng=np.random.default_rng(20261013);cases=np.array(CASES)
    def boot(f,n=4000):
        v=[f(cases[rng.integers(0,len(cases),len(cases))]) for _ in range(n)];return [float(np.percentile(v,2.5)),float(np.percentile(v,97.5))],[float(np.percentile(v,5)),float(np.percentile(v,95))]
    pr=R.groupby(['case','arm']).pos_rmse.mean().unstack();hr=R.groupby(['case','arm']).hd_rmse_deg.mean().unstack()
    dC=C.assign(d=lambda x:np.abs(np.log(x.anees/3.0))).groupby(['case','arm']).d.mean().unstack();cv=C.groupby(['case','arm']).coverage95.mean().unstack()
    def ratio(a,b):return lambda cs:float(np.mean(pr.loc[cs,a]/pr.loc[cs,b]))
    res=dict(dr_config=A.dr_config,snr=A.snr,seeds=A.seeds,seconds=time.time()-t0,fold_models=models_all,arms=ARMS)
    res['arm_means']={a:dict(pos_rmse=float(pr[a].mean()),hd_rmse_deg=float(hr[a].mean()),anees_cells_median=float(C[C.arm==a].anees.median()),coverage95=float(cv[a].mean()),innov_acf1=float(R[R.arm==a].innov_acf1.mean()),d_ln_anees=float(dC[a].mean())) for a in ARMS}
    f=ratio('E1_GM','E1_defR');ci95,_=boot(f);res['G1_acc_noninferior']=dict(ratio=f(cases),ci95=ci95,pass_=bool(ci95[1]<1.10))
    def dd(a,b):return lambda cs:float(np.mean(dC.loc[cs,a]-dC.loc[cs,b]))
    f=dd('E1_GM','E1_defR');ci95,_=boot(f);res['G2_consistency_vs_defR']=dict(delta=f(cases),ci95=ci95,pass_=bool(ci95[1]<0))
    f=dd('E1_GM','E1_RIAT');ci95,_=boot(f);res['G2b_vs_Rinflation']=dict(delta=f(cases),ci95=ci95,gm_better_than_Rinflation=bool(ci95[1]<0))
    f=lambda cs:float(cv.loc[cs,'E1_GM'].mean());ci95,ci90=boot(f);res['G3_abs_coverage_E1_GM']=dict(mean=f(cases),ci90=ci90,pass_=bool(ci90[0]>=0.92 and ci90[1]<=0.98),evaluated=(A.dr_config!='NONE'))
    for a,b in (('E1_defR','B0_fixed'),('E1_GM','B0_GM'),('E1_GM','A_DR'),('E1_defR','A_DR'),('B0_fixed','A_DR')):
        f=ratio(a,b);ci95,_=boot(f);res[f'acc_{a}_vs_{b}']=dict(ratio=f(cases),ci95=ci95)
    (out/'R23_RESULTS.json').write_text(json.dumps(res,indent=1,default=float));print(json.dumps({k:v for k,v in res.items() if k not in('fold_models',)},indent=1,default=float))

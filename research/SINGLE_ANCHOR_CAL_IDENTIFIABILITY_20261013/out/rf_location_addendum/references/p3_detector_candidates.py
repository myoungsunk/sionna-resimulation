"""P3: detector-timing (D1 fractional crossing, D2 template fit) and conditional-bias (E1 ridge on online features) candidates, selected by leave-one-route-out validation.
PRE-STATED selection rule (the plan's 'D+E only if each passes alone' clause was missing in attempt 1 of this script, which let D1+E1 win; attempt 1 is kept as P3_attempt1_superseded): a candidate is carried to P4 only if its pooled LORO site-weighted Full-RF range RMSE is <= 0.95 x that of B (existing offset)
AND it is better than B in each of the 3 folds. Otherwise B stays frozen. The XY shared by R2 and R4 is excluded from held-out scoring. Truth (d_true) enters fits of TRAIN folds only.
usage: p3_detector_candidates.py OUT_DIR --h-full-dirs .. --h-los-dirs .. --freqs F"""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
G7=P.ROOT/'research/V01B_CLOSURE_20261012/G7/out'
ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('--h-full-dirs',nargs='+',required=True);ap.add_argument('--h-los-dirs',nargs='+',required=True);ap.add_argument('--freqs',required=True);a=ap.parse_args()
out=Path(a.out);assert not out.exists();out.mkdir(parents=True)
freq=np.load(a.freqs);tm=P.tap_m(freq)
f=pd.read_csv(G7/'01_FEATURES_12.csv',usecols=['case','route','pose_id']);l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv',usecols=['case','route','pose_id','true_distance_m','true_x','true_y'])
d=f.merge(l,on=['case','route','pose_id'],validate='one_to_one').sort_values(['case','pose_id']).reset_index(drop=True)
d['mount']=d.case.str.extract(r'_m(\d+)')[0].astype(int);d['site']=[f'{r}|{x:.4f}|{y:.4f}' for r,x,y in zip(d.route,d.true_x,d.true_y)]
xy=[f'{x:.4f}|{y:.4f}' for x,y in zip(d.true_x,d.true_y)];sh=pd.Series(xy).groupby(pd.Series(xy)).transform('size');d['xy']=xy
cross=d.groupby('xy').route.nunique();shared=set(cross[cross>1].index);d['shared']=d.xy.isin(shared)
find=lambda dirs,n:next(p for dd in dirs for p in [Path(dd)/n] if p.exists())
SF=[];SL=[];DF=[];DL=[]
for case,g in d.groupby('case',sort=False):
    ids=g.pose_id.to_numpy();Hf=np.load(find(a.h_full_dirs,f'H_{case}.npy'),mmap_mode='r');Hl=np.load(find(a.h_los_dirs,f'H_LoS_{case}.npy'),mmap_mode='r')
    sf,_=P.cir_mag(Hf[ids]);sl,_=P.cir_mag(Hl[ids]);SF.append(sf.astype(np.float32));SL.append(sl.astype(np.float32));DF.append(P.detect(sf,tm));DL.append(P.detect(sl,tm))
SF=np.concatenate(SF);SL=np.concatenate(SL);cat=lambda L:{k:np.concatenate([x[k] for x in L]) for k in L[0]};DF=cat(DF);DL=cat(DL)
dt=d.true_distance_m.to_numpy();mount=d.mount.to_numpy();route=d.route.to_numpy()
rB_f=DF['r_b']-P.B_OLD;rB_l=DL['r_b']-P.B_OLD
def score(err,sub):
    e=pd.Series(err,index=d.index)[sub];g=(e**2).groupby([d.case[sub],d.site[sub]]).mean();return dict(n=int(sub.sum()),rmse_site=float(np.sqrt(g.mean())),rmse_pose=float(np.sqrt((e**2).mean())),mean=float(e.mean()),sd=float(e.std()),abs_p95=float(np.percentile(np.abs(e),95)))
rows=[];frozen_params={}
def fit_all(tr):
    """fit every candidate on the TRAIN mask; return a dict of callables' parameters"""
    m={}
    m['C_const']=float((DL['r_b'][tr]-dt[tr]).mean());b,a_=np.polyfit(dt[tr],DL['r_b'][tr],1);m['C2']=(float(a_),float(b))
    m['D1_offset']=float((DL['r_d1'][tr]-dt[tr]).mean())
    X=P.e1_features(DF,mount,tm);m['E1']=P.ridge(X[tr],(rB_f-dt)[tr]);
    detD=dict(DF);detD['r_b']=DF['r_d1']-m['D1_offset'];XD=P.e1_features(detD,mount,tm);m['E1D']=P.ridge(XD[tr],((DF['r_d1']-m['D1_offset'])-dt)[tr])
    m['D2_template']=P.build_template(SL[tr],dt[tr]/tm).tolist();return m
def apply_all(m,sub):
    r={'B_old':{'full':rB_f,'los':rB_l},'C_const':{'full':DF['r_b']-m['C_const'],'los':DL['r_b']-m['C_const']},'C2_affine':{'full':(DF['r_b']-m['C2'][0])/m['C2'][1],'los':(DL['r_b']-m['C2'][0])/m['C2'][1]},
       'D1_fractional':{'full':DF['r_d1']-m['D1_offset'],'los':DL['r_d1']-m['D1_offset']}}
    X=P.e1_features(DF,mount,tm);r['E1_on_B']={'full':rB_f-P.ridge_pred(m['E1'],X)}
    detD=dict(DF);detD['r_b']=DF['r_d1']-m['D1_offset'];r['D1+E1']={'full':(DF['r_d1']-m['D1_offset'])-P.ridge_pred(m['E1D'],P.e1_features(detD,mount,tm))}
    T=np.array(m['D2_template']);idx=np.where(sub)[0]
    pf=P.d2_fit(SF[idx],{k:v[idx] for k,v in DF.items()},T)*tm;pl=P.d2_fit(SL[idx],{k:v[idx] for k,v in DL.items()},T)*tm
    full=np.full(len(d),np.nan);los=np.full(len(d),np.nan);full[idx]=pf;los[idx]=pl;r['D2_template']={'full':full,'los':los};return r
fold_res={}
for held in ('R2','R4','R5'):
    tr=(route!=held);te=(route==held)&(~d.shared.to_numpy());m=fit_all(tr);r=apply_all(m,te);fold_res[held]=m
    for arm,v in r.items():
        for kind,rng in v.items():
            s=score(rng-dt,te);rows.append(dict(fold=held,arm=arm,channel=kind,**s))
R=pd.DataFrame(rows);R.to_csv(out/'P3_VALIDATION_PAIRED.csv',index=False)
# pooled over the 3 folds (site-weighted: pool the case-site MSE groups)
pool=[]
for arm in R.arm.unique():
    for kind in ('full','los'):
        q=R[(R.arm==arm)&(R.channel==kind)]
        if len(q)==0:continue
        n=q.n.to_numpy();pool.append(dict(arm=arm,channel=kind,rmse_pose=float(np.sqrt(np.sum(n*q.rmse_pose**2)/n.sum())),rmse_site=float(np.sqrt(np.sum(n*q.rmse_site**2)/n.sum())),abs_p95_mean=float(q.abs_p95.mean()),per_fold_rmse_site=dict(zip(q.fold,q.rmse_site.round(5))),n=int(n.sum())))
pool=pd.DataFrame(pool);b=pool[(pool.arm=='B_old')&(pool.channel=='full')].iloc[0]
sel=[];verdicts={}
for _,rw in pool[pool.channel=='full'].iterrows():
    if rw.arm=='B_old':continue
    rel=rw.rmse_site/b.rmse_site;each=all(rw.per_fold_rmse_site[k]<b.per_fold_rmse_site[k] for k in ('R2','R4','R5'));verdicts[rw.arm]=dict(rel_to_B_site_weighted=float(rel),better_in_all_folds=bool(each),carried_to_P4=bool(rel<=0.95 and each))
    if rw.arm=='D1+E1':continue          # plan rule: D+E is eligible ONLY if D and E each pass on their own (evaluated below)
    if rel<=0.95 and each:sel.append(rw.arm)
for _,rw in pool[pool.channel=='full'].iterrows():
    if rw.arm!='D1+E1':continue
    rel=rw.rmse_site/b.rmse_site;each=all(rw.per_fold_rmse_site[k]<b.per_fold_rmse_site[k] for k in ('R2','R4','R5'));ok_parts=('D1_fractional' in sel) and ('E1_on_B' in sel)
    verdicts['D1+E1']=dict(rel_to_B_site_weighted=float(rel),better_in_all_folds=bool(each),carried_to_P4=bool(rel<=0.95 and each and ok_parts),requires_D1_and_E1_individually=bool(ok_parts))
    if verdicts['D1+E1']['carried_to_P4']:sel.append('D1+E1')
cand=dict(arms=['B_old','C_const','C2_affine','D1_fractional','D2_template','E1_on_B','D1+E1'],features_E1=P.E1_FEATURES,selection_rule='pooled LORO site-weighted Full RMSE <= 0.95*B and better in all 3 folds',verdicts=verdicts,pooled=pool.to_dict('records'))
(out/'P3_MODEL_CANDIDATES.json').write_text(json.dumps(cand,indent=1,default=float))
# freeze: fit on ALL routes (the shared XY stays in training only) -> coefficients for P4/P5
mall=fit_all(np.ones(len(d),bool))
choice=sorted(sel,key=lambda k:verdicts[k]['rel_to_B_site_weighted'])[0] if sel else 'B_old'
frozen=dict(chosen=choice,reason='first by LORO site-weighted Full RMSE among candidates passing the pre-stated rule' if sel else 'no candidate met the pre-stated rule -> existing fixed offset B stays frozen',
   b_old_offset_m=P.B_OLD,params=mall,loro_fold_params={k:{kk:vv for kk,vv in v.items() if kk!='D2_template'} for k,v in fold_res.items()},code_sha256={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in('p3_common.py','p3_detector_candidates.py')},feature_schema=P.E1_FEATURES)
(out/'P3_FROZEN_MODEL.json').write_text(json.dumps(frozen,indent=1,default=float))
(out/'P3_DECISION.md').write_text('# P3 decision\n\nchosen for P4: **%s**\n\n```json\n%s\n```\n'%(choice,json.dumps(dict(verdicts=verdicts,pooled_full=pool[pool.channel=='full'][['arm','rmse_site','rmse_pose','abs_p95_mean','per_fold_rmse_site']].to_dict('records'),pooled_los=pool[pool.channel=='los'][['arm','rmse_site','rmse_pose']].to_dict('records')),indent=1,default=float)))
print('chosen:',choice);print(pool[['arm','channel','rmse_site','rmse_pose','abs_p95_mean','per_fold_rmse_site']].round(5).to_string());print(json.dumps(verdicts,indent=1))

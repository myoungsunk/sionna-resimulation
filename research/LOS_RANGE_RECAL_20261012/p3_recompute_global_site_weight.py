"""R2-4a: recompute the P3 LORO pooled RMSE with GLOBAL site-uniform weighting (every (case,site) group MSE weighted equally across the 3 folds),
instead of the R1 rule (fold rmse_site^2 weighted by pose count n). Re-uses the unchanged P3 pipeline text up to the validation table, so fits/folds/exclusions are identical.
Consistency check: per-fold rmse_site must reproduce R1 P3_VALIDATION_PAIRED.csv. R1 files are NOT modified.
usage: p3_recompute_global_site_weight.py OUT_DIR R1_P3_DIR --h-full-dirs .. --h-los-dirs .. --freqs F"""
import sys,json
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent
src=(HERE/'p3_detector_candidates.py').read_text()
head=src[:src.index("R=pd.DataFrame(rows)")]
GROUPS=[]
head=head.replace("e=pd.Series(err,index=d.index)[sub];g=(e**2).groupby([d.case[sub],d.site[sub]]).mean();return dict(","e=pd.Series(err,index=d.index)[sub];g=(e**2).groupby([d.case[sub],d.site[sub]]).mean();GROUPS.append((g.copy(),int(sub.sum())));return dict(")
assert "GROUPS.append" in head
r1_dir=Path(sys.argv[2]);argv=[sys.argv[0],sys.argv[1]]+sys.argv[3:];sys.argv=argv
g=dict(__name__='p3_recompute',__file__=str(HERE/'p3_detector_candidates.py'),GROUPS=GROUPS);exec(compile(head,'p3_detector_candidates_head','exec'),g)
rows=g['rows'];out=g['out'];GR=GROUPS;assert len(GR)==len(rows)
R=pd.DataFrame(rows);old=pd.read_csv(r1_dir/'P3_VALIDATION_PAIRED.csv')
chk=R.merge(old,on=['fold','arm','channel'],suffixes=('','_r1'));assert len(chk)==len(R)
mx=float(np.abs(chk.rmse_site-chk.rmse_site_r1).max());assert mx<1e-9,mx
rec=[]
for (r,(grp,n)) in zip(rows,GR):
    rec.append(dict(fold=r['fold'],arm=r['arm'],channel=r['channel'],n_pose=n,n_groups=len(grp),sum_mse=float(grp.sum())))
Q=pd.DataFrame(rec)
res=[]
for (arm,ch),q in Q.groupby(['arm','channel']):
    res.append(dict(arm=arm,channel=ch,rmse_site_global=float(np.sqrt(q.sum_mse.sum()/q.n_groups.sum())),rmse_site_r1_pose_weighted=float(np.sqrt(np.sum(q.n_pose*(old.set_index(['fold','arm','channel']).loc[list(zip(q.fold,q.arm,q.channel))].rmse_site.to_numpy()**2))/q.n_pose.sum())),n_groups=int(q.n_groups.sum()),
       per_fold={f:float(np.sqrt(s/k)) for f,s,k in zip(q.fold,q.sum_mse,q.n_groups)}))
P_=pd.DataFrame(res);b=P_[(P_.arm=='B_old')&(P_.channel=='full')].iloc[0]
ver={};sel=[]
for _,rw in P_[P_.channel=='full'].iterrows():
    if rw.arm=='B_old':continue
    rel_g=rw.rmse_site_global/b.rmse_site_global;rel_r1=rw.rmse_site_r1_pose_weighted/b.rmse_site_r1_pose_weighted
    each=all(rw.per_fold[k]<b.per_fold[k] for k in('R2','R4','R5'));ver[rw.arm]=dict(rel_global=float(rel_g),rel_r1_pose_weighted=float(rel_r1),better_in_all_folds=bool(each),passes_rule_global=bool(rel_g<=0.95 and each))
    if rw.arm!='D1+E1' and ver[rw.arm]['passes_rule_global']:sel.append(rw.arm)
if 'D1+E1' in ver:ver['D1+E1']['passes_rule_global']=bool(ver['D1+E1']['passes_rule_global'] and 'D1_fractional' in sel and 'E1_on_B' in sel)
if ver.get('D1+E1',{}).get('passes_rule_global'):sel.append('D1+E1')
choice=min(sel,key=lambda k:ver[k]['rel_global']) if sel else 'B_old'
doc=dict(note='global site-uniform weighting; R1 files unchanged',consistency_max_abs_diff_fold_rmse_site=mx,verdicts=ver,pooled=P_.to_dict('records'),choice_global=choice,choice_r1='E1_on_B',choice_unchanged=bool(choice=='E1_on_B'))
Path(out/'P3_RECOMPUTE_GLOBAL_SITE_WEIGHT.json').write_text(json.dumps(doc,indent=1,default=float));print(json.dumps(dict(choice=choice,unchanged=doc['choice_unchanged'],ver=ver),indent=1,default=float))

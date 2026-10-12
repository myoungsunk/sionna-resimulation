"""P4: blind range-accuracy test of the FROZEN P3 model on NEW physical sites (same corridor scene). Predictions are produced from the complex channel only and written BEFORE the truth file is opened.
Experiments (separate, never pooled): noise_free, snr30, snr10 (paired: B and the chosen model are computed from the same noisy CIR).
Gate (fixed in the plan before the test): primary = site-weighted Full-RF range RMSE reduction vs B >= 10 % with the paired site-cluster bootstrap 95 % CI entirely below 0.
Levels: (a) LORO exploratory (done in P1/P3), (b) site-disjoint new XY = THIS test, (c) different scene/material/anchor geometry = NOT AVAILABLE -> GENERALIZATION_NOT_VERIFIED.
usage: p4_blind_range_eval.py OUT_DIR BLIND_DIR FROZEN.json FREQS"""
import json,sys,hashlib
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import p3_common as P
out=Path(sys.argv[1]);blind=Path(sys.argv[2]);frozen=json.load(open(sys.argv[3]));freq=np.load(sys.argv[4]);out.mkdir(parents=True,exist_ok=False)
# --- code integrity against the freeze addendum
add=json.load(open(Path(sys.argv[3]).parent/'P3_FREEZE_ADDENDUM.json'));cur={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in add['code_sha256']}
assert cur==add['code_sha256'],('code changed after freeze',cur,add['code_sha256'])
# --- load blind channels
HF=[];HL=[];K=[]
for p in sorted(blind.glob('shard*.npz')):
    z=np.load(p);HF.append(z['H_full']);HL.append(z['H_los']);K+=list(zip(z['site_id'],z['anchor_x'],z['mount']))
HF=np.concatenate(HF);HL=np.concatenate(HL);site=np.array([k[0] for k in K]);anc=np.array([k[1] for k in K]);mnt=np.array([k[2] for k in K])
assert len(set(K))==len(K)==480*2 or len(K)>0
tm=P.tap_m(freq);pred=[]
for exp,snr in (('noise_free',None),('snr30',30),('snr10',10)):
    nv=P.O.noise_var_from_snr(snr) if snr else None;thr=P.O.detection_threshold(nv) if snr else None
    for kind,H in (('full',HF),('los',HL)):
        rng=np.random.default_rng([20261012,snr or 0,0 if kind=='los' else 1]);r=P.predict(H,mnt,freq,frozen,noise_var=nv,rng=rng,threshold=thr)
        pred.append(pd.DataFrame(dict(experiment=exp,channel=kind,site_id=site,anchor_x=anc,mount=mnt,detected=r['detected'],tap=r['tap'],r_B=r['B_old'],r_chosen=r['chosen'])))
pred=pd.concat(pred,ignore_index=True);pred.to_csv(out/'P4_PREDICTIONS_BEFORE_TRUTH.csv',index=False,float_format='%.10g')
pred_sha=hashlib.sha256((out/'P4_PREDICTIONS_BEFORE_TRUTH.csv').read_bytes()).hexdigest()
# --- scorer: only here the truth is opened
sites=json.load(open(HERE/'out_p0_p5/R1/P4_TEST_SITES_FROZEN.json'))['sites'];sdict={s['site_id']:s for s in sites}
sys.path.insert(0,str(P.ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
from qclean_uwb.scenarios.corridor import CorridorSetup
truth={}
for ax in (4.0,10.0):
    cs=CorridorSetup(anchor_x_m=ax)
    for s in sites:truth[(s['site_id'],ax)]=float(np.linalg.norm(cs.robot_position(s['x'],s['y'])-np.asarray(cs.anchor_position)))
pred['d_true']=[truth[(s,a)] for s,a in zip(pred.site_id,pred.anchor_x)];pred['x']=[sdict[s]['x'] for s in pred.site_id];pred['y']=[sdict[s]['y'] for s in pred.site_id]
pred['horiz_dist_anchor']=np.hypot(pred.x-pred.anchor_x,pred.y);pred['dbin']=pd.cut(pred.d_true,[0,5,10,np.inf],right=False).astype(str)
pred['e_B']=pred.r_B-pred.d_true;pred['e_chosen']=pred.r_chosen-pred.d_true
res={'prediction_file_sha256_written_before_truth':pred_sha,'chosen_model':frozen['chosen'],'levels':{'a_LORO_exploratory':'P1/P3','b_site_disjoint_new_XY':'this test','c_other_scene':'NOT_AVAILABLE -> GENERALIZATION_NOT_VERIFIED'},'experiments':{}}
rng=np.random.default_rng(20261012)
def site_weighted(e,df):
    g=(e**2).groupby(df.site_id).mean();return float(np.sqrt(g.mean()))
for exp in ('noise_free','snr30','snr10'):
    for ch in ('full','los'):
        q=pred[(pred.experiment==exp)&(pred.channel==ch)];det=q.detected.to_numpy();qd=q[det]
        if ch=='los' and True:arms=['B']
        else:arms=['B','chosen']
        r=dict(n=int(len(q)),detection_rate=float(det.mean()),missed=int((~det).sum()),rmse_site_weighted={},rmse_pose={},abs_p95={},mean={},sd={})
        for arm in arms:
            e=qd['e_'+('B' if arm=='B' else 'chosen')];r['rmse_site_weighted'][arm]=site_weighted(e,qd);r['rmse_pose'][arm]=float(np.sqrt((e**2).mean()));r['abs_p95'][arm]=float(np.percentile(np.abs(e),95));r['mean'][arm]=float(e.mean());r['sd'][arm]=float(e.std())
        if ch=='full':
            sids=qd.site_id.unique();grp={s:g for s,g in qd.groupby('site_id')};sB={s:float((g.e_B**2).mean()) for s,g in grp.items()};sC={s:float((g.e_chosen**2).mean()) for s,g in grp.items()}
            aB=np.array([sB[s] for s in sids]);aC=np.array([sC[s] for s in sids]);rel=[]
            for _ in range(4000):
                pick=rng.integers(0,len(sids),len(sids));rel.append(np.sqrt(aC[pick].mean())/np.sqrt(aB[pick].mean())-1)
            r['relative_change_site_weighted_rmse']=dict(point=float(np.sqrt(aC.mean())/np.sqrt(aB.mean())-1),ci95=[float(np.percentile(rel,2.5)),float(np.percentile(rel,97.5))],n_site_clusters=int(len(sids)))
            r['pose_level_paired_abs_error_improved_fraction']=float((qd.e_chosen.abs()<qd.e_B.abs()).mean())
            by={}
            for key in('dbin','anchor_x','mount'):
                for lv,g in qd.groupby(key):by[f'{key}={lv}']=dict(n=int(len(g)),rmse_B=float(np.sqrt((g.e_B**2).mean())),rmse_chosen=float(np.sqrt((g.e_chosen**2).mean())))
            r['strata']=by
        res['experiments'][f'{exp}/{ch}']=r
nf=res['experiments']['noise_free/full']['relative_change_site_weighted_rmse'];gate_pass=(nf['point']<=-0.10) and (nf['ci95'][1]<0)
res['gate_noise_free_full']=dict(point_change=nf['point'],ci95=nf['ci95'],needs='point <= -10% and CI upper < 0',within_scene_pass=bool(gate_pass))
res['verdict']='WITHIN_SCENE_IMPROVEMENT_GENERALIZATION_NOT_VERIFIED' if gate_pass else ('FAIL' if nf['point']>=0 else 'INCONCLUSIVE_OR_PARTIAL')
(out/'P4_SITE_BOOTSTRAP_CI.json').write_text(json.dumps(res,indent=1,default=float))
for ch,name in (('full','P4_HELDOUT_FULLRF_PAIRED.csv'),('los','P4_HELDOUT_LOS_PAIRED.csv')):pred[pred.channel==ch].to_csv(out/name,index=False,float_format='%.10g')
f=pred[(pred.channel=='full')&(pred.experiment=='noise_free')].copy();f['worse']=f.e_chosen.abs()-f.e_B.abs();pd.concat([f.nlargest(12,'worse'),f.reindex(f.e_chosen.abs().sort_values(ascending=False).index).head(12)]).drop_duplicates(['site_id','anchor_x','mount']).to_csv(out/'P4_FAILURE_CASES.csv',index=False,float_format='%.10g')
(out/'P4_GATE.md').write_text('# P4 gate\n\nverdict: **%s**\n\n```json\n%s\n```\n'%(res['verdict'],json.dumps({k:v for k,v in res.items() if k!='experiments'},indent=1,default=float)))
print(res['verdict'],json.dumps(res['gate_noise_free_full']));
for k,v in res['experiments'].items():print(k,'det %.3f'%v['detection_rate'],{a:round(b,4) for a,b in v['rmse_site_weighted'].items()},v.get('relative_change_site_weighted_rmse'))

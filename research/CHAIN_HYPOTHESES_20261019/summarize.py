"""Independent result audit and descriptive hypothesis contrasts."""
from pathlib import Path
import argparse,json,hashlib,shutil
import numpy as np
import pandas as pd

def readtable(p):
    try:return pd.read_csv(p)
    except pd.errors.EmptyDataError:return pd.DataFrame()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    root=Path(a.input);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    scorefiles=list(root.rglob('SCORES.csv'));tables=[readtable(p) for p in scorefiles];tables=[d for d in tables if len(d)]
    if not tables:raise RuntimeError('No scientific results to summarize')
    scores=pd.concat(tables,ignore_index=True)
    if scores.duplicated(['case','bias','arm','scope']).any():raise RuntimeError('Duplicate results')
    scores.to_csv(out/'ALL_SCORES.csv',index=False);ev=scores[scores.scope=='evaluation'].copy();ev.to_csv(out/'EVALUATION_SCORES.csv',index=False)
    qas=[];audits=[];bad=[];events=[];episodes=[]
    for p in root.rglob('QA.json'):
        qas.extend(json.loads(p.read_text()))
    for p in root.rglob('EPISODES.csv'):
        d=readtable(p)
        if len(d):episodes.append(d)
    if episodes:pd.concat(episodes,ignore_index=True).to_csv(out/'ALL_EPISODES.csv',index=False)
    for p in root.rglob('*_TRACE.npz'):
        parts=p.stem.split('_');case='_'.join(parts[:3]);bias=parts[3]
        with np.load(p,allow_pickle=False) as z:
            t=z['t'];mask=t>=30;truth=z['truth_offline'];X=z['state'];P=z['cov'];arms=z['arms'].tolist()
            for j,arm in enumerate(arms):
                e=X[mask,j,2]-truth[mask,2];e=np.arctan2(np.sin(e),np.cos(e));v=P[mask,j,2,2];d=e/np.sqrt(v)
                rmse=float(np.rad2deg(np.sqrt(np.sum(e*e)/len(e))));coverage=float(np.count_nonzero(d*d<=3.841458820694124)/len(e));nees=float(np.dot(d,d)/len(e))
                ref=ev[(ev.case==case)&(ev.bias==bias)&(ev.arm==arm)]
                if len(ref)!=1:bad.append({'file':str(p),'arm':arm,'error':'Missing unique score'});continue
                rr=ref.iloc[0];diff=max(abs(rmse-rr.heading_rmse_deg),abs(coverage-rr.heading95),abs(nees-rr.heading_nees)/max(1.,nees))
                eig=float(np.linalg.eigvalsh(P[:,j]).min())
                audits.append({'case':case,'bias':bias,'arm':arm,'score_diff':diff,'min_eigenvalue':eig,'frames':len(t)})
                if diff>1e-8 or eig<=0:bad.append(audits[-1])
    pd.DataFrame(audits).to_csv(out/'INDEPENDENT_SAVED_TRACE_QA.csv',index=False)
    base=ev[ev.arm=='POWER1'].set_index(['case','bias'])
    contrasts=[]
    for r in ev.itertuples(index=False):
        b=base.loc[(r.case,r.bias)]
        contrasts.append({'case':r.case,'bias':r.bias,'arm':r.arm,'heading_rmse_deg':r.heading_rmse_deg,'rmse_change_vs_POWER':r.heading_rmse_deg-b.heading_rmse_deg,'rmse_ratio_vs_POWER':r.heading_rmse_deg/b.heading_rmse_deg,'heading95':r.heading95,'coverage_gap_change':abs(r.heading95-.95)-abs(b.heading95-.95),'nll_change_vs_POWER':r.heading_nll_rad-b.heading_nll_rad,'interval_width_ratio':r.interval95_mean_width_deg/b.interval95_mean_width_deg,'bias_rmse_ratio':r.gyro_bias_rmse_dps/b.gyro_bias_rmse_dps})
    con=pd.DataFrame(contrasts);con.to_csv(out/'CONTROLLED_CONTRASTS.csv',index=False)
    aggregate=[]
    for arm,d in con.groupby('arm'):
        aggregate.append({'arm':arm,'n_conditions':len(d),'heading_improved':int((d.rmse_change_vs_POWER<-1e-6).sum()),'heading_worse_10pct':int((d.rmse_ratio_vs_POWER>1.10).sum()),'coverage_closer_95':int((d.coverage_gap_change<-1e-6).sum()),'nll_improved':int((d.nll_change_vs_POWER<-1e-6).sum()),'median_rmse_ratio':float(d.rmse_ratio_vs_POWER.median()),'median_interval_width_ratio':float(d.interval_width_ratio.median())})
    pd.DataFrame(aggregate).to_csv(out/'DESCRIPTIVE_HYPOTHESIS_COUNTS.csv',index=False)
    local=[]
    for r in scores[scores.scope=='after_event'].itertuples(index=False):
        b=scores[(scores.case==r.case)&(scores.bias==r.bias)&(scores.scope=='after_event')&(scores.arm=='POWER1')]
        if len(b)==1 and r.arm.startswith('LOCAL_'):
            local.append({'case':r.case,'bias':r.bias,'arm':r.arm,'after_n':r.n,'after_heading_rmse_deg':r.heading_rmse_deg,'baseline_after_rmse_deg':b.iloc[0].heading_rmse_deg,'after_mean_deg':r.signed_mean_deg,'after_heading95':r.heading95,'baseline_after_heading95':b.iloc[0].heading95})
    pd.DataFrame(local).to_csv(out/'LOCAL_AFTER_EFFECTS.csv',index=False)
    receipts=[json.loads(p.read_text()) for p in root.rglob('RECEIPT.json')]
    info={'case_artifacts':len(scorefiles),'independently_scored_trajectories':len(audits),'saved_trace_files':len(list(root.rglob('*_TRACE.npz'))),'score_rows':len(scores),'evaluation_rows':len(ev),'errors':bad,'all_math_qa':qas,'case_receipts':receipts,'science_status':'EXPLORATORY_SAME_CORRIDOR_HYPOTHESIS_TEST','new_scene_validation':'NOT_TESTED_NO_NEW_FULL_RF','causal_scope':'physical event is measured detector sensitivity; no wall-level ray removal in this run'}
    (out/'FINAL_QA.json').write_text(json.dumps(info,indent=2,ensure_ascii=False))
    selected=ev[(ev.bias=='B0')&ev.arm.isin(['JOINT4','POWER1','MEM_WHITE','MEM_RS','MEM_R','MEM_S','STATIC_RICH','POWER_IEKF','POWER_SR4','POWER_RECOVERY','P4_HARD_BOTH','P4_UTILITY','LOCAL_MEM_KEEP','LOCAL_MEM_DROP'])]
    selected.to_csv(out/'KEY_B0.csv',index=False)
    print('FINAL_COUNTS',json.dumps({k:v for k,v in info.items() if k not in ['all_math_qa','case_receipts']}),flush=True)
    print('HYPOTHESIS_COUNTS',json.dumps(aggregate),flush=True)
    print('KEY_B0',selected[['case','arm','heading_rmse_deg','heading95','sigma_rms_deg','heading_nees','gyro_bias_rmse_dps']].to_json(orient='records'),flush=True)
    print('LOCAL_AFTER',json.dumps(local),flush=True)
    files=[]
    for p in out.rglob('*'):
        if p.is_file():files.append({'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    pd.DataFrame(files).to_csv(out/'MANIFEST.csv',index=False)
    if bad:raise SystemExit(2)

if __name__=='__main__':main()

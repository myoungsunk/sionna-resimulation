"""Verify all fixed Huber/gyro traces and summarize paired condition/seed results."""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

KEYS=['case','channel','range_model','condition','level','seed','arm','model']
GROUP=['condition','level','channel','range_model','arm','model']
FIELDS=['heading_rmse_deg','xy_rmse_m','mean_pose_NEES','mean_heading_NEES','pose95','heading95']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args()
    root=args.root;out=root/'ANALYSIS';out.mkdir(exist_ok=False)
    source=Path(__file__).resolve();repo=source.parents[5]
    for stage in ('SNOISE','S0','S1','S2','NOISE','L0','L1','L2'):
        m=json.loads((root/stage/'MANIFEST.json').read_text())
        assert m['status']=='COMPLETED' and m['exit_code']==0 and m['parity']['status']=='PASS'
        assert m['total_cells']==(24 if stage.startswith('S') else 504)
        for n,h in m['sha256'].items():assert sha(root/stage/n)==h,(stage,n)
        c=json.loads((root/stage/'EXECUTION_CONTRACT.json').read_text())
        for n,h in c['source_sha256'].items():assert sha(repo/n)==h,n
    assert json.loads((root/'NOISE/PARITY.json').read_text())['previous_noise_pair']['cells_per_model']=={'M0':252,'RF_HUBER_ONLY':252}
    all_rows=[];all_pooled=[];stage_receipts=[]
    for stage in ('NOISE','L0','L1','L2'):
        sums=defaultdict(lambda:np.zeros(14));errors=defaultdict(list)
        max_nees_diff=0.;max_heading_nees_diff=0.;min_eig=math.inf;count=0
        for c in pd.read_csv(root/stage/'RF_COMPONENT_TRACE.csv.gz',chunksize=50000,float_precision='round_trip'):
            n=len(c);p=np.empty((n,3,3))
            p[:,0,0]=c.Pxx;p[:,1,1]=c.Pyy;p[:,2,2]=c.Ppsi
            p[:,0,1]=p[:,1,0]=c.Pxy;p[:,0,2]=p[:,2,0]=c.Pxpsi;p[:,1,2]=p[:,2,1]=c.Pypsi
            e=np.column_stack([c.error_x,c.error_y,np.radians(c.heading_error_deg)])
            nees=np.einsum('ij,ij->i',e,np.linalg.solve(p,e[...,None])[...,0])
            hnees=e[:,2]**2/p[:,2,2]
            assert np.isfinite(p).all() and np.isfinite(e).all() and np.isfinite(nees).all()
            assert np.array_equal(nees<=7.814727903251179,c.pose95.to_numpy(bool))
            assert np.array_equal(hnees<=3.841458820694124,c.heading95.to_numpy(bool))
            max_nees_diff=max(max_nees_diff,float(np.max(np.abs(nees-c.pose_NEES))))
            max_heading_nees_diff=max(max_heading_nees_diff,float(np.max(np.abs(hnees-c.heading_NEES))))
            min_eig=min(min_eig,float(np.linalg.eigvalsh(p).min()))
            c['count']=1;c['h2']=c.heading_error_deg**2;c['p2']=c.error_x**2+c.error_y**2
            c['accepted']=(c.status=='applied').astype(int);c['rejected']=(c.status=='rejected_NIS').astype(int)
            c['weight_count']=c.huber_weight.notna().astype(int);c['weight_sum']=c.huber_weight.fillna(0)
            c['h_cov_ratio']=c.Ppsi/c.prior_Ppsi;c['p_cov_ratio']=(c.Pxx+c.Pyy)/(c.prior_Pxx+c.prior_Pyy)
            cols=['count','h2','p2','pose_NEES','heading_NEES','pose95','heading95','accepted','rejected',
                  'weight_count','weight_sum','h_cov_ratio','p_cov_ratio','true_bias_dps']
            for key,g in c.groupby(KEYS):
                sums[key]+=g[cols].sum().to_numpy(float)
                errors[key].append(np.column_stack([np.abs(g.heading_error_deg),np.sqrt(g.p2)]))
            count+=n
        ref=pd.read_csv(root/stage/'RF_COMPONENT_METRICS.csv',float_precision='round_trip').set_index(KEYS)
        assert len(sums)==len(ref)==504 and min_eig>0
        max_metric=0.;rows=[];group_errors=defaultdict(list)
        for key,a in sums.items():
            n=a[0];v=[np.sqrt(a[1]/n),np.sqrt(a[2]/n),a[3]/n,a[4]/n,a[5]/n,a[6]/n]
            r=ref.loc[key]
            max_metric=max(max_metric,float(np.max(np.abs(np.asarray(v)-r[FIELDS].to_numpy(float)))))
            assert n==r['n'] and a[7]==r.accepted_updates and a[8]==r.rejected_updates
            er=np.concatenate(errors[key]);row=dict(zip(KEYS,key));row.update(zip(FIELDS,v))
            row.update(n=int(n),heading_p95_deg=float(np.quantile(er[:,0],.95)),position_p95_m=float(np.quantile(er[:,1],.95)),
                       accepted_updates=int(a[7]),rejected_updates=int(a[8]),accept_fraction=a[7]/n,reject_fraction=a[8]/n,
                       mean_huber_weight=a[10]/a[9] if a[9] else np.nan,mean_heading_cov_ratio=a[11]/n,
                       mean_xy_cov_ratio=a[12]/n,true_bias_dps=a[13]/n)
            rows.append(row);group_errors[tuple(row[k] for k in GROUP)].append(er)
        assert max_metric<=1e-8 and max_nees_diff<=1e-8 and max_heading_nees_diff<=1e-8,(stage,max_metric,max_nees_diff,max_heading_nees_diff)
        frame=pd.DataFrame(rows)
        for key,g in frame.groupby(GROUP):
            row=dict(zip(GROUP,key));row.update(n=int(g.n.sum()),cells=len(g))
            for field in FIELDS:
                square=field in FIELDS[:2];z=np.average(g[field]**(2 if square else 1),weights=g.n)
                row[field]=float(np.sqrt(z) if square else z)
            for field in ['accept_fraction','reject_fraction','mean_heading_cov_ratio','mean_xy_cov_ratio']:
                row[field]=float(np.average(g[field],weights=g.n))
            er=np.concatenate(group_errors[key]);row.update(heading_p95_deg=float(np.quantile(er[:,0],.95)),position_p95_m=float(np.quantile(er[:,1],.95)))
            all_pooled.append(row)
        all_rows.extend(rows)
        stage_receipts.append(dict(stage=stage,cells=len(rows),trace_rows=count,metric_max_abs_error=max_metric,
                                   NEES_recompute_max_abs_error=max_nees_diff,heading_NEES_recompute_max_abs_error=max_heading_nees_diff,
                                   coverage_recomputed_exact=True,min_pose_cov_eigenvalue=min_eig))
        print(json.dumps(stage_receipts[-1]),flush=True)
    frame=pd.DataFrame(all_rows);frame.to_csv(out/'VERIFIED_CELL_METRICS.csv',index=False)
    pd.DataFrame(all_pooled).to_csv(out/'POOLED_METRICS.csv',index=False)
    case_rows=[]
    for key,g in frame.groupby(['case']+GROUP):
        r=dict(zip(['case']+GROUP,key));r.update(seeds=len(g),n=int(g.n.sum()))
        for f in FIELDS:
            square=f in FIELDS[:2];z=np.average(g[f]**(2 if square else 1),weights=g.n);r[f]=float(np.sqrt(z) if square else z)
        case_rows.append(r)
    cases=pd.DataFrame(case_rows);cases.to_csv(out/'CASE_METRICS.csv',index=False)
    contrasts=[]
    for key,g in frame.groupby(KEYS[:-1]):
        a=g[g.model=='M0'].iloc[0];b=g[g.model=='RF_HUBER_ONLY'].iloc[0]
        r=dict(zip(KEYS[:-1],key));r['true_bias_dps']=a.true_bias_dps
        for f in FIELDS+['heading_p95_deg','position_p95_m','reject_fraction']:
            r[f+'_difference']=float(b[f]-a[f])
        contrasts.append(r)
    pd.DataFrame(contrasts).to_csv(out/'PAIRED_CELL_CONTRASTS.csv',index=False)
    verdicts=[]
    for key,g in cases.groupby(GROUP[:-1]):
        a=g[g.model=='M0'].set_index('case');b=g[g.model=='RF_HUBER_ONLY'].set_index('case').loc[a.index]
        r=dict(zip(GROUP[:-1],key));r['cases']=len(a)
        for f in FIELDS:
            d=b[f]-a[f];r[f+'_increase_cases']=int((d>1e-8).sum());r[f+'_decrease_cases']=int((d< -1e-8).sum());r[f+'_numerical_ties']=int((abs(d)<=1e-8).sum())
        verdicts.append(r)
    pd.DataFrame(verdicts).to_csv(out/'CASE_DIRECTION_COUNTS.csv',index=False)
    receipt=dict(status='PASS',created_utc=datetime.now(timezone.utc).isoformat(),cells_verified=len(frame),
                 stages=stage_receipts,source_sha256=sha(source),scientific_PASS=False,
                 numerical_tie_tolerance=1e-8,numerical_ties_not_statistical_significance=True,
                 time_samples_independent=False,output_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'ANALYSIS_RECEIPT.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt))

if __name__=='__main__':main()

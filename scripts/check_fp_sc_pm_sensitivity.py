"""Reaggregate frozen diagnostic arrays without importing the diagnostic scorer."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import argparse,csv,json,sys
from pathlib import Path
import numpy as np
import psutil
p=psutil.Process();p.cpu_affinity(p.cpu_affinity()[:3])
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json,STEP_M

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    a.output.mkdir(exist_ok=False);run=a.run;r=json.loads((run/'RUN_RECEIPT.json').read_text())
    assert r['status']=='COMPLETE_DIAGNOSTIC_ONLY_NOT_PROVIDER_OR_E1_02'
    assert not r['E1_02_started'] and not r['E2_started'] and r['VALID_constructed']==0
    for path,h in r['input_hashes'].items():assert sha256(R/path)==h
    for path,h in r['code_hashes'].items():assert sha256(R/path)==h
    for path,h in r['files'].items():assert sha256(run/path)==h
    assert sha256(run.parent/'CONTRACT_KO.md')==r['contract_sha256']
    summary=json.loads((run/'SUMMARY.json').read_text());episodes=json.loads((run/'EPISODES.json').read_text())
    lookup={(x['case_id'],x['scenario'],x['mode'],x['stratum']):x for x in summary};assert len(lookup)==len(summary)
    epmap={(x['case_id'],x['scenario'],x['mode'],x['episode']):x for x in episodes};assert len(epmap)==len(episodes)
    grid=r['scenarios'];total=0;maxscore=0.;counts={};all_modes=r['modes'];arrays={};matched_summaries=0
    stress_path=next(R/p for p in r['input_hashes'] if p.endswith('/STRESS.csv'))
    with stress_path.open() as file:stress=list(csv.DictReader(file))
    stress_lookup={(v['case_id'],int(v['k']),v['stress']):v for v in stress}
    def compare(x,f,w,c,base):
        nonlocal matched_summaries
        tp=int(((f==1)&w).sum());fp=int(((f==1)&~w).sum());fn=int(((f==0)&w).sum());tn=int(((f==0)&~w).sum())
        hw=int(((f<0)&w).sum());hn=int(((f<0)&~w).sum());n=len(f)
        expected=dict(n=n,normal=int((~w).sum()),wrong=int(w.sum()),tp=tp,fp=fp,fn=fn,tn=tn,held_wrong=hw,held_normal=hn)
        for k,v in expected.items():assert x[k]==v,(k,x[k],v)
        def div(v,d):return v/d if d else None
        rates=dict(hypothetical_available_rate=div(tp+fp+tn+fn,n),hold_rate=div(hw+hn,n),
                   tpr_all=div(tp,tp+fn+hw),fpr_all=div(fp,fp+tn+hn),miss_burden_all=div(fn+hw,tp+fn+hw),
                   tpr_active=div(tp,tp+fn),fpr_active=div(fp,fp+tn),fnr_active=div(fn,fn+tp))
        for k,v in rates.items():assert x[k]==v
        for tag,b in [('vs_C',c),('vs_nominal',base)]:
            assert x[tag]==dict(new_detection=int(((f==1)&w&(b!=1)).sum()),new_false_alarm=int(((f==1)&~w&(b!=1)).sum()),
                lost_detection_to_negative=int(((f==0)&w&(b==1)).sum()),lost_detection_to_hold=int(((f<0)&w&(b==1)).sum()))
        assert sum((tp,fp,tn,fn,hw,hn))==n;matched_summaries+=1
    for path in sorted(run.glob('*_ONLINE.npz')):
        cid=path.name.removesuffix('_ONLINE.npz')
        with np.load(path,allow_pickle=False) as z:data={k:z[k] for k in z.files}
        with np.load(run/(cid+'_EVALUATOR.npz')) as z:ev={k:z[k] for k in z.files}
        f=data['flags'];scores=data['scores'];n=len(data['t']);total+=n;counts[cid]=n
        assert scores.shape==f.shape==(64,n,4)
        assert len(set(data['pose_id']))==n and np.array_equal(data['raw_tap'],data['selected_tap'])
        assert np.array_equal(data['scenario_ids'],[g['id'] for g in grid])
        pp=data['p_bounds'];mm=data['m_bounds'];j=data['history_j'];age=data['history_age'];t=data['t']
        assert np.all((j==-1)|(j<np.arange(n)[None,:]))
        finite_m=np.isfinite(mm).all(axis=2);assert not finite_m[:,0].any()
        assert np.all((age[finite_m]>0)&(age[finite_m]<=2))
        assert not finite_m[[i for i,g in enumerate(grid) if g['id']=='M_LAG_2.2']].any()
        # Separate geometric-distance-to-interval calculation of all score rows.
        raw_m=data['raw_tap'][None,:]*STEP_M
        p_distance=np.maximum(raw_m-pp[:,:,1],0)+np.maximum(pp[:,:,0]-raw_m,0)
        m_distance=np.maximum(raw_m-mm[:,:,1],0)+np.maximum(mm[:,:,0]-raw_m,0)
        p_ok=np.isfinite(pp).all(axis=2)&((pp[:,:,1]-pp[:,:,0])<=1.5)
        c_ok=np.isfinite(data['c_score'])&(data['raw_tap']>=0)
        for i,ok,extra in [(0,np.ones((64,n),bool),np.zeros((64,n))),
                           (1,p_ok,(p_distance/.15)**2),(2,finite_m,(m_distance/.15)**2),
                           (3,p_ok&finite_m,np.maximum((p_distance/.15)**2,(m_distance/.15)**2))]:
            ok=ok&c_ok[None,:];expected=data['c_score'][None,:]+extra
            assert np.array_equal(f[:,:,i]>=0,ok)
            assert np.isnan(scores[:,:,i][~ok]).all()
            err=float(np.max(abs(scores[:,:,i][ok]-expected[ok]))) if ok.any() else 0.;maxscore=max(maxscore,err);assert err<1e-10
            assert np.array_equal(f[:,:,i][ok],(expected[ok]>=2).astype(np.int8))
        # Rebuild each M interval from the saved past raw, elapsed time and known scenario.
        cumulative=np.cumsum(abs(data['ds']))
        for s,g in enumerate(grid):
            multiplier=np.ones(n)
            if g['profile']=='jump':multiplier[:n//2]=0
            if g['profile']=='drift':multiplier=np.minimum(1,np.maximum(0,(t-t[n//2])/10))
            center_p=(data['nominal_low']+data['nominal_high'])/2+multiplier*g['p_shift_taps']*STEP_M
            half_p=(data['nominal_high']-data['nominal_low'])*g['p_width_scale']/2
            expected_p=np.column_stack((center_p-half_p,center_p+half_p))
            if g['legacy']:expected_p=np.array([[float(stress_lookup[(cid,k,g['legacy'])][field]) for field in ('low','high')] for k in range(n)])
            assert np.max(abs(pp[s]-expected_p))<1e-10
            idx=np.flatnonzero(finite_m[s]);prev=j[s,idx]
            center=(data['raw_tap'][prev]+g['m_fp_shift_taps'])*STEP_M+data['offset'][idx]-data['offset'][prev]+g['m_offset_shift_taps']*STEP_M
            radius=np.maximum(.2*(t[idx]-t[prev]),cumulative[idx]-cumulative[prev])*g['m_motion_scale']+.17
            assert np.max(abs(mm[s,idx,0]-(center-radius)),initial=0)<1e-10
            assert np.max(abs(mm[s,idx,1]-(center+radius)),initial=0)<1e-10
            if g['event']=='reinitialize':assert np.all(j[s,n//2:][j[s,n//2:]>=0]>=n//2)
            valid=ev['label_valid'];w=ev['error_taps']!=0
            subsets={'all':valid,'normal':valid&(ev['error_taps']==0),'one_tap':valid&(ev['error_taps']==1),'large':valid&(ev['error_taps']>=2)}
            if g['profile']!='constant' or g['event']!='none':subsets.update(before=valid&(np.arange(n)<n//2),after=valid&(np.arange(n)>=n//2))
            for i,mode in enumerate(all_modes):
                for label,take in subsets.items():compare(lookup[(cid,g['id'],mode,label)],f[s,take,i],w[take],f[0,take,0],f[0,take,i])
                for ep in np.unique(ev['episode_id']):
                    take=valid&(ev['episode_id']==ep);compare(epmap[(cid,g['id'],mode,int(ep))],f[s,take,i],w[take],f[0,take,0],f[0,take,i])
        arrays[cid]=(data,ev)
    assert total==6272
    reg=json.loads((run/'REGRESSION_11095.json').read_text());stress_path=next(R/p for p in r['input_hashes'] if p.endswith('/STRESS.csv'))
    with stress_path.open() as file:stress=list(csv.DictReader(file))
    assert len(stress)==43904 and sum(int(x['narrow_reference_exclusion']) for x in stress)==11095
    for x in reg:
        data,ev=arrays[x['case_id']];s=next(i for i,g in enumerate(grid) if g['id']==x['scenario']);i=all_modes.index(x['mode'])
        take=np.array([int(v['k']) for v in stress if v['case_id']==x['case_id'] and 'LEGACY_'+v['stress']==x['scenario'] and v['narrow_reference_exclusion']=='1'],dtype=int)
        f=data['flags'];w=ev['error_taps']!=0;compare(x,f[s,take,i],w[take],f[0,take,0],f[0,take,i])
    verdict=dict(status='PASS_DIAGNOSTIC_OUTPUT_SELF_CHECK',source_rows=total,scenario_count=64,
        mode_rows=total*64*4,max_score_error=maxscore,summary_rows_checked=matched_summaries,source_cases=counts,
        regression_exclusions=11095,E1_02_started=False,E2_started=False,VALID_constructed=0,
        independent_audit=False,checker_sha256=sha256(Path(__file__)),run_receipt_sha256=sha256(run/'RUN_RECEIPT.json'))
    write_json(a.output/'CHECK.json',verdict);print(json.dumps(verdict),flush=True)

if __name__=='__main__':main()

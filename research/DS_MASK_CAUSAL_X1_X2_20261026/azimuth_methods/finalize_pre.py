"""Recover final aggregation from saved results; no optimizer/filter rerun."""
from prechecks import ROOT,BASE,SRC,CASES,PRIMARY,B,sha,dump,uncertainty
import numpy as np,pandas as pd,json
from pathlib import Path
def main():
    files=[ROOT/x for x in ['M3PRE_ALIGNMENT.csv','M2PRE_CONSISTENCY.csv','M2PRE_PACKETS.csv.gz','finalize_pre.py']]
    dump('PRE_AGGREGATION_LOCK.json',dict(files=[dict(path=str(p),sha256=sha(p)) for p in files],reason='Fix pandas T column access; frozen computed rows preserved'))
    a=pd.read_csv(ROOT/'M3PRE_ALIGNMENT.csv');m=pd.read_csv(ROOT/'M2PRE_CONSISTENCY.csv');raw=pd.read_csv(ROOT/'M2PRE_PACKETS.csv.gz');checks=[]
    def check(name,x,y,tol=1e-10):
        err=float(np.max(abs(np.asarray(x)-np.asarray(y))));assert err<=tol,(name,err);checks.append(dict(name=name,max_abs=err))
    assert len(a)==720 and len(m)==180
    assert not a.duplicated(['case','bias','arm','pass_id','T_pre','T_post','dof']).any()
    for row in m.itertuples():
        g=raw[(raw.case==row.case)&(raw.bias==row.bias)&(raw.arm==row.arm)&(raw['T']==row.T)&(raw.grp==row.grp)];v=g.loc[g.valid,'ratio'];assert len(g)==row.n and len(v)==row.n_valid
        if len(v)>=30:check('rolling_median',v.median(),row.ratio_med);check('rolling_p90',v.quantile(.9),row.ratio_p90)
    cases={x['id']:x for x in json.loads((SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']}
    for (cid,bias,arm),gg in a[a.dof==2].groupby(['case','bias','arm']):
        z=np.load(BASE/'e1_e4/E1'/f'{cid}_{bias}.npz');j=list(z['names']).index('A0' if arm=='BB' else 'A1');t=np.round(z['t_s'],8);x=z['x'][:,j,:2];anc=np.array(cases[cid]['anchor'])[:2];height=cases[cid]['anchor'][2]-cases[cid]['robot_z_m'];truth=z['truth_scoring_only']
        for row in gg.itertuples():
            idx=np.flatnonzero((t>=row.window_start_s)&(t<=row.window_end_s));k0,k1=idx[0],idx[-1];used=idx[z['acc'][idx,j]];assert len(used)==row.n_range
            q=x[used]-x[k0];v=x[k0]+np.array([row.dx_cm,row.dy_cm])/100;u=q+v-anc;dist=np.sqrt(np.sum(u*u,axis=1)+height*height);sd=np.sqrt(z['R'][used,j,0,0]);J=u/dist[:,None]/sd[:,None];res=(dist+B-z['nu'][used,j,0]-z['h'][used,j,0])/sd;w=np.minimum(1,1.345/np.maximum(abs(res),1e-300));I=J.T@(w[:,None]*J)
            end=x[k1]-x[k0]+v;ur=(end-anc)/np.linalg.norm(end-anc);ut=np.array([-ur[1],ur[0]]);sigma,cond,valid=uncertainty(I,ut)
            if valid:check('alignment_sigma_cm',sigma*100,row.sigma_dt_cm,1e-8)
            gt=truth[k1,:2]-anc;gt/=np.linalg.norm(gt);utg=np.array([-gt[1],gt[0]])
            check('alignment_end_et',utg@(end-truth[k1,:2])*100,row.et_aligned_end_cm,1e-8)
            null=np.r_[-(v-anc)[1],(v-anc)[0],1];J3=np.column_stack([J,np.einsum('ni,ni->n',J,np.column_stack([-q[:,1],q[:,0]]))]);check('rotation_null',J3@null,np.zeros(len(J)),1e-10)
            expected=valid and row.solver_success and row.n_range>=30 and np.isfinite(row.reduction) and row.reduction>=.5 and sigma*100<3
            assert bool(row.pass_goal)==bool(expected)
    m3=[]
    for pre in [5,10,20]:
        for post in [5,10,20]:
            d=a[(a.dof==2)&(a.arm=='MB')&(a.T_pre==pre)&(a.T_post==post)];count=0
            for cid in PRIMARY:
                q=d[(d.case==cid)&(d.pass_id==1)];count+=int(len(q)==2 and q.pass_goal.all())
            r5=d[d.case.str.startswith('R5')];robust=len(r5)==12 and bool(r5.pass_goal.all());m3.append(dict(T_pre=pre,T_post=post,primary_case_pass_count=count,R5_pass_count=int(r5.pass_goal.sum()),R5_expected_count=12,R5_all_pass=robust,GO=bool(count>=2 and robust)))
    m2=[];details=[]
    for T in [5,10,20]:
        count=0;strengths=[]
        for cid in PRIMARY:
            pair=[]
            for bias in ['B0','L2']:
                s=m[(m.case==cid)&(m.bias==bias)&(m.arm=='MB')&(m['T']==T)].set_index('grp').ratio_med
                rm=s['near']/s['mid'] if s['mid']>0 else np.nan;rf=s['near']/s['far'] if s['far']>0 else np.nan;ok=bool(rm>=2 and rf>=2);pair.append(ok)
                if np.isfinite(rm) and np.isfinite(rf):strengths.append(min(rm,rf))
                details.append(dict(case=cid,bias=bias,T=T,near_mid_ratio=rm,near_far_ratio=rf,GO=ok))
            count+=int(all(pair))
        m2.append(dict(T=T,primary_case_pass_count=count,contrast_strength=float(np.median(strengths)) if strengths else None,GO=bool(count>=2)))
    go=[r for r in m2 if r['GO']];chosen=sorted(go,key=lambda r:(-r['primary_case_pass_count'],-r['contrast_strength'],r['T']))[0]['T'] if go else None
    pd.DataFrame(m3).to_csv(ROOT/'M3PRE_DECISIONS.csv',index=False);pd.DataFrame(m2).to_csv(ROOT/'M2PRE_DECISIONS.csv',index=False);pd.DataFrame(details).to_csv(ROOT/'M2PRE_CONTRASTS.csv',index=False,na_rep='NA')
    for f in json.loads((ROOT/'INPUT_LOCK.json').read_text())['files']:assert sha(Path(f['path']))==f['sha256']
    dump('PRE_CHECKS.json',dict(status='PASS',checks=checks,source_hashes_unchanged=True,aggregation_failure_preserved='PRE_FAILURE.json',no_filter_replay=True))
    result=dict(M3_pre='GO' if any(x['GO'] for x in m3) else 'NO_GO',M2_pre='GO' if go else 'NO_GO',M2_selected_T=chosen,M3_alignment_rows=len(a),M2_packet_rows=len(raw))
    dump('PRE_RESULT.json',result);print(result);print(pd.DataFrame(m3).to_string(index=False));print(pd.DataFrame(m2).to_string(index=False))
if __name__=='__main__':main()

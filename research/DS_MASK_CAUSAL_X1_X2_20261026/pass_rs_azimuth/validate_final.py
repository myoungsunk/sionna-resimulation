from pathlib import Path
import json,hashlib,shutil
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent
def main():
    checks=[];maxerr={};p=pd.read_csv(R/'P2_PASSES_GT.csv');p=p[p.primary]
    table=pd.read_csv(R/'P1_RS_TABLE.csv')
    manifest=json.loads(Path(r'D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text());cases={x['id']:x for x in manifest['cases']}
    def eq(name,a,b,tol):
        err=float(np.max(np.abs(np.asarray(a).astype(float)-np.asarray(b).astype(float))));assert err<=tol,(name,err)
        maxerr[name]=max(maxerr.get(name,0),err);checks.append(name)
    for name in ['INPUT_LOCK.json','STAGE0_LOCK.json','RS_INPUT_LOCK.json','RT_INPUT_LOCK.json']:
        for f in json.loads((R/name).read_text(encoding='utf-8'))['files']:
            assert hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()==f['sha256'],f['path'];checks.append('input_hash')
    for f,h in json.loads((R/'2A_INPUT_LOCK.json').read_text()).items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h
    gate_rows=[]
    for stage in ['RS0','RS1_RS2','RT_OFF','RT_CUT']:
        for pp in p.itertuples():
            z=np.load(R/stage/f'{pp.case}_{pp.bias}.npz');ref=np.load(R.parent/'e1_e4/E1'/f'{pp.case}_{pp.bias}.npz');ab=ref['acc'][:,list(ref['names']).index('A0')];t=np.round(z['t_s'],8)
            for j,name in enumerate(z['names']):
                jr=list(ref['names']).index('A0' if name.endswith('BB') else 'A1')
                mu=z['mu'][:,j];rr=z['R'][:,j];prior=z['prior'][:,j];P=z['Pprior'][:,j];H=z['H'][:,j];nu=z['nu'][:,j];acc=z['acc'][:,j]
                eq('frozen_mean',mu,ref['mu'][:,jr],0);eq('frozen_Rrange',rr[:,0,:],ref['R'][:,jr,0,:],0);eq('frozen_Roffdiag',rr[:,1,0],ref['R'][:,jr,1,0],0)
                d=np.linalg.norm(prior[:,:2]-np.array(cases[pp.case]['anchor'])[:2],axis=1)
                expected_r=ref['R'][:,jr,1,1].copy();weight=np.zeros(len(d))
                if name.startswith(('RS1_','RS2_')):
                    tab=table[table.route_holdout==pp.case.split('_')[0]].set_index('bin')
                    for k in np.flatnonzero(d<2):
                        b='0-.5' if d[k]<.5 else '.5-1' if d[k]<1 else '1-1.5'
                        weight[k]=1 if d[k]<1.5 else 2*(2-d[k]);expected_r[k]=np.exp(weight[k]*np.log(tab.loc[b,'var'])+(1-weight[k])*np.log(expected_r[k]))
                eq('Rss',rr[:,1,1],expected_r,1e-15)
                if stage.startswith('RS'):eq('distance',z['d_est'][:,j],d,1e-12);eq('blend_weight',z['blend_weight'][:,j],weight,1e-12)
                hp=H@P;cov=hp@H.swapaxes(-1,-2)+rr;cov=.5*(cov+cov.swapaxes(-1,-2));K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
                nis=np.einsum('ni,ni->n',nu,np.linalg.solve(cov,nu[...,None])[...,0])
                if name.startswith('RS2_'):eq('natural_gate',acc,nis<=9.21034037197618,0)
                else:eq('fixed_AB',acc,ab,0)
                if stage=='RT_CUT':
                    active=np.ones(len(t),bool) if name.startswith('ALL') else (t>=pp.window_start_s)&(t<=pp.window_end_s)
                    rad=(prior[:,:2]-np.array(cases[pp.case]['anchor'])[:2])/d[:,None];ut=np.column_stack([-rad[:,1],rad[:,0]])
                    K[active,:2,0]-=np.einsum('ni,ni->n',ut[active],K[active,:2,0])[:,None]*ut[active]
                    eq('RT_tangent_zero',np.einsum('ni,ni->n',ut[active],K[active,:2,0]),np.zeros(active.sum()),1e-12)
                eq('gain',K,z['K'][:,j],1e-10)
                A=np.eye(4)-K@H;post=A@P@A.swapaxes(-1,-2)+K@rr@K.swapaxes(-1,-2);post=.5*(post+post.swapaxes(-1,-2));post[~acc]=P[~acc]
                eq('Joseph',post,z['P'][:,j],1e-10)
                window=(t>=pp.window_start_s)&(t<=pp.window_end_s)
                gate_rows.append(dict(case=pp.case,bias=pp.bias,arm=name,window_n=int(window.sum()),AB_accepted=int((window&ab).sum()),actual_accepted=int((window&acc).sum()),new_rejected=int((window&ab&~acc).sum()),new_accepted=int((window&~ab&acc).sum()),new_reject_fraction=float((window&ab&~acc).sum()/(window&ab).sum())))
    pd.DataFrame(gate_rows).to_csv(R/'ACTUAL_GATE_CHANGES.csv',index=False)
    for name in ['RS_MANAGED_FINISH.json','RT_MANAGED_FINISH.json']:
        x=json.loads((R/name).read_text(encoding='utf-8-sig'))['processes'][0]
        assert x['exit_code']==0 and x['ref_count']==0 and all(x[k]['state']=='absent' for k in ['actual_process','actual_supervisor','job'])
        target=R/'logs'/name.split('_')[0];target.mkdir(parents=True,exist_ok=True)
        for f in ['stdout.log','stderr.log']:shutil.copyfile(Path(x['log_dir'])/f,target/f)
    result=dict(status='PASS',check_count=len(checks),max_abs_errors=maxerr,inputs_unchanged=True,managed_helpers_terminated=True)
    (R/'FINAL_CHECKS.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()

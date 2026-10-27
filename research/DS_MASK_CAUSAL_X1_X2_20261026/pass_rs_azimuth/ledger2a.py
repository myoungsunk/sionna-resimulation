from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
def main():
    assert json.loads((ROOT/'RS_EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
    assert not (ROOT/'2A_GATE.json').exists()
    p=pd.read_csv(ROOT/'P2_PASSES_GT.csv');p=p[p.primary]
    manifest_path=Path(r'D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json')
    manifest=json.loads(manifest_path.read_text())
    cases={c['id']:c for c in manifest['cases']}
    locked=[manifest_path,ROOT/'EXPERIMENT2_DEFINITIONS.md',Path(__file__),ROOT/'P2_PASSES_GT.csv']+[ROOT.parent/'e1_e4/E1'/f'{r.case}_{r.bias}.npz' for r in p.itertuples()]
    hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in locked}
    (ROOT/'2A_INPUT_LOCK.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    rows=[];series=[];checks=[]
    for row in p.itertuples():
        z=np.load(ROOT.parent/'e1_e4/E1'/f'{row.case}_{row.bias}.npz');ids=[list(z['names']).index(x) for x in ['A0','A1']]
        t=np.round(z['t_s'],8);x=z['x'][:,ids,:2];prior=z['prior'][:,ids,:2];truth=z['truth_scoring_only'][:,:2]
        anchor=np.array(cases[row.case]['anchor'])[:2];rad=truth-anchor;ur=rad/np.linalg.norm(rad,axis=1)[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
        prop=np.zeros_like(x);prop[1:]=prior[1:]-x[:-1]-np.diff(truth,axis=0)[:,None,:]
        K=z['K'][:,ids,:2,:];nu=z['nu'][:,ids];acc=z['acc'][:,ids]
        rng=K[:,:,:,0]*nu[:,:,0,None]*acc[:,:,None];pol=K[:,:,:,1]*nu[:,:,1,None]*acc[:,:,None]
        ru=prior-anchor;ru/=np.linalg.norm(ru,axis=2)[:,:,None]
        rrad=np.einsum('nji,nji->nj',rng,ru)[:,:,None]*ru;rtan=rng-rrad
        j0=int(np.flatnonzero(t>=row.window_start_s)[0]);initial=(x[j0-1,1]-x[j0-1,0]) if j0 else prior[0,1]-prior[0,0]
        components={'prop':prop,'rng_rad':rrad,'rng_tan':rtan,'pol':pol}
        vals={'initial':ut@initial*100};passvals={}
        for name,vec in components.items():
            gap=vec[:,1]-vec[:,0];gap[:j0]=0
            vals[name]=np.einsum('ni,ni->n',ut,np.cumsum(gap,axis=0))*100
            onlypass=gap.copy();onlypass[t>row.window_end_s]=0
            passvals[name]=np.einsum('ni,ni->n',ut,np.cumsum(onlypass,axis=0))*100
        observed=np.einsum('ni,ni->n',ut,x[:,1]-x[:,0])*100
        got=sum(vals.values());err=float(np.max(abs(got[j0:]-observed[j0:])))
        checks.append(dict(case=row.case,bias=row.bias,packet_max_abs_cm=err));assert err<=1e-10
        post=(t>row.post_start_s)&(t<=row.post_end_s)
        # First pass next-start endpoint cannot occur here when the full 30s window fits.
        eps=p[(p.case==row.case)&(p.bias==row.bias)]
        assert row.valid_post and row.post_n==int(post.sum())
        denom=float(observed[post].mean());out=dict(case=row.case,bias=row.bias,pass_id=row.pass_id,post_gap_cm=denom)
        for name,v in vals.items():
            value=float(v[post].mean());out[name+'_cm']=value;out[name+'_share']=value/denom if abs(denom)>1e-10 else np.nan
            if name in passvals:
                out[name+'_window_increment_cm']=float(passvals[name][post].mean())
                out[name+'_after_window_increment_cm']=value-out[name+'_window_increment_cm']
        out['sum_error_cm']=abs(sum(out[k+'_cm'] for k in vals)-denom);assert out['sum_error_cm']<=1e-10
        out['CUT_RT_trigger']=bool(out['rng_tan_share']>=.3)
        out['H1_descriptive']=bool(out['rng_rad_share']>=.5)
        out['review_prop_pol']=bool(out['prop_share']>=.5 or out['pol_share']>=.5)
        rows.append(out)
        for k in np.flatnonzero(t>=row.window_start_s):
            series.append(dict(case=row.case,bias=row.bias,k=k,t_s=t[k],d_gt_m=np.linalg.norm(rad[k]),observed_gap_cm=observed[k],**{name+'_cm':v[k] for name,v in vals.items()}))
    pd.DataFrame(rows).to_csv(ROOT/'2A_LEDGER_PASS.csv',index=False)
    pd.DataFrame(series).to_csv(ROOT/'2A_LEDGER_SERIES.csv.gz',index=False,compression='gzip')
    for f,h in hashes.items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h
    (ROOT/'2A_GATE.json').write_text(json.dumps(dict(status='PASS',checks=checks,CUT_RT_trigger=any(r['CUT_RT_trigger'] for r in rows),no_replay=True),indent=2),encoding='utf-8')
    print(pd.DataFrame(rows)[['case','bias','post_gap_cm','initial_cm','prop_share','rng_rad_share','rng_tan_share','pol_share','CUT_RT_trigger']].to_string(index=False))
if __name__=='__main__':main()

"""Remove only tangential XY entries of the joint range gain; Joseph P."""
from run_rs import ROOT,S,E,V,np,pd,PRIMARY
import json,traceback,sys

def main():
    gate=json.loads((ROOT/'2A_GATE.json').read_text());assert gate['status']=='PASS' and gate['CUT_RT_trigger']
    locked=json.loads((ROOT/'RS_INPUT_LOCK.json').read_text())['files']
    locked=locked+[dict(path=str(p),sha256=S.sha(p)) for p in [ROOT/'run_rt.py',ROOT/'2A_GATE.json',ROOT/'EXPERIMENT2_DEFINITIONS.md',ROOT/'RT_DEFINITIONS.md',ROOT/'P2_PASSES_GT.csv']]
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('RT_INPUT_LOCK.json',dict(files=locked,command=sys.argv,utc=S.now()))
    model=V.SourceFFD();passes=pd.read_csv(ROOT/'P2_PASSES_GT.csv')
    feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
    cache=[]
    for case in V.MANIFEST['cases']:
        if case['id'] not in PRIMARY:continue
        for bias in ['B0','L2']:
            inp=S.load_case(case,bias,feat,par,mr,hg)
            with np.load(ROOT.parent/'e1_e4/E1'/f'{case["id"]}_{bias}.npz') as z:ref={k:z[k] for k in z.files}
            j=list(ref['names']).index('A0');mask=np.column_stack([ref['acc'][:,j],ref['acc'][:,j]])
            p=passes[(passes.case==case['id'])&(passes.bias==bias)&passes.primary].iloc[0]
            cache.append((case,bias,inp,ref,mask,p))
    scores=[];original=E.update;checkrows=[]
    for stage in ['RT_OFF','RT_CUT']:
        specs=[dict(name=f'{kind}_{arm}',alpha=i) for kind in (['OFF'] if stage=='RT_OFF' else ['PASS','ALL']) for arm,i in [('BB',0),('MB',1)]]
        for case,bias,inp,ref,mask,p in cache:
            counter=[0];removed=[]
            def update(x,P,z,h,H,mu,R,mode):
                k=counter[0];counter[0]+=1
                assert k<len(inp['t']) and x.shape[0]==len(specs)
                v=z-h-mu;hp=H@P;cov=hp@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2));K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
                raw=K.copy();rad=x[:,:2]-np.array(case['anchor'])[:2];rad/=np.linalg.norm(rad,axis=1)[:,None];ut=np.column_stack([-rad[:,1],rad[:,0]])
                active=np.zeros(len(specs),bool)
                for j,s in enumerate(specs):
                    active[j]=stage=='RT_CUT' and (s['name'].startswith('ALL') or p.window_start_s<=round(float(inp['t'][k]),8)<=p.window_end_s)
                    if active[j]:K[j,:2,0]-=ut[j]*(ut[j]@K[j,:2,0])
                if active.any():assert np.max(abs(np.einsum('ni,ni->n',ut[active],K[active,:2,0])))<1e-12
                assert np.array_equal(K[:,:,1],raw[:,:,1]) and np.array_equal(K[:,2:,0],raw[:,2:,0])
                removed.append(dict(k=k,t_s=float(inp['t'][k]),pose_id=int(inp['ids'][k]),pass_active=bool(active[0]),all_active=bool(active[-1])))
                y=x+np.einsum('nij,nj->ni',K,v);y[:,2]=V.MC.wrap(y[:,2]);A=np.eye(4)[None]-K@H;cp=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);cp=.5*(cp+cp.swapaxes(-1,-2))
                yes=mode>0
                return np.where(yes[:,None],y,x),np.where(yes[:,None,None],cp,P),K
            E.update=update
            S.event('RT_CASE_START',stage_name=stage,case=case['id'],bias=bias)
            out=E.replay(case,inp,model,specs,mask)
            E.update=original;assert counter[0]==len(inp['t'])
            pd.DataFrame(removed).to_csv(ROOT/f'{stage}_{case["id"]}_{bias}_schedule.csv',index=False)
            if stage=='RT_OFF':
                for j,arm in enumerate(['A0','A1']):
                    jr=list(ref['names']).index(arm)
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
                        diff=out[key][:,j].astype(float)-ref[key][:,jr].astype(float)
                        if key in ['x','prior']:diff[:,2]=V.MC.wrap(diff[:,2])
                        S.check(case['id']+bias+arm+key,diff,np.zeros_like(diff),1e-10)
            scores.extend(E.score(stage,case,bias,inp,out,specs,0));pd.DataFrame(scores).to_csv(ROOT/'RT_SCORES.csv',index=False)
            S.write('RT_CHECKS.json',S.checks);S.event('RT_CASE_PASS',stage_name=stage,case=case['id'],bias=bias)
        S.write(stage+'_GATE.json',dict(status='PASS',conditions=6))
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('RT_EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',inputs_unchanged=True,utc=S.now()))

if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('RT_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise

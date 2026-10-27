"""Frozen-mean RS0/RS1/RS2 experiment; no training, no process-noise change."""
from pathlib import Path
import os,sys,json,importlib.util,traceback
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
spec=importlib.util.spec_from_file_location('frozen_e',r'D:/SLAM_bot/DS_NONLINEAR_E1_E4_20261027_01a1775b/run_experiments.py')
E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
S=E.S;S.ROOT=ROOT;E.ROOT=ROOT;os.environ['PJ_OUT']=str(ROOT/'runtime_rs')
sys.path.insert(0,str(S.PKG))
import v_replay as V
import numpy as np
import pandas as pd
E.V=V;S.V=V
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']

def run(case,inp,model,specs,ab,table):
    n=len(inp['t']);J=len(specs);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1))
    out={k:np.empty((n,J)+sh) for k,sh in {'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'K':(4,2),'mu':(2,),'R':(2,2),'nu':(2,)}.items()}
    for k in ['d_est','blend_weight','nis']:out[k]=np.zeros((n,J))
    out['acc']=np.zeros((n,J),bool)
    for k in range(n):
        if k%128==0:S.stopcheck()
        if k:
            c=inp['controls']
            for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));R=np.tile(inp['R'][k],(J,1,1));z=np.tile(inp['z'][k],(J,1))
        d=np.linalg.norm(x[:,:2]-np.array(case['anchor'])[:2],axis=1);weight=np.zeros(J)
        for j,s in enumerate(specs):
            mu[j,0]+=s['alpha']*(inp['pred'][k]-mu[j,0])
            if s['rs'] and d[j]<2:
                label=['0-.5','.5-1','1-1.5'][min(int(np.searchsorted([0,.5,1,1.5],d[j],side='right')-1),2)]
                row=table.loc[label];assert row.valid and row['var']>0
                weight[j]=1 if d[j]<1.5 else (2-d[j])/.5
                R[j,1,1]=np.exp(weight[j]*np.log(row['var'])+(1-weight[j])*np.log(R[j,1,1]))
        nu=z-h-mu;cov=H@P@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2))
        nis=np.einsum('ni,ni->n',nu,np.linalg.solve(cov,nu[...,None])[...,0]);mode=np.array([int(nis[j]<=V.MC.G2) if s['rs']==2 else int(ab[k]) for j,s in enumerate(specs)])
        for key,v in [('prior',x),('Pprior',P),('h',h),('H',H),('mu',mu),('R',R),('nu',nu),('d_est',d),('blend_weight',weight),('nis',nis)]:out[key][k]=v
        x,P,K=E.update(x,P,z,h,H,mu,R,mode)
        out['x'][k]=x;out['P'][k]=P;out['K'][k]=K;out['acc'][k]=mode>0
    assert all(np.isfinite(out[key]).all() for key in out)
    for key in ['P','Pprior']:
        assert np.max(abs(out[key]-out[key].swapaxes(-1,-2)))<1e-12
        assert np.linalg.eigvalsh(out[key]).min()>=-1e-12
    rejected=~out['acc']
    if rejected.any():
        S.check('reject_x',out['x'][rejected],out['prior'][rejected],0)
        S.check('reject_P',out['P'][rejected],out['Pprior'][rejected],0)
    for j,s in enumerate(specs):
        if s['rs']!=2:S.check(s['name']+'_fixed_AB',out['acc'][:,j],ab,0)
        else:S.check(s['name']+'_natural_gate',out['acc'][:,j],out['nis'][:,j]<=V.MC.G2,0)
        S.check('mu_s_unchanged',out['mu'][:,j,1],inp['mu'][:,1],0)
        S.check('Rrr_unchanged',out['R'][:,j,0,0],inp['R'][:,0,0],0)
    return out

def main():
    assert json.loads((ROOT/'STAGE0_DECISION.json').read_text())['overall']=='GO'
    locked=json.loads((ROOT.parent/'pol_azimuth_alloc/INPUT_LOCK.json').read_text())['files']
    # Verify the inherited immutable source/data lock, excluding only old diagnostic output code.
    for item in locked:assert S.sha(item['path'])==item['sha256'],item['path']
    extra=[ROOT/'run_rs.py',ROOT/'PROTOCOL_ADDENDUM.md',ROOT/'P1_RS_TABLE.csv',ROOT/'STAGE0_DECISION.json',Path(E.__file__),Path(S.__file__)]
    locked=locked+[dict(path=str(p),sha256=S.sha(p)) for p in extra]
    S.write('RS_INPUT_LOCK.json',dict(files=locked,command=sys.argv,utc=S.now()))
    S.test_update();model=V.SourceFFD()
    feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
    cache=[];table=pd.read_csv(ROOT/'P1_RS_TABLE.csv')
    for case in V.MANIFEST['cases']:
        if case['id'] not in PRIMARY:continue
        for bias in ['B0','L2']:
            inp=S.load_case(case,bias,feat,par,mr,hg)
            with np.load(ROOT.parent/'e1_e4/E1'/f'{case["id"]}_{bias}.npz') as z:ref={k:z[k] for k in z.files}
            S.check('pose_id',inp['ids'],ref['pose_id'],0);S.check('time',inp['t'],ref['t_s'],0)
            j=list(ref['names']).index('A0');ab=ref['acc'][:,j]
            cache.append((case,bias,inp,ref,ab,table[table.route_holdout==case['route']].set_index('bin')))
    scores=[]
    for stage in ['RS0','RS1_RS2']:
        specs=[dict(name=f'RS{r}_{a}',alpha=i,rs=r) for r in ([0] if stage=='RS0' else [1,2]) for a,i in [('BB',0),('MB',1)]]
        for case,bias,inp,ref,ab,tab in cache:
            S.event('RS_CASE_START',stage_name=stage,case=case['id'],bias=bias)
            out=run(case,inp,model,specs,ab,tab)
            if stage=='RS0':
                for j,arm in enumerate(['A0','A1']):
                    jr=list(ref['names']).index(arm)
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
                        v=out[key][:,j].astype(float)-ref[key][:,jr].astype(float)
                        if key in ['x','prior']:v[:,2]=V.MC.wrap(v[:,2])
                        S.check(case['id']+bias+arm+'_'+key,v,np.zeros_like(v),1e-10)
            scores.extend(E.score(stage,case,bias,inp,out,specs,0))
            pd.DataFrame(scores).to_csv(ROOT/'RS_SCORES.csv',index=False)
            S.write('RS_CHECKS.json',S.checks);S.event('RS_CASE_PASS',stage_name=stage,case=case['id'],bias=bias)
        S.write(stage+'_GATE.json',dict(status='PASS',meaning='Numerical/implementation gate only',conditions=6))
    for item in locked:assert S.sha(item['path'])==item['sha256'],item['path']
    S.write('RS_EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',utc=S.now(),inputs_unchanged=True,RS3_executed=False,Q_unchanged=True,retraining=False))

if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('RS_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise

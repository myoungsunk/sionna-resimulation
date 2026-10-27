"""Online-distance tangent gain sweep; frozen A_B and original controls."""
from pathlib import Path
import os,sys,json,importlib.util,traceback
ROOT=Path(__file__).resolve().parent;sys.dont_write_bytecode=True
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
spec=importlib.util.spec_from_file_location('frozen_e',r'D:/SLAM_bot/DS_NONLINEAR_E1_E4_20261027_01a1775b/run_experiments.py');E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
S=E.S;S.ROOT=ROOT;E.ROOT=ROOT;os.environ['PJ_OUT']=str(ROOT/'runtime_m1');sys.path.insert(0,str(S.PKG))
import v_replay as V
import numpy as np
import pandas as pd
E.V=V;S.V=V
CASES=['R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']

def update(x,P,z,h,H,mu,R,accept,lam,ut):
    v=z-h-mu;hp=H@P;cov=hp@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2));K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
    raw_tan=np.einsum('ni,ni->n',ut,K[:,:2,0]);K[:,:2,0]-=(1-lam)[:,None]*raw_tan[:,None]*ut
    assert np.max(abs(np.einsum('ni,ni->n',ut,K[:,:2,0])-lam*raw_tan))<1e-12
    y=x+np.einsum('nij,nj->ni',K,v);y[:,2]=V.MC.wrap(y[:,2]);A=np.eye(4)[None]-K@H;pp=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);pp=.5*(pp+pp.swapaxes(-1,-2))
    return np.where(accept[:,None],y,x),np.where(accept[:,None,None],pp,P),K

def replay(case,inp,model,specs,ab):
    n=len(inp['t']);J=len(specs);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1))
    out={k:np.empty((n,J)+sh) for k,sh in {'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'K':(4,2),'mu':(2,),'R':(2,2),'nu':(2,)}.items()}
    for k in ['d_est','lambda_effective','range_R_scale']:out[k]=np.zeros((n,J))
    out['acc']=np.zeros((n,J),bool)
    for k in range(n):
        if k%128==0:S.stopcheck()
        if k:
            c=inp['controls']
            for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));R=np.tile(inp['R'][k],(J,1,1));z=np.tile(inp['z'][k],(J,1))
        radial=x[:,:2]-np.array(case['anchor'])[:2];d=np.linalg.norm(radial,axis=1);ur=radial/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]]);lam=np.ones(J);scale=np.ones(J)
        for j,s in enumerate(specs):
            mu[j,0]+=s['alpha']*(inp['pred'][k]-mu[j,0])
            if d[j]<s['D']:lam[j]=s['lam'];scale[j]=s['rscale'];R[j,0,0]*=scale[j]
        for key,v in [('prior',x),('Pprior',P),('h',h),('H',H),('mu',mu),('R',R),('nu',z-h-mu),('d_est',d),('lambda_effective',lam),('range_R_scale',scale)]:out[key][k]=v
        yes=np.full(J,ab[k]);x,P,K=update(x,P,z,h,H,mu,R,yes,lam,ut);out['x'][k]=x;out['P'][k]=P;out['K'][k]=K;out['acc'][k]=yes
    for key in out:assert np.isfinite(out[key]).all(),key
    for key in ['P','Pprior']:
        assert abs(out[key]-out[key].swapaxes(-1,-2)).max()<1e-12
        assert np.linalg.eigvalsh(out[key]).min()>=-1e-12
    reject=~out['acc']
    if reject.any():S.check('reject_x',out['x'][reject],out['prior'][reject],0);S.check('reject_P',out['P'][reject],out['Pprior'][reject],0)
    for j,s in enumerate(specs):S.check('fixed_AB',out['acc'][:,j],ab,0);S.check('frozen_mu_s',out['mu'][:,j,1],inp['mu'][:,1],0);S.check('frozen_Rss',out['R'][:,j,1,1],inp['R'][:,1,1],0)
    return out

def main():
    locked=json.loads((ROOT.parent/'pass_rs_azimuth/RS_INPUT_LOCK.json').read_text())['files']
    locked+= [dict(path=str(p),sha256=S.sha(p)) for p in [ROOT/'run_m1.py',ROOT/'DEFINITIONS.md',ROOT/'PROTOCOL.md']]
    for r in locked:assert S.sha(r['path'])==r['sha256'],r['path']
    S.write('M1_INPUT_LOCK.json',dict(files=locked,utc=S.now(),command=sys.argv));model=V.SourceFFD()
    feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
    cache=[]
    for case in V.MANIFEST['cases']:
        if case['id'] not in CASES:continue
        for bias in ['B0','L2']:
            inp=S.load_case(case,bias,feat,par,mr,hg)
            with np.load(ROOT.parent/'e1_e4/E1'/f'{case["id"]}_{bias}.npz') as f:ref={k:f[k] for k in f.files}
            S.check('pose_id',inp['ids'],ref['pose_id'],0);S.check('time',inp['t'],ref['t_s'],0);ab=ref['acc'][:,list(ref['names']).index('A0')];cache.append((case,bias,inp,ref,ab))
    scores=[]
    for stage in ['M1_OFF','M1_SWEEP']:
        variants=[('0',1,0,1)] if stage=='M1_OFF' else [('a',.5,1.5,1),('b',.25,1.5,1),('c',0,1.5,1),('d',.5,2.5,1),('e',1,1.5,4)]
        specs=[dict(name='M1-'+v+'_'+arm,alpha=alpha,lam=lam,D=D,rscale=rr) for v,lam,D,rr in variants for arm,alpha in [('BB',0),('MB',1)]]
        for case,bias,inp,ref,ab in cache:
            S.event('M1_START',stage_name=stage,case=case['id'],bias=bias);out=replay(case,inp,model,specs,ab)
            if stage=='M1_OFF':
                for j,aname in enumerate(['A0','A1']):
                    jr=list(ref['names']).index(aname)
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
                        diff=out[key][:,j].astype(float)-ref[key][:,jr].astype(float)
                        if key in ['x','prior']:diff[:,2]=V.MC.wrap(diff[:,2])
                        S.check(case['id']+bias+aname+key,diff,np.zeros_like(diff),1e-10)
            scores.extend(E.score(stage,case,bias,inp,out,specs,0));pd.DataFrame(scores).to_csv(ROOT/'M1_SCORES.csv',index=False);S.write('M1_CHECKS.json',S.checks);S.event('M1_CASE_PASS',stage_name=stage,case=case['id'],bias=bias)
        S.write(stage+'_GATE.json',dict(status='PASS',conditions=10))
    for r in locked:assert S.sha(r['path'])==r['sha256'],r['path']
    S.write('M1_EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',conditions=10,variants=6,inputs_unchanged=True,Q_unchanged=True,retraining=False,utc=S.now()))
if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('M1_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise

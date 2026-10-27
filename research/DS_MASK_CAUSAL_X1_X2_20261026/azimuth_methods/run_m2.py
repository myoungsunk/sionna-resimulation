from run_m1 import ROOT,S,E,V,np,pd,CASES
import json,sys,traceback

def gamma_for(s,delta,bound):
    if abs(s+delta)<=bound or abs(delta)<1e-18:return 1.,True
    r=sorted([(-bound-s)/delta,(bound-s)/delta]);lo=max(0.,r[0]);hi=min(1.,r[1])
    if hi>=lo:return hi,True
    return (1. if abs(s+delta)<abs(s) else 0.),False

def replay(case,inp,model,specs,ab,T):
    n=len(inp['t']);J=len(specs);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1))
    out={k:np.empty((n,J)+sh) for k,sh in {'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'K':(4,2),'mu':(2,),'R':(2,2),'nu':(2,)}.items()}
    for key in ['gamma','S_prev_m','S_after_m','sigma_t_m','bound_m','d_est']:out[key]=np.zeros((n,J))
    for key in ['acc','info_valid','feasible']:out[key]=np.zeros((n,J),bool)
    ci=np.zeros((n+1,J,2,2));cu=np.zeros((n+1,J,2));tt=np.round(inp['t'],8)
    for k in range(n):
        if k%128==0:S.stopcheck()
        if k:
            c=inp['controls']
            for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));R=np.tile(inp['R'][k],(J,1,1));z=np.tile(inp['z'][k],(J,1))
        for j,s in enumerate(specs):mu[j,0]+=s['alpha']*(inp['pred'][k]-mu[j,0])
        nu=z-h-mu;hp=H@P;cov=hp@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2));K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
        rawK=K.copy();rawdx=np.einsum('nij,nj->ni',K,nu);rad=x[:,:2]-np.array(case['anchor'])[:2];d=np.linalg.norm(rad,axis=1);rad/=d[:,None];ut=np.column_stack([-rad[:,1],rad[:,0]])
        ci[k+1]=ci[k]+np.einsum('ni,nj->nij',H[:,0,:2],H[:,0,:2])/R[:,0,0,None,None]*ab[k]
        left=np.searchsorted(tt,round(float(tt[k]-T),8),side='right');I=ci[k+1]-ci[left];sp=np.einsum('ni,ni->n',ut,cu[k]-cu[left]);dt=np.einsum('ni,ni->n',ut,rawdx[:,:2]);gamma=np.ones(J);sigma=np.full(J,np.inf);bound=np.full(J,np.inf);valid=np.zeros(J,bool);feasible=np.ones(J,bool)
        for j,s in enumerate(specs):
            eig=np.linalg.eigvalsh(I[j]);valid[j]=tt[k]-tt[0]>=T and eig[0]>max(1e-12,eig[-1]*1e-10)
            if valid[j]:
                sigma[j]=np.sqrt(ut[j]@np.linalg.solve(I[j],ut[j]));bound[j]=s['kappa']*sigma[j] if s['kappa'] else np.inf
                if s['kappa'] and ab[k]:gamma[j],feasible[j]=gamma_for(sp[j],dt[j],bound[j])
        K[:,:2,:]-=(1-gamma)[:,None,None]*ut[:,:,None]*np.einsum('ni,nij->nj',ut,rawK[:,:2,:])[:,None,:]
        assert np.max(abs(np.einsum('ni,nij->nj',ut,K[:,:2,:])-gamma[:,None]*np.einsum('ni,nij->nj',ut,rawK[:,:2,:])))<1e-12
        dx=np.einsum('nij,nj->ni',K,nu);after=sp+np.einsum('ni,ni->n',ut,dx[:,:2])*ab[k]
        for key,val in [('prior',x),('Pprior',P),('h',h),('H',H),('mu',mu),('R',R),('nu',nu),('gamma',gamma),('S_prev_m',sp),('S_after_m',after),('sigma_t_m',sigma),('bound_m',bound),('info_valid',valid),('feasible',feasible),('d_est',d)]:out[key][k]=val
        y=x+dx;y[:,2]=V.MC.wrap(y[:,2]);A=np.eye(4)[None]-K@H;pp=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);pp=.5*(pp+pp.swapaxes(-1,-2))
        if ab[k]:x=y;P=pp
        cu[k+1]=cu[k]+dx[:,:2]*ab[k];out['x'][k]=x;out['P'][k]=P;out['K'][k]=K;out['acc'][k]=ab[k]
    for key in ['x','P','prior','Pprior','H','K','mu','R','nu']:assert np.isfinite(out[key]).all()
    for key in ['P','Pprior']:assert abs(out[key]-out[key].swapaxes(-1,-2)).max()<1e-12 and np.linalg.eigvalsh(out[key]).min()>=-1e-12
    assert out['gamma'].min()>=0 and out['gamma'].max()<=1
    reject=~out['acc']
    if reject.any():S.check('reject_x',out['x'][reject],out['prior'][reject],0);S.check('reject_P',out['P'][reject],out['Pprior'][reject],0)
    for j in range(J):S.check('fixed_AB',out['acc'][:,j],ab,0)
    return out

def main():
    pre=json.loads((ROOT/'PRE_RESULT.json').read_text());assert pre['M2_pre']=='GO';T=pre['M2_selected_T'];assert T==10
    # Analytic limiter sanity checks before the filter is executed.
    for s,d,b,expected in [(0,2,1,.5),(2,1,1,0),(2,-.5,1,1),(2,-2,1,1),(-2,-1,1,0),(0,0,1,1)]:assert abs(gamma_for(s,d,b)[0]-expected)<1e-12
    locked=json.loads((ROOT/'M1_INPUT_LOCK.json').read_text())['files']+[dict(path=str(p),sha256=S.sha(p)) for p in [ROOT/'run_m2.py',ROOT/'M2_REPLAY_DEFINITIONS.md',ROOT/'PRE_RESULT.json']]
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('M2_INPUT_LOCK.json',dict(files=locked,utc=S.now(),command=sys.argv));model=V.SourceFFD()
    feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz');cache=[]
    for case in V.MANIFEST['cases']:
        if case['id'] not in CASES:continue
        for bias in ['B0','L2']:
            inp=S.load_case(case,bias,feat,par,mr,hg)
            with np.load(ROOT.parent/'e1_e4/E1'/f'{case["id"]}_{bias}.npz') as f:ref={k:f[k] for k in f.files}
            S.check('pose_id',inp['ids'],ref['pose_id'],0);ab=ref['acc'][:,list(ref['names']).index('A0')];cache.append((case,bias,inp,ref,ab))
    scores=[]
    for stage in ['M2_OFF','M2_SWEEP']:
        specs=[dict(name=f'M2-{kap}_{arm}',alpha=alpha,kappa=kap) for kap in ([0] if stage=='M2_OFF' else [1,2,3]) for arm,alpha in [('BB',0),('MB',1)]]
        for case,bias,inp,ref,ab in cache:
            S.event('M2_START',stage_name=stage,case=case['id'],bias=bias);out=replay(case,inp,model,specs,ab,T)
            if stage=='M2_OFF':
                for j,name in enumerate(['A0','A1']):
                    jr=list(ref['names']).index(name)
                    for key in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
                        diff=out[key][:,j].astype(float)-ref[key][:,jr].astype(float)
                        if key in ['x','prior']:diff[:,2]=V.MC.wrap(diff[:,2])
                        S.check(case['id']+bias+name+key,diff,np.zeros_like(diff),1e-10)
            scores.extend(E.score(stage,case,bias,inp,out,specs,0));pd.DataFrame(scores).to_csv(ROOT/'M2_SCORES.csv',index=False);S.write('M2_CHECKS.json',S.checks);S.event('M2_CASE_PASS',stage_name=stage,case=case['id'],bias=bias)
        S.write(stage+'_GATE.json',dict(status='PASS',conditions=10))
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('M2_EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',conditions=10,T=T,k=[1,2,3],inputs_unchanged=True,utc=S.now()))
if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('M2_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise

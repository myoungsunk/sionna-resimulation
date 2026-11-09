"""Separate mathematical/source/array audit path. Same author, not external audit.
Uses original scalar LUT/transition/update as reference, not new model helpers.
"""
from __future__ import annotations
import ast,hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

DEG=180/np.pi

def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def errmax(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))

def check(condition,label):
    if not condition:raise AssertionError(label)

def source_audit(root):
    root=Path(root);source={}
    # Reused numerical sources plus newly written algorithms.
    for p in sorted(root.rglob('*.py')):
        if '__pycache__' not in str(p):
            source[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return source

def leak_audit(model_file):
    tree=ast.parse(Path(model_file).read_text());bad=[]
    names={'run_baseline','run_mixture','replay','rts','predict','mix_moments','log_likelihood','scalar_candidate'}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
            for x in ast.walk(node):
                if isinstance(x,ast.Attribute) and x.attr in ('truth','saved','trace','original'):
                    bad.append((node.name,x.lineno,x.attr))
                if isinstance(x,ast.Name) and x.id in ('truth','gt','true_bias','z_los'):
                    bad.append((node.name,x.lineno,x.id))
    check(not bad,'GROUND_TRUTH_REFERENCE_IN_INFERENCE:'+repr(bad))
    return {'checked_functions':sorted(names),'forbidden_references':bad}

def original_candidate(e,x,P,z):
    def model(v):
        h,H=e.scalar_lut.model(v,e.case)
        return h[1:],H[1:]
    a,b,d=e.core.gaussian_update(x,P,np.array([z]),model,np.array([[.0081]]))
    return a,b,d

def original_predict(e,x,P,u,k):
    ds=float(u['ds_odom'][k]);da=float(u['dtheta_gyro'][k]);dt=float(u['dt_s'][k])
    q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    return e.core.predict(x,P,ds,da,dt,q)[:2]

def state_qa(data):
    X=data['X'];P=data['P']
    check(np.isfinite(X).all() and np.isfinite(P).all(),'NONFINITE_STATE')
    eig=float(np.linalg.eigvalsh(P).min())
    check(eig>0,'POSTERIOR_NOT_PD')
    asym=float(np.max(np.abs(P-P.swapaxes(-1,-2))))
    check(asym<1e-10,'COV_ASYMMETRY')
    return dict(n=len(X),min_eigenvalue=eig,max_asymmetry=asym)

def baseline_parity(data,original,index,check_nis):
    d=dict(state=errmax(data['X'],original['estimate'][:,index]),
           covariance=errmax(data['P'],original['covariance'][:,index]))
    if check_nis:
        d['nis']=errmax(data['nis'],original['nis'][:,index])
        d['mask_mismatch']=int(np.count_nonzero(data['accepted']!=(original['status'][:,index]=='APPLIED')))
    check(d['state']<1e-7 and d['covariance']<1e-8,'ORIGINAL_XP_PARITY_FAIL:'+repr(d))
    check(not check_nis or (d['nis']<1e-7 and d['mask_mismatch']==0),'ORIGINAL_NIS_PARITY_FAIL:'+repr(d))
    return d

def audit_jacobians(e,u,baseline):
    hf=[];ff=[];skip=0;scalar_error=[]
    for k in np.linspace(1,len(baseline['X'])-1,32).astype(int):
        x=baseline['prior_X'][k];h,H,clip=e.observe(x)
        scalar_h,scalar_H=e.scalar_lut.model(x,e.case)
        scalar_error.append(max(abs(h-scalar_h[1]),np.max(abs(H-scalar_H[1]))))
        est=[]
        for j in range(4):
            dx=np.zeros(4);dx[j]=1e-6
            hp=e.scalar_lut.model(x+dx,e.case)[0][1]
            hm=e.scalar_lut.model(x-dx,e.case)[0][1]
            est.append((hp-hm)/2e-6)
        he=float(np.max(np.abs(est-H)))
        # Kinks are reported explicitly; never hidden as passing derivatives.
        if he>2e-4:skip+=1
        else:hf.append(he)
        ds,da,dt=map(float,(u['ds_odom'][k],u['dtheta_gyro'][k],u['dt_s'][k]))
        _,F,_=e.core.transition(x,ds,da,dt)
        fd=np.zeros((4,4))
        for j in range(4):
            dx=np.zeros(4);dx[j]=1e-6
            yp=e.core.transition(x+dx,ds,da,dt)[0];ym=e.core.transition(x-dx,ds,da,dt)[0]
            dif=yp-ym;dif[2]=wrap(dif[2]);fd[:,j]=dif/2e-6
        ff.append(float(abs(fd-F).max()))
    check(max(ff)<2e-7,'TRANSITION_FINITE_DIFFERENCE_FAIL')
    check(max(scalar_error)<1e-10,'LUT_BATCH_SCALAR_MISMATCH')
    check(len(hf)>=24,'TOO_MANY_LUT_KINKS_OR_GRADIENT_FAILURES')
    return dict(n=32,H_max=max(hf),F_max=max(ff),H_kink_or_failure_count=skip,scalar_lut_max=max(scalar_error))

def projection_audit(a):
    G,V,P0=a['G'],a['V'],a['P0'];iv=np.linalg.solve(V,np.eye(len(V)));ones=np.ones(len(V))
    J=G.T@iv@G;v=G.T@iv@ones;vv=ones@iv@ones
    Jc=J-np.outer(v,v)/vv
    augmented=np.block([[np.linalg.inv(P0)+J,v[:,None]],[v[None,:],np.array([[vv]])]])
    Pc=np.linalg.inv(augmented)[:4,:4]
    rel=float(np.linalg.norm(Jc-a['Jc'])/max(1,np.linalg.norm(Jc)))
    de=errmax(Pc,a['Pc'])
    check(rel<2e-8 and de<1e-8,'PROJECTOR_AUGMENTED_SCHUR_MISMATCH')
    mine=float(np.linalg.eigvalsh(a['Pc']-a['P1']).min())
    check(mine>-1e-9,'PROJECTION_ADDS_INFORMATION')
    end_error=0.
    if 'Pend' in a:
        # Independent basis-elimination path at endpoint.
        _,_,vh=np.linalg.svd(np.ones((1,len(V))),full_matrices=True)
        N=vh[1:]
        yy=N@a['Y']@N.T;E=a['E']@N.T
        pp=a['Pend']-E@np.linalg.solve(yy,E.T)
        end_error=errmax(pp,a['PEC'])
        check(end_error<1e-8,'ENDPOINT_CORRELATED_NOISE_MARGINALIZATION_FAIL')
        check(np.linalg.eigvalsh(a['PEC']-a['PE']).min()>-1e-9,'ENDPOINT_PROJECTION_ADDS_INFO')
    return dict(matrix_relative_error=rel,augmented_cov_error=max(de,end_error),min_information_loss_eigen=mine)

def audit_mixture(e,u,z,x0,result,collapse):
    """Recompute every retained update and weight from saved parent arrays
    through the original scalar observation and prediction implementation.
    """
    prevx=x0[None,:].copy();prevP=np.diag([.1**2,.1**2,math.radians(5)**2,math.radians(.1)**2])[None,:,:]
    prevw=np.ones(1);prevmode=np.array([-1]);prevmodep=np.array([.1,.9]);K=result['component_X'].shape[1]
    maxx=maxp=maxw=maxmom=maxloss=0.;tested=0
    for k in range(len(z)):
        xx=[];pp=[]
        for j in range(len(prevw)):
            x,P=original_predict(e,prevx[j],prevP[j],u,k) if k else (prevx[j],prevP[j])
            xx.append(x);pp.append(P)
        cm=[];cp=[];logs=[]
        for j,(x,P) in enumerate(zip(xx,pp)):
            y,C,d=original_candidate(e,x,P,float(z[k]))
            nu=float(d['innovation'][0]);S=float(d['S'][0,0]);on=-.5*(math.log(2*math.pi*S)+nu*nu/S)
            pm=np.array([.1,.9]) if k==0 else (prevmodep@np.array([[.95,.05],[.05,.95]]) if collapse else np.array([[.95,.05],[.05,.95]])[prevmode[j]])
            cm.extend((x,y));cp.extend((P,C))
            logs.extend((math.log(max(prevw[j],1e-300))+math.log(pm[0])-math.log(2),
                         math.log(max(prevw[j],1e-300))+math.log(pm[1])+on))
        cm=np.asarray(cm);cp=np.asarray(cp);cw=np.exp(np.asarray(logs)-logsumexp(logs))
        maxw=max(maxw,errmax(cw,result['pool_weights'][k,:len(cw)]))
        if collapse:
            weights=cw;mx=cm;pc=cp;lost=0.;expectedmodep=cw
        else:
            picks=[]
            for mode in (0,1):
                ids=np.arange(mode,len(cw),2)
                picks.extend(ids[np.argsort(-cw[ids],kind='stable')[:K//2]].tolist())
            actual=result['pool_index'][k,:int(result['counts'][k])].astype(int)
            check(np.array_equal(actual,picks),'BRANCH_PRUNING_ORDER')
            weights=cw[picks]/cw[picks].sum();mx=cm[picks];pc=cp[picks];lost=1-cw[picks].sum()
            maxx=max(maxx,errmax(mx,result['component_X'][k,:len(picks)]))
            maxp=max(maxp,errmax(pc,result['component_P'][k,:len(picks)]))
            maxw=max(maxw,errmax(weights,result['weights'][k,:len(picks)]))
            expectedmodep=np.array([weights[np.array(picks)%2==m].sum() for m in (0,1)])
        mean=weights@mx;mean[2]=math.atan2(weights@np.sin(mx[:,2]),weights@np.cos(mx[:,2]))
        delta=mx-mean;delta[:,2]=wrap(delta[:,2])
        cov=sum(weights[j]*(pc[j]+np.outer(delta[j],delta[j])) for j in range(len(weights)))
        maxmom=max(maxmom,errmax(mean,result['X'][k]),errmax(cov,result['P'][k]))
        maxloss=max(maxloss,abs(lost-result['discarded_mass'][k]))
        maxw=max(maxw,errmax(expectedmodep,result['mode_probs'][k]))
        b=int(result['counts'][k]);prevx=result['component_X'][k,:b];prevP=result['component_P'][k,:b]
        prevw=result['weights'][k,:b];prevmode=result['modes'][k,:b].astype(int);prevmodep=result['mode_probs'][k]
        check(abs(prevw.sum()-1)<1e-12,'MIXTURE_WEIGHT_SUM')
        check(np.linalg.eigvalsh(prevP).min()>0,'COMPONENT_NOT_PD');tested+=b
    check(maxx<1e-7 and maxp<1e-8 and maxw<1e-7 and maxmom<1e-7 and maxloss<1e-7,
          f'MIXTURE_AUDIT_FAIL:{maxx,maxp,maxw,maxmom,maxloss}')
    return dict(retained_component_steps=tested,state_max=maxx,cov_max=maxp,weight_max=maxw,moments_max=maxmom,discard_max=maxloss)

def fresh_reference(e,u,z,x0,end,omit):
    """Different API and scalar code path, whole history from frame zero."""
    x=x0.copy();P=np.diag([.1**2,.1**2,math.radians(5)**2,math.radians(.1)**2]);xx=[];pp=[];aa=[]
    for k in range(end+1):
        if k:x,P=original_predict(e,x,P,u,k)
        y,C,d=original_candidate(e,x,P,float(z[k]));yes=k not in omit and d['NIS']<=6.6348966010212145
        if yes:x,P=y,C
        xx.append(x.copy());pp.append(P.copy());aa.append(yes)
    return dict(X=np.asarray(xx),P=np.asarray(pp),accepted=np.asarray(aa))

def synthetic_audit(m):
    rng=np.random.default_rng(20261109);err_proj=err_mix=err_rts=0.
    for j in range(80):
        n=5+(j%7);A=rng.normal(size=(4,4));P0=A@A.T+np.eye(4)*.2
        C=rng.normal(size=(n,n));V=C@C.T+np.eye(n)*.2;G=rng.normal(size=(n,4))
        L=np.linalg.cholesky(V);W=np.linalg.solve(L,G);u=np.linalg.solve(L,np.ones(n));u/=np.linalg.norm(u)
        B=W-u[:,None]*(u@W)[None,:];J=W.T@W;Jc=B.T@B
        au=dict(G=G,V=V,P0=P0,J=J,Jc=Jc,P1=np.linalg.inv(np.linalg.inv(P0)+J),Pc=np.linalg.inv(np.linalg.inv(P0)+Jc))
        e=projection_audit(au);err_proj=max(err_proj,e['augmented_cov_error'])
        xx=rng.normal(size=(2,4))*.1;xx[:,2]=[np.pi-.02,-np.pi+.03]
        pp=np.stack([P0*.01,P0*.03]);w=np.array([.3,.7]);mean,cov=m.mix_moments(xx,pp,w)
        check(abs(abs(mean[2])-np.pi)<.03,'CIRCULAR_MEAN_WRAP_FAIL')
        check(np.linalg.eigvalsh(cov).min()>0,'MIX_COV_FAIL')
        err_mix=max(err_mix,float(np.max(np.abs(cov-cov.T))))
    # RTS versus independent batch Gaussian conditioning; zero-ish angles avoid wrapping ambiguity.
    n=7;d=4;F=np.eye(d);F[0,2]=.1;F[2,3]=-.2;Q=np.eye(d)*.002
    P0=np.eye(d)*.01;mu=np.zeros(d);H=np.array([.1,.2,.8,0.]);R=.02
    y=rng.normal(0,.03,n);Pf=[];xf=[];xp=[];Pp=[]
    joint=np.zeros((n*d,n*d));joint[:d,:d]=P0
    for k in range(n):
        if k:
            mu=F@mu;P0=F@P0@F.T+Q
            for j in range(k):joint[k*d:(k+1)*d,j*d:(j+1)*d]=F@joint[(k-1)*d:k*d,j*d:(j+1)*d];joint[j*d:(j+1)*d,k*d:(k+1)*d]=joint[k*d:(k+1)*d,j*d:(j+1)*d].T
            joint[k*d:(k+1)*d,k*d:(k+1)*d]=F@joint[(k-1)*d:k*d,(k-1)*d:k*d]@F.T+Q
        xp.append(mu.copy());Pp.append(P0.copy());K=P0@H/(H@P0@H+R)
        mu=mu+K*(y[k]-H@mu);P0=P0-np.outer(K,H@P0)
        xf.append(mu.copy());Pf.append(P0.copy())
    window=dict(X=np.array(xf),P=np.array(Pf),prior_X=np.array(xp),prior_P=np.array(Pp),F=np.tile(F,(n,1,1)))
    sx,sp=m.rts(window);Hstack=np.kron(np.eye(n),H[None,:])
    post=np.linalg.inv(np.linalg.inv(joint)+Hstack.T@Hstack/R);postmean=post@Hstack.T@y/R
    err_rts=max(errmax(sx,postmean.reshape(n,d)),max(errmax(sp[k],post[k*d:(k+1)*d,k*d:(k+1)*d]) for k in range(n)))
    check(err_rts<1e-10,'RTS_BATCH_DISAGREEMENT')
    # Actual mutation detection: altered covariance/mode weight and false extra information.
    mutations=[]
    try:state_qa(dict(X=np.zeros((1,4)),P=-np.eye(4)[None,:,:]))
    except AssertionError:mutations.append('negative_covariance_detected')
    else:raise AssertionError('FAULT_NOT_DETECTED')
    aa=dict(au);aa['Jc']=aa['Jc']+np.eye(4)
    try:projection_audit(aa)
    except AssertionError:mutations.append('duplicated_information_detected')
    else:raise AssertionError('FAULT_NOT_DETECTED')
    return dict(status='PASS',projection_trials=80,projection_cov_max=err_proj,mix_symmetry_max=err_mix,
        rts_batch_state_cov_max=err_rts,faults_detected=mutations)

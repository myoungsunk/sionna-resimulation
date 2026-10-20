"""Six-state research engine: [x,y,yaw,gyro_bias,normalized_RF_bias_1,2].
All inference inputs are observed RF, fixed learned parameters, causal controls,
and an observed-feature event mask. Truth is not an inference argument.
Zero correlation exactly reduces the physical marginal to POWER1.
Original four-state dynamics are preserved. Extra states never replace gyro bias.
"""
from __future__ import annotations
import numpy as np
from core import transition,wrap
GATE=9.210340371976184
PINIT=np.diag([.1**2,.1**2,np.radians(5.)**2,np.radians(.1)**2])

def specifications(event,params):
    tau=params['tau_s']; frac=params['fraction']
    specs=[dict(name='JOINT4',base='r0'),dict(name='POWER1',base='power'),
      dict(name='POWER_INDEPENDENT',base='power',latent=True,tau=0.,fraction=frac),
      dict(name='POWER_MEMORY',base='power',latent=True,tau=tau,fraction=frac),
      dict(name='POWER_MEMORY_HALF_TAU',base='power',latent=True,tau=tau/2,fraction=frac),
      dict(name='POWER_MEMORY_DOUBLE_TAU',base='power',latent=True,tau=2*tau,fraction=frac),
      dict(name='POWER_MEMORY_NO_CROSS',base='power',latent=True,tau=tau,fraction=frac,no_cross=True),
      dict(name='POWER_MEMORY_S_ONLY',base='power',latent=True,tau=tau,fraction=frac,latent_mask=[0,1]),
      dict(name='JOINT4_MEMORY',base='r0',latent=True,tau=tau,fraction=frac),
      dict(name='POWER_MEAN_ONLY',base='mean'),dict(name='POWER_COV_ONLY',base='cov'),
      dict(name='POWER_NO_CRS',base='diag'),dict(name='POWER_NO_GATE',base='power',no_gate=True),
      dict(name='POWER_MEMORY_NO_GATE',base='power',latent=True,tau=tau,fraction=frac,no_gate=True),
      dict(name='POWER_SR4',base='power',order='sr'),
      dict(name='POWER_ITERATED',base='power',order='iterated'),
      dict(name='P4_HARD_RECONSTRUCTED',base='p4hard'),
      dict(name='P4_MEAN_SWITCH_ONLY',base='p4mean'),
      dict(name='P4_COV_SWITCH_ONLY',base='p4cov')]
    if event is not None:
        for base in ['power','r0']:
            prefix='POWER' if base=='power' else 'JOINT4'
            for mode in ['local_drop','local_keep']:
                specs.append(dict(name=prefix+'_'+mode.upper(),base=base,latent=True,
                                  tau=tau,fraction=frac,activation=mode,event=event))
        specs.append(dict(name='POWER_LOCAL_NO_MEMORY',base='power',latent=True,tau=0.,fraction=frac,activation='local_drop',event=event))
    return specs

def parameters_at(i,spec,mu,C,R0,risk):
    mean=mu.copy();cov=C.copy();base=spec['base']
    if base=='r0': mean[:]=0;cov=R0.copy()
    elif base=='mean': cov=R0.copy()
    elif base=='cov': mean[:]=0
    elif base=='diag': cov=np.diag(np.diag(C))
    elif base=='p4hard' and risk<.5: mean[:]=0;cov=R0.copy()
    elif base=='p4mean' and risk<.5: mean[:]=0
    elif base=='p4cov' and risk<.5: cov=R0.copy()
    active=spec.get('latent',False)
    if 'activation' in spec:
        a,b=spec['event'];active=active and i>=a and (spec['activation']=='local_keep' or i<b)
    if active:
        mask=np.asarray(spec.get('latent_mask',[1,1]),float)
        B=np.linalg.cholesky(cov)@np.diag(np.sqrt(spec['fraction']*mask))
        white=cov-B@B.T
    else: B=np.zeros((2,2));white=cov
    return mean,white,B,active

def single_update(x,P,z,h,H,R):
    nu=z-h;S=H@P@H.T+R;K=np.linalg.solve(S,H@P).T
    y=x+K@nu;y[2]=wrap(y[2]);A=np.eye(len(x))-K@H
    Q=A@P@A.T+K@R@K.T
    return y,(Q+Q.T)/2,K,nu,float(nu@np.linalg.solve(S,nu))

def iterate_update(x0,P0,z,R,case,model,limit=4):
    """Fixed-prior damped Gauss Newton. One observation, covariance applied once."""
    y=x0.copy();Pinv=np.linalg.inv(P0[:4,:4]);Ri=np.linalg.inv(R)
    def objective(x):
        h,_=model.model(x[:4],case);d=x[:4]-x0[:4];d[2]=wrap(d[2])
        nu=z-h
        return float(d@Pinv@d+nu@Ri@nu)
    cost=objective(y); accepted_iterations=0
    for _ in range(limit):
        h,H4=model.model(y[:4],case);H=np.zeros((2,6));H[:,:4]=H4
        d=y-x0;d[2]=wrap(d[2]);S=H@P0@H.T+R;K=np.linalg.solve(S,H@P0).T
        target=x0+K@(z-h+H@d);target[2]=wrap(target[2]);direction=target-y;direction[2]=wrap(direction[2])
        moved=False
        for scale in (1.,.5,.25,.125):
            candidate=y+scale*direction;candidate[2]=wrap(candidate[2]);cc=objective(candidate)
            if cc<=cost+1e-12:
                y=candidate;cost=cc;moved=True;accepted_iterations+=1;break
        if not moved or np.linalg.norm(direction)<1e-8:break
    _,H4=model.model(y[:4],case);H=np.zeros((2,6));H[:,:4]=H4
    K=np.linalg.solve(H@P0@H.T+R,H@P0).T;A=np.eye(6)-K@H
    Q=A@P0@A.T+K@R@K.T
    return y,(Q+Q.T)/2,accepted_iterations

def sequential_update(x,P,z,R,case,model):
    h,H4=model.model(x[:4],case);H=np.zeros((2,6));H[:,:4]=H4
    a=R[1,0]/R[0,0];v=R[1,1]-R[1,0]**2/R[0,0]
    y,Q,*_=single_update(x,P,z[:1],h[:1],H[:1],R[:1,:1])
    h2,H24=model.model(y[:4],case);HH=np.zeros((1,6));HH[:,:4]=H24[1:2]-a*H24[:1]
    y,Q,*_=single_update(y,Q,np.array([z[1]-a*z[0]]),np.array([h2[1]-a*h2[0]]),HH,np.array([[v]]))
    return y,Q

def run(t,controls,initial_pose,z,mu,C,risk,case,model,specs,radio_mask=None,initial_cov=None,parameter_provider=None):
    n=len(t);m=len(specs);nx=6;I=np.eye(nx)
    x=np.zeros((m,nx));x[:,:3]=initial_pose
    P=np.repeat(np.eye(nx)[None],m,axis=0);P[:,:4,:4]=PINIT if initial_cov is None else initial_cov
    radio_mask=np.ones(n,bool) if radio_mask is None else np.asarray(radio_mask,bool)
    xs=np.zeros((n,m,nx));ps=np.zeros((n,m,nx,nx));xp=np.zeros_like(xs);pp=np.zeros_like(ps)
    nus=np.zeros((n,m,2));SS=np.zeros((n,m,2,2));Ks=np.zeros((n,m,nx,2));Hs=np.zeros((n,m,2,nx));hs=np.zeros((n,m,2))
    gates=np.zeros((n,m),bool);nis=np.zeros((n,m));proposed=np.zeros((n,m));linear_error=np.zeros((n,m));iterations=np.zeros((n,m),int)
    used_mu=np.zeros((n,m,2));used_R=np.zeros((n,m,2,2));loadings=np.zeros((n,m,2,2))
    R0=np.diag([.0068578637,.0081]);min_eig=np.inf
    for i in range(n):
        dt=float(controls['dt_s'][i]) if i else .2
        active=[];ms=[];Rs=[];Bs=[]
        for j,spec in enumerate(specs):
            mean,R,B,is_active=parameters_at(i,spec,mu[i],C[i],R0,float(risk[i]));active.append(is_active);ms.append(mean);Rs.append(R);Bs.append(B)
            if i:
                new,F4,G=transition(x[j,:4],float(controls['ds_odom'][i]),float(controls['dtheta_gyro'][i]),dt)
                F=I.copy();F[:4,:4]=F4
                rho=np.exp(-dt/spec['tau']) if is_active and spec.get('tau',0)>0 else 0.
                F[4:,4:]*=rho
                Q=np.zeros((6,6));Qi=np.diag([2e-5*abs(float(controls['ds_odom'][i])),np.radians(.015)**2*dt,0.])
                Q[:4,:4]=G@Qi@G.T;Q[4:,4:]=np.eye(2)*(1-rho*rho)
                x[j,:4]=new;x[j,4:]*=rho;P[j]=F@P[j]@F.T+Q
            if 'activation' in spec:
                a,b=spec['event']
                if i==a or (spec['activation']=='local_drop' and i==b):
                    x[j,4:]=0.;P[j,4:,4:]=np.eye(2);P[j,:4,4:]=0.;P[j,4:,:4]=0.
            if spec.get('no_cross',False):P[j,:4,4:]=0.;P[j,4:,:4]=0.
            # Explicit offline interventions; ordinary POWER1 never sees truth.
            if 'diagnostic_event' in spec:
                a,b=spec['diagnostic_event']
                if i==a and 'oracle_heading' in spec:x[j,2]=spec['oracle_heading']
                if a<=i<b and spec.get('zero_psi_bg'):P[j,2,3]=P[j,3,2]=0.
                if a<=i<b and spec.get('r_scale'):Rs[-1]=Rs[-1]*spec['r_scale']
            if parameter_provider is not None:
                if spec.get('latent'):raise ValueError('dynamic provider is physical POWER only')
                ms[-1],Rs[-1]=parameter_provider(i,x[j,:4].copy(),spec)
        ms=np.asarray(ms);Rs=np.asarray(Rs);Bs=np.asarray(Bs)
        xp[i]=x;pp[i]=P
        hp,H4=model.batch(x[:,:4],case,gradient=True)
        H=np.zeros((m,2,6));H[:,:,:4]=H4;H[:,:,4:]=Bs
        pred=hp+np.einsum('mab,mb->ma',Bs,x[:,4:])
        nu=z[i][None]-ms-pred;S=H@P@H.transpose(0,2,1)+Rs
        K=np.linalg.solve(S,H@P).transpose(0,2,1)
        d=np.einsum('mab,mb->ma',K,nu);value=np.einsum('mi,mi->m',nu,np.linalg.solve(S,nu[...,None])[...,0])
        # Channel diagnostics use marginal likelihoods and the fixed 1-dof 99% gate.
        for j,spec in enumerate(specs):
            a,b=spec.get('diagnostic_event',(-1,-1))
            if a<=i<b and 'channel' in spec:
                ch=spec['channel'];K[j]=0.
                K[j,:,ch]=P[j]@H[j,ch]/S[j,ch,ch]
                value[j]=nu[j,ch]**2/S[j,ch,ch]
            if a<=i<b and spec.get('block_bias'):K[j,3]=0.
        d=np.einsum('mab,mb->ma',K,nu)
        accept=value<=GATE
        for j,spec in enumerate(specs):
            if spec.get('no_gate'):accept[j]=True
            a,b=spec.get('diagnostic_event',(-1,-1))
            if a<=i<b and 'channel' in spec:accept[j]=value[j]<=6.6348966010212145
            if spec.get('skip_all') or not radio_mask[i]:accept[j]=False
            if a<=i<b and spec.get('skip_event'):accept[j]=False
        proposed[i]=d[:,2];nis[i]=value;gates[i]=accept;nus[i]=nu;SS[i]=S;Ks[i]=K;Hs[i]=H;hs[i]=hp;used_mu[i]=ms;used_R[i]=Rs;loadings[i]=Bs
        nxall=x+d;nxall[:,2]=wrap(nxall[:,2]);A=I[None]-K@H;pc=A@P@A.transpose(0,2,1)+K@Rs@K.transpose(0,2,1)
        for j,spec in enumerate(specs):
            if not accept[j]:continue
            if spec.get('order')=='sr':
                nxall[j],pc[j]=sequential_update(x[j],P[j],z[i]-ms[j],Rs[j],case,model)
            elif spec.get('order')=='iterated':
                nxall[j],pc[j],iterations[i,j]=iterate_update(x[j],P[j],z[i]-ms[j],Rs[j],case,model)
        x[accept]=nxall[accept];P[accept]=pc[accept];P=(P+P.transpose(0,2,1))/2
        if not (np.isfinite(x).all() and np.isfinite(P).all()): raise FloatingPointError(f'NONFINITE at frame {i}')
        if i%50==0 or i==n-1:
            e=float(np.linalg.eigvalsh(P).min());min_eig=min(min_eig,e)
            if e<=0:raise FloatingPointError(f'NONSPD at frame {i}: {e}')
        xs[i]=x;ps[i]=P
        if i%250==0: print('RECURSIVE_PROGRESS',case['id'],i,n,flush=True)
    # Only x physical marginal is used for main accuracy/reliability evaluation.
    return dict(t=t,state=xs,cov=ps,prior=xp,prior_cov=pp,innovation=nus,S=SS,K=Ks,H=Hs,h=hs,accepted=gates,nis=nis,proposal_dpsi=proposed,iterations=iterations,mean=used_mu,Rwhite=used_R,B=loadings,names=np.array([s['name'] for s in specs]),minimum_cov_eigenvalue=np.array(min_eig))

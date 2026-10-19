"""Inference only. Inputs contain observations, controls, fitted parameters, and initial estimate.
Truth is absent from this module. Common masks and placebo windows are labeled diagnostic.
"""
import numpy as np
from colored_math import wrap,augment,predict_aug,update
from policies import parameters,event_intervals,ARMS


def iterated(x,P,z,mu,R,model,case):
    base=x[:4].copy();P0=P[:4,:4];inv=np.linalg.inv(P0);xi=base.copy()
    def cost(q):
        h,_=model.batch(q[None,:],case,gradient=False)
        d=q-base;d[2]=wrap(d[2]);v=z-mu-h[0]
        return float(d@inv@d+v@np.linalg.solve(R,v))
    before=cost(base);now=before;steps=0
    for _ in range(4):
        h,H=model.model(xi,case);d=xi-base;d[2]=wrap(d[2])
        S=H@P0@H.T+R;K=np.linalg.solve(S,H@P0).T
        target=base+K@(z-mu-h+H@d);target[2]=wrap(target[2])
        delta=target-xi;delta[2]=wrap(delta[2]);found=False
        for power in range(6):
            trial=xi+delta/(2**power);trial[2]=wrap(trial[2]);new=cost(trial)
            if new<=now+1e-12:xi=trial;now=new;steps+=1;found=True;break
        if not found or np.linalg.norm(delta)<1e-8:break
    _,H=model.model(xi,case);S=H@P0@H.T+R;K=np.linalg.solve(S,H@P0).T
    A=np.eye(4)-K@H;C=A@P0@A.T+K@R@K.T
    y=x.copy();Q=P.copy();y[:4]=xi;Q[:4,:4]=(C+C.T)*.5
    return y,Q,steps,before,now


def replay(t,controls,z,initial,stream,case,config,model,transition,arms=None):
    arms=ARMS if arms is None else list(arms);na=len(arms);n=len(t)
    event=event_intervals({'t':t,**stream},config)
    P0=np.diag([.01,.01,np.radians(5.)**2,np.radians(.1)**2])
    X=[];Ps=[]
    for _ in arms:
        x,P=augment(np.r_[initial,0.],P0);X.append(x);Ps.append(P)
    X=np.array(X);Ps=np.array(Ps);rejects=np.zeros(na,int)
    store={'state':np.zeros((n,na,6)),'cov':np.zeros((n,na,6,6)),
           'prior_state':np.zeros((n,na,6)),'prior_cov':np.zeros((n,na,6,6)),
           'K':np.zeros((n,na,6,2)),'H':np.zeros((n,na,2,6)),
           'S':np.zeros((n,na,2,2)),'innovation':np.zeros((n,na,2)),
           'h_pred':np.zeros((n,na,2)),'mu':np.zeros((n,na,2)),
           'nis':np.zeros((n,na)),'accepted':np.zeros((n,na),bool),
           'proposal':np.zeros((n,na,6)),'B':np.zeros((n,na,2,2)),
           'P_update_eigmin':np.zeros((n,na)),'recovery':np.zeros((n,na),bool)}
    iterations=[];qa=[];mask_reference=arms.index('POWER1');failures=[]
    for k in range(n):
        dt=float(controls['dt_s'][k]) if k else .2
        if dt<=0:dt=.2
        pars=[]
        for j,arm in enumerate(arms):
            par=parameters(arm,k,stream,config,event,dt);pars.append(par)
            if k:X[j],Ps[j]=predict_aug(X[j],Ps[j],controls['ds_odom'][k],controls['dtheta_gyro'][k],dt,par[4],transition)
            if arm=='MEM_NO_CROSS':Ps[j,:4,4:]=0.;Ps[j,4:,:4]=0.
        store['prior_state'][k]=X;store['prior_cov'][k]=Ps
        hh,jj=model.batch(X[:,:4],case)
        proposals=[]
        for j,arm in enumerate(arms):
            mu,C,B,E,a,active=pars[j];H=np.column_stack([jj[j],B]);h=hh[j]+B@X[j,4:]
            out=update(X[j],Ps[j],z[k],h+mu,H,E)
            proposals.append((out,H,h,mu,C,B,E))
        common=proposals[mask_reference][0][2]['accepted']
        for j,arm in enumerate(arms):
            (y,Q,d),H,h,mu,C,B,E=proposals[j]
            force=None
            if arm in ['POWER_COMMON_GATE','MEM_COMMON_GATE']:force=common
            elif arm=='POWER_NO_GATE':force=True
            if force is not None:y,Q,d=update(X[j],Ps[j],z[k],h+mu,H,E,force=force)
            if arm=='POWER_RECOVERY' and not d['accepted'] and rejects[j]>=4:
                scale=max(1.,d['nis']/9.210340371976184)
                y,Q,d=update(X[j],Ps[j],z[k],h+mu,H,E*scale,force=True)
                store['recovery'][k,j]=True
            if arm=='POWER_FREEZE_BG' and d['accepted']:
                K=d['K'].copy();K[3]=0;delta=K@d['innovation'];y=X[j]+delta;y[2]=wrap(y[2]);A=np.eye(6)-K@H
                Q=A@Ps[j]@A.T+K@E@K.T;Q=(Q+Q.T)*.5;d['K']=K;d['proposal']=delta
            if arm=='POWER_IEKF' and d['accepted']:
                y,Q,ni,c0,c1=iterated(X[j],Ps[j],z[k],mu,C,model,case)
                iterations.append({'frame':k,'steps':ni,'cost_before':c0,'cost_after':c1})
            if arm=='POWER_SR4' and d['accepted']:
                from n4c_joint_sr4 import correlated_sr4
                a,b=correlated_sr4(np,X[j,:4],Ps[j,:4,:4],z[k],mu,C,model,case)
                y=X[j].copy();Q=Ps[j].copy();y[:4]=a;Q[:4,:4]=b
            store['K'][k,j]=d['K'];store['H'][k,j]=H;store['S'][k,j]=d['S'];store['innovation'][k,j]=d['innovation'];store['h_pred'][k,j]=h;store['mu'][k,j]=mu;store['B'][k,j]=B
            store['nis'][k,j]=d['nis'];store['accepted'][k,j]=d['accepted'];store['proposal'][k,j]=d['proposal']
            eig=float(np.linalg.eigvalsh((Q+Q.T)*.5)[0]);store['P_update_eigmin'][k,j]=eig
            if not (np.isfinite(y).all() and np.isfinite(Q).all()) or eig<=0:raise ArithmeticError(str((arm,k,'invalid state/covariance',eig)))
            X[j]=y;Ps[j]=Q;rejects[j]=0 if d['accepted'] else rejects[j]+1
            if arm in ['JOINT4','POWER1'] and k%100==0:
                from core import gaussian_update
                refx,refP,rd=gaussian_update(store['prior_state'][k,j,:4],store['prior_cov'][k,j,:4,:4],z[k]-mu,lambda x:model.model(x,case),C,gate_threshold=9.210340371976184)
                dd=refx-y[:4];dd[2]=wrap(dd[2]);qa.append({'frame':k,'arm':arm,'state_diff':float(abs(dd).max()),'cov_diff':float(abs(refP-Q[:4,:4]).max()),'gate_diff':bool(rd['accepted']!=d['accepted'])})
        store['state'][k]=X;store['cov'][k]=Ps
        if k%200==0:print('RECURSION',case['id'],k,n,flush=True)
    return store,event,qa,iterations

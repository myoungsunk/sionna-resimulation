"""SE(2) EKF with shared-input prediction/odometry correlation. No truth inputs."""
from __future__ import annotations
import numpy as np
from .filters import DriveFilter, wrap, CHI2_1_999
from .hs_lut import s_model


def transition(x, distance, gyro, dt, b):
    D=1+x[4]
    if D <= 0: raise ValueError('invalid gyro scale state')
    a=(gyro-x[3]*dt)/D
    u=distance-x[5]*b*a/4
    half=a/2
    if abs(half)<1e-5:
        s=1-half**2/6+half**4/120
        sp=-half/3+half**3/30
    else:
        s=np.sin(half)/half
        sp=(half*np.cos(half)-np.sin(half))/half**2
    direction=np.array([np.cos(x[2]+half),np.sin(x[2]+half)])
    perpendicular=np.array([-direction[1],direction[0]])
    pu=s*direction; pa=u*(sp*direction+s*perpendicular)/2
    F=np.eye(6); G=np.zeros((6,3))
    F[:2,2]=u*s*perpendicular
    for j, da in ((3,-dt/D),(4,-a/D),(5,0.)):
        du=-x[5]*b*da/4-(b*a/4 if j==5 else 0.)
        F[:2,j]=pu*du+pa*da; F[2,j]=da
    G[:2,0]=pu
    G[:2,1]=(pa-pu*x[5]*b/4)/D; G[2,1]=1/D
    out=x.copy(); out[:2]+=u*s*direction; out[2]=wrap(out[2]+a)
    return out,F,G


def odometry_model(x, distance, gyro, dt, b_nom, known_eb=0.):
    D=1+x[4]; b=b_nom/(1+known_eb); eps=x[5]
    a=(gyro-x[3]*dt)/D; L=1-eps**2/4; scale=1/(1+known_eb)
    h=scale*(L*a+eps*distance/b)
    H=np.zeros(6); H[3]=-scale*L*dt/D; H[4]=-scale*L*a/D
    H[5]=scale*(distance/b-eps*a/2)
    hd=scale*eps/b; hg=scale*L/D
    return h,H,np.array([-hd,-hg,1.])


def correlated_update(x,P,H,y,R,C):
    """e=true-est, Cov(e_minus,v)=C. Returns Joseph covariance and S."""
    S=float(H@P@H+R+2*H@C)
    if S <= 1e-20: return x,P,S
    U=P@H+C; K=U/S; M=np.eye(len(x))-np.outer(K,H)
    newP=M@P@M.T+R*np.outer(K,K)-np.outer(M@C,K)-np.outer(K,M@C)
    newx=x+K*y; newx[2]=wrap(newx[2])
    return newx,(newP+newP.T)/2,S


def covariance_diagnostic(P, reference_scale=0.):
    """Float64 PSD check without projection, using pre-update numerical scale.

    A cancelled posterior can be nearly zero; its prediction/initial scale must
    remain the roundoff reference. This is a guard, not a covariance repair.
    """
    if not np.isfinite(P).all():
        return dict(valid=False,minimum_eigenvalue=float('nan'),tolerance=0.)
    eigenvalues=np.linalg.eigvalsh(P)
    scale=max(float(reference_scale),float(np.max(np.abs(eigenvalues))))
    tolerance=512*np.finfo(np.float64).eps*scale
    return dict(valid=bool(np.max(np.abs(P-P.T))<=max(tolerance,1e-300)
                           and eigenvalues.min()>=-tolerance),
                minimum_eigenvalue=float(eigenvalues.min()),tolerance=tolerance)


class SensorV2Filter(DriveFilter):
    def __init__(self,cfg,lut,x0,P0=None):
        if cfg.model_version!='sensor-v2' or cfg.kind!='ekf' or cfg.s_mode!='direct':
            raise ValueError('sensor-v2 supports EKF direct-s only; IEKF/UKF/GSF/inverse are unverified')
        if cfg.known_wheelbase_error <= -1: raise ValueError('invalid known wheelbase')
        if cfg.pos_process_std != 0: raise ValueError('sensor-v2 position slack is disabled; no tuning to hide mismatch')
        if cfg.use_s and lut is None: raise ValueError('s update requires an explicit LUT; no implicit synthetic replacement')
        super().__init__(cfg,lut,x0,P0)

    def step(self,d,g,o,dt):
        c=self.comps[0]; cfg=self.cfg; xp=c.x.copy()
        b=cfg.wheel_base/(1+cfg.known_wheelbase_error)
        c.x,F,G=transition(xp,d,g,dt,b)
        Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*dt,
                   cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)])
        c.P=F@c.P@F.T+G@Q@G.T
        h,H,B=odometry_model(xp,d,g,dt,cfg.wheel_base,cfg.known_wheelbase_error)
        # Odometry identifies the PRE-step calibration state. Pose does not enter h,
        # and calibration is fixed until the endpoint bias-RW increment below.
        C=-G@Q@B; R=float(B@Q@B); y=o-h
        S=float(H@c.P@H+R+2*H@C)
        status='disabled'
        if cfg.use_odom_heading:
            if S<=1e-20: status='zero_variance'
            elif y*y/S>CHI2_1_999: status='rejected'; self.stats['o_rejected']+=1
            else:
                c.x,c.P,_=correlated_update(c.x,c.P,H,y,R,C)
                status='applied'; self.stats['o_updates']+=1
        c.P[3,3]+=cfg.bias_rw_std**2*dt
        return dict(innovation=y,R=R,S=S,status=status,H=H,C=C,Q=Q,F=F,G=G)

    def scalar(self,z,h,H,R,key):
        c=self.comps[0]; y=float(z-h); S=float(H@c.P@H+R)
        status='zero_variance' if S<=1e-20 else ('rejected' if y*y/S>self.cfg.gate else 'applied')
        if key=='s' and S>1e-20: self.stats['nis_s'].append(y*y/S)
        if status=='applied': self._apply(c,H,y,S,R); self.stats[key+'_updates']+=1
        if status=='rejected': self.stats[key+'_rejected']+=1
        return y,R,S,status

    def range_record(self,z):
        x=self.comps[0].x; a=self.cfg.anchor_xyz; dz=a[2]-self.cfg.robot_z
        h=np.sqrt((x[0]-a[0])**2+(x[1]-a[1])**2+dz**2)
        if h<=1e-12: return np.nan,np.nan,np.nan,'undefined_geometry'
        H=np.zeros(6); H[:2]=(x[:2]-np.array(a[:2]))/h
        R=self.cfg.range_sigma**2+self.cfg.range_quant_var+self.cfg.range_extra_sigma**2
        return self.scalar(z,h+self.cfg.range_offset,H,R,'r')

    def s_record(self,z,power):
        x=self.comps[0].x
        if np.linalg.norm(x[:2]-np.asarray(self.cfg.anchor_xyz[:2])) <= 1e-6:
            return np.nan,np.nan,np.nan,'undefined_geometry'
        h,J=s_model(self.lut,self.cfg.anchor_xyz,self.cfg.robot_z,*x[:3],self.cfg.mount_deg,with_jac=True)
        H=np.zeros(6); H[:3]=J
        return self.scalar(z,float(h),H,self._s_R(*power),'s')


def run_filter_v2(cfg,lut,inputs,obs,flags,x0,P0=None):
    required=('dt_s','ds_odom','dtheta_gyro','dtheta_odom')
    if any(k not in inputs for k in required): raise ValueError('sensor-v2 needs explicit interval times and measurements')
    n=len(inputs['ds_odom']); dt=np.asarray(inputs['dt_s'])
    for key in required:
        value = np.asarray(inputs[key], dtype=float)
        if value.shape != (n,) or not np.isfinite(value).all():
            raise ValueError(f'sensor-v2 {key} must be a finite length-{n} array')
    if n == 0:
        raise ValueError('sensor-v2 needs at least one sample')
    initial = np.asarray(x0, dtype=float)
    if initial.shape != (6,) or not np.isfinite(initial).all():
        raise ValueError('sensor-v2 initial state must be finite and length 6')
    if len(dt)!=n or dt[0]!=0 or np.any(dt[1:]<=0): raise ValueError('invalid interval times')
    f=SensorV2Filter(cfg,lut,x0,P0)
    est=np.empty((n,6)); cov=np.empty((n,6,6))
    raw={f'{m}_{key}':np.full(n,np.nan) for m in ('odom','range','s') for key in ('innovation','R','S')}
    raw.update({f'{m}_status':np.full(n,'missing',dtype='U24') for m in ('odom','range','s')})
    for key,shape in (('odom_H',(6,)),('odom_C',(6,)),('input_Q',(3,3)),('transition_F',(6,6)),('input_G',(6,3))):
        raw[key]=np.zeros((n,)+shape)
    initial_P=f.comps[0].P.copy()
    initial_scale=float(np.linalg.norm(initial_P,2))
    for k in range(n):
        if k:
            rec=f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],dt[k])
            for key in ('innovation','R','S','status','H','C'): raw['odom_'+key][k]=rec[key]
            for key,src in (('input_Q','Q'),('transition_F','F'),('input_G','G')): raw[key][k]=rec[src]
        else: raw['odom_status'][k]='initial'
        detected=bool(obs.get('detected',np.zeros(n,bool))[k])
        for name,enabled,field in (('range',cfg.use_range,'range_m'),('s',cfg.use_s,'s')):
            if not enabled: raw[name+'_status'][k]='disabled'; continue
            if not detected or field not in obs or not np.isfinite(obs[field][k]): continue
            if name=='s' and cfg.skip_s_in_turn and flags.get('turn_phase',np.zeros(n,bool))[k]:
                raw['s_status'][k]='skipped_turn'; continue
            r=f.range_record(obs[field][k]) if name=='range' else f.s_record(obs[field][k],obs['power'][k])
            for key,value in zip(('innovation','R','S','status'),r): raw[name+'_'+key][k]=value
        est[k],cov[k]=f.mean_cov()
        reference_scale=initial_scale
        if k:
            predicted=rec['F']@cov[k-1]@rec['F'].T+rec['G']@rec['Q']@rec['G'].T
            reference_scale=max(reference_scale,float(np.linalg.norm(predicted,2)))
        diagnostic=covariance_diagnostic(cov[k],reference_scale)
        if not diagnostic['valid']:
            raise FloatingPointError(f'covariance invalid at sample {k}: {diagnostic}')
    return dict(est=est,cov_full=cov,cov3=cov[:,:3,:3],stats=f.stats,
                initial_state=np.asarray(x0).copy(),initial_prior=initial_P,observation_trace=raw)

from __future__ import annotations
import numpy as np
from qclean_uwb.drivesim.filter_v2 import SensorV2Filter, transition, odometry_model, CHI2_1_999
from qclean_uwb.drivesim import sensor_v2 as V

class JointCubatureFilter(SensorV2Filter):
    """Diagnostic only: integrate shared input noise jointly with state/odometry.
    Fixed Q/R, positive-weight spherical-radial cubature, no variance tuning.
    """
    def step(self,d,g,o,dt):
        c=self.comps[0]; cfg=self.cfg; n=9
        xp=c.x.copy();P=c.P.copy();b=cfg.wheel_base/(1+cfg.known_wheelbase_error)
        Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*dt,
            cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)])
        Pa=np.zeros((n,n));Pa[:6,:6]=(P+P.T)*.5;Pa[6:,6:]=Q
        ev,U=np.linalg.eigh(Pa)
        tol=512*np.finfo(float).eps*max(1e-30,max(abs(ev)))
        if min(ev)<-tol:raise ValueError(('NON_PSD_PRIOR',min(ev),tol))
        L=U*np.sqrt(np.maximum(ev,0))[None,:]
        mean=np.r_[xp,0.,0.,0.];points=np.r_[mean+np.sqrt(n)*L.T,mean-np.sqrt(n)*L.T]
        vals=np.empty((2*n,7))
        for i,a in enumerate(points):
            xx,nd,ng,no=a[:6],a[6],a[7],a[8]
            vals[i,:6]=transition(xx,d-nd,g-ng,dt,b)[0]
            vals[i,2]=xp[2]+V.wrap(vals[i,2]-xp[2])
            vals[i,6]=odometry_model(xx,d-nd,g-ng,dt,cfg.wheel_base,cfg.known_wheelbase_error)[0]+no
        mu=vals.mean(axis=0);diff=vals-mu;Cov=diff.T@diff/(2*n)
        y=o-mu[6];S=float(Cov[6,6]);status='disabled'
        c.x=mu[:6].copy();c.P=Cov[:6,:6].copy()
        if cfg.use_odom_heading:
            if S<=1e-20:status='zero_variance'
            elif y*y/S>CHI2_1_999:status='rejected';self.stats['o_rejected']+=1
            else:
                cross=Cov[:6,6];c.x+=cross/S*y;c.P-=np.outer(cross,cross)/S
                status='applied';self.stats['o_updates']+=1
        c.x[2]=V.wrap(c.x[2]);c.P=(c.P+c.P.T)*.5;c.P[3,3]+=cfg.bias_rw_std**2*dt
        xdummy,F,G=transition(xp,d,g,dt,b);h,H,B=odometry_model(xp,d,g,dt,cfg.wheel_base,cfg.known_wheelbase_error)
        return dict(innovation=y,R=float(B@Q@B),S=S,status=status,H=H,C=-G@Q@B,Q=Q,F=F,G=G)
    def range_record(self,z):
        c=self.comps[0];cfg=self.cfg;x,P=c.x.copy(),c.P.copy();xy=P[:2,:2]
        nodes,weights=np.polynomial.hermite.hermgauss(9)
        ev,U=np.linalg.eigh((xy+xy.T)*.5)
        tol=512*np.finfo(float).eps*max(1e-30,max(abs(ev)))
        if ev.min()<-tol:raise ValueError('NON_PSD_RANGE_PRIOR')
        L=U*np.sqrt(np.maximum(ev,0))[None,:]
        xx,yy=np.meshgrid(nodes,nodes,indexing='ij');ww=(weights[:,None]*weights[None,:]/np.pi).ravel()
        dx=np.sqrt(2)*np.c_[xx.ravel(),yy.ravel()]@L.T
        pt=x[:2]+dx;anc=cfg.anchor_xyz;dz=anc[2]-cfg.robot_z
        vals=np.sqrt((pt[:,0]-anc[0])**2+(pt[:,1]-anc[1])**2+dz**2)+cfg.range_offset
        hm=float(ww@vals);h=vals-hm;crossxy=(dx*ww[:,None]).T@h
        cross=P[:,:2]@np.linalg.solve(xy,crossxy)
        R=cfg.range_sigma**2+cfg.range_extra_sigma**2+cfg.range_quant_var
        S=float(ww@(h*h)+R);res=float(z-hm)
        status='zero_variance' if S<=1e-20 else ('rejected' if res*res/S>cfg.gate else 'applied')
        if status=='applied':
            c.x=x+cross/S*res;c.x[2]=V.wrap(c.x[2]);c.P=P-np.outer(cross,cross)/S;c.P=(c.P+c.P.T)/2;self.stats['r_updates']+=1
        elif status=='rejected': self.stats['r_rejected']+=1
        return res,R,S,status

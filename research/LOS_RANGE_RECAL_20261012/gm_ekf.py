"""7-state EKF = sensor-v2 6-state EKF + first-order Gauss-Markov range-bias state b (z_range = dist + offset + b + white). Re-uses the frozen transition/odometry/correlated_update.
With sigma_b2 -> 0 it must equal the 6-state SensorV2Filter (unit test: r23_gm_unit_test.py)."""
import math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
from qclean_uwb.drivesim import filter_v2 as F
from qclean_uwb.drivesim.filters import CHI2_1_999,CHI2_1_99,wrap
class GMEKF:
    def __init__(self,cfg,x0,sigma_b2,phi,r_white,range_offset):
        self.cfg=cfg;self.n=7;self.x=np.r_[np.asarray(x0,float),0.];self.P=np.zeros((7,7));self.P[:6,:6]=np.diag(np.array(cfg.p0_std,float)**2);self.P[6,6]=sigma_b2
        self.sb2=float(sigma_b2);self.phi=float(phi);self.rw=float(r_white);self.off=float(range_offset);self.stats=dict(r_updates=0,r_rejected=0,o_updates=0,o_rejected=0)
    def step(self,d,g,o,dt):
        cfg=self.cfg;xp=self.x[:6].copy();b=cfg.wheel_base/(1+cfg.known_wheelbase_error)
        x6,F6,G6=F.transition(xp,d,g,dt,b)
        Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*dt,cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)])
        F7=np.eye(7);F7[:6,:6]=F6;F7[6,6]=self.phi;G7=np.zeros((7,3));G7[:6]=G6
        self.x[:6]=x6;self.P=F7@self.P@F7.T+G7@Q@G7.T;self.P[6,6]+=self.sb2*(1-self.phi**2)
        h,H,B=F.odometry_model(xp,d,g,dt,cfg.wheel_base,cfg.known_wheelbase_error);C=-G6@Q@B;R=float(B@Q@B);y=o-h
        H7=np.r_[H,0.];C7=np.r_[C,0.];S=float(H7@self.P@H7+R+2*H7@C7)
        if cfg.use_odom_heading and S>1e-20:
            if y*y/S>CHI2_1_999:self.stats['o_rejected']+=1
            else:self.x,self.P,_=F.correlated_update(self.x,self.P,H7,y,R,C7);self.stats['o_updates']+=1
    def range_update(self,z):
        a=self.cfg.anchor_xyz;dz=a[2]-self.cfg.robot_z;x=self.x;h=math.sqrt((x[0]-a[0])**2+(x[1]-a[1])**2+dz**2)
        if h<=1e-12:return
        H=np.zeros(7);H[:2]=(x[:2]-np.array(a[:2]))/h;H[6]=1.0;y=float(z-(h+self.off+x[6]));S=float(H@self.P@H+self.rw)
        if S<=1e-20:return
        if y*y/S>self.cfg.gate:self.stats['r_rejected']+=1;return
        K=self.P@H/S;M=np.eye(7)-np.outer(K,H);self.P=M@self.P@M.T+self.rw*np.outer(K,K);self.P=(self.P+self.P.T)/2;self.x=self.x+K*y;self.x[2]=wrap(self.x[2]);self.stats['r_updates']+=1
        return y,S
    def mean_cov(self):return self.x[:6].copy(),self.P[:6,:6].copy()

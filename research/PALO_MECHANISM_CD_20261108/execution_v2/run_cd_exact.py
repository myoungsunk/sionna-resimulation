"""Numerical repair of v1 batch implementation; scientific contract unchanged.
Failure evidence: Actions 42450550130 stopped BEFORE C/D at strict C0 Full/B0
X=1.6643e-7,P=3.1931e-8,NIS=4.2953e-7,mask=0. No tolerance relaxation.
Use original scalar algebraic ordering, math trigonometry for motion, full
GQG^T, H@P solve and Joseph update. Re-run ALL original parity checks.
"""
import sys,math,hashlib
from pathlib import Path
import numpy as np
import run_cd_base as M
M.DEST='research/PALO_MECHANISM_CD_20261108/execution_v2'

def observe(self,x):
 x=np.asarray(x);anchor=np.asarray(self.case['anchor'],float)
 u=x[:,0]-anchor[0];v=x[:,1]-anchor[1];h=anchor[2]-float(self.case['robot_z_m'])
 rho2=np.maximum(u*u+v*v,1e-12);rho=np.sqrt(rho2)
 psi=np.degrees(x[:,2])+float(self.case['mount_deg'])
 theta=np.degrees(np.arctan2(rho,h));tx=np.degrees(np.arctan2(-v,u));rx=(np.degrees(np.arctan2(-v,-u))-psi+180.)%360.-180.
 tt=theta/self.dt;clip=(tt<0)|(tt>self.nt-1-1e-9);t=np.clip(tt,0.,self.nt-1-1e-9)
 a=(tx+180.)/self.dp;b=(rx+180.)/self.dp
 i=np.floor(t).astype(int);jf=np.floor(a);kf=np.floor(b);ft=t-i;fa=a-jf;fb=b-kf
 j=jf.astype(int)%self.np;k=kf.astype(int)%self.np;j1=(j+1)%self.np;k1=(k+1)%self.np
 S=self.lut;c000,c001,c010,c011=S[i,j,k],S[i,j,k1],S[i,j1,k],S[i,j1,k1];c100,c101,c110,c111=S[i+1,j,k],S[i+1,j,k1],S[i+1,j1,k],S[i+1,j1,k1]
 c00=c000*(1-fb)+c001*fb;c01=c010*(1-fb)+c011*fb;c10=c100*(1-fb)+c101*fb;c11=c110*(1-fb)+c111*fb
 c0=c00*(1-fa)+c01*fa;c1=c10*(1-fa)+c11*fa
 val=c0*(1-ft)+c1*ft;gt=(c1-c0)/self.dt;ga=((c01-c00)*(1-ft)+(c11-c10)*ft)/self.dp
 gb=(((c001-c000)*(1-fa)+(c011-c010)*fa)*(1-ft)+((c101-c100)*(1-fa)+(c111-c110)*fa)*ft)/self.dp
 deg=180./np.pi
 dth_du=h/(rho2+h*h)*u/rho*deg;dth_dv=h/(rho2+h*h)*v/rho*deg
 dtx_du=v/rho2*deg;dtx_dv=-u/rho2*deg;drx_du=-v/rho2*deg;drx_dv=u/rho2*deg
 H=np.zeros((len(x),4));H[:,0]=gt*dth_du+ga*dtx_du+gb*drx_du;H[:,1]=gt*dth_dv+ga*dtx_dv+gb*drx_dv;H[:,2]=-gb*deg
 assert np.isfinite(val).all() and np.isfinite(H).all()
 return val,H,clip

def candidate(self,x,P,z):
 P=(P+P.transpose(0,2,1))/2;h,H,clip=self.observe(x);nu=np.asarray(z)-h
 hp=H[:,None,:]@P;S3=hp@H[:,:,None]+M.RS;ss=S3[:,0,0]
 K=np.linalg.solve(S3,hp).transpose(0,2,1)[:,:,0]
 nis=(nu[:,None,None]@np.linalg.solve(S3,nu[:,None,None]))[:,0,0]
 d=K*nu[:,None];out=x+d;out[:,2]=M.wrap(out[:,2]);A=np.eye(4)[None]-K[:,:,None]@H[:,None,:]
 C=A@P@A.transpose(0,2,1)+(K[:,:,None]*M.RS)@K[:,None,:];C=(C+C.transpose(0,2,1))/2
 return out,C,dict(h=h,H=H,nu=nu,S=ss,K=K,d=d,nis=nis,clip=clip)

def advance(self,x,P,ds,gyro,dt):
 n=len(x);ds=np.broadcast_to(ds,(n,));gyro=np.broadcast_to(gyro,(n,));dt=np.broadcast_to(dt,(n,));a=gyro-x[:,3]*dt
 c=np.empty(n);dc=np.empty(n)
 for j,z in enumerate(a):c[j],dc[j]=self.core.sinc_half(float(z))
 phi=x[:,2]+a/2;co=np.fromiter((math.cos(z) for z in phi),float,count=n);si=np.fromiter((math.sin(z) for z in phi),float,count=n)
 u=np.stack([co,si],1);up=np.stack([-si,co],1);d=(ds*c)[:,None]*u;v=ds[:,None]*(dc[:,None]*u+c[:,None]*up/2)
 out=x.copy();out[:,:2]+=d;out[:,2]=M.wrap(x[:,2]+a)
 F=np.broadcast_to(np.eye(4),(n,4,4)).copy();F[:,:2,2]=np.stack([-d[:,1],d[:,0]],1);F[:,:2,3]=-dt[:,None]*v;F[:,2,3]=-dt
 G=np.zeros((n,4,3));G[:,:2,0]=c[:,None]*u;G[:,:2,1]=v;G[:,2,1]=1.;G[:,3,2]=1.
 Q=np.zeros((n,3,3));Q[:,0,0]=2e-5*abs(ds);Q[:,1,1]=math.radians(.015)**2*dt
 P=(P+P.transpose(0,2,1))/2;C=F@P@F.transpose(0,2,1)+G@Q@G.transpose(0,2,1);C=(C+C.transpose(0,2,1))/2
 return out,C

M.Model.observe=observe;M.Model.candidate=candidate;M.Model.advance=advance
orig_dump=M.dump
def dump(p,x):
 if p.name=='EXECUTION_CONTRACT.json':
  x['execution_version']='v2 operation-order repair; unchanged parity thresholds'
  x['failed_v1_run']=42450550130
  x['base_runner_sha256']=hashlib.sha256(Path(M.__file__).read_bytes()).hexdigest()
  x['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  p.parent.mkdir(parents=True,exist_ok=True);(p.parent/'RUNNER_DRIVER.py').write_bytes(Path(__file__).read_bytes())
 orig_dump(p,x)
M.dump=dump
if __name__=='__main__':M.main()

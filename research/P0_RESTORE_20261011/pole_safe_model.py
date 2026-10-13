"""Candidate near-pole Cartesian FFD model; original LUT is never overwritten.
Fits complex physical Cartesian fields, NOT evaluation s labels or true heading.
Primary: theta<=1deg fit, smooth 1..3deg splice, original LUT at >=3deg.
First-path tap switches remain piecewise differentiable and are logged in tests.
"""
from __future__ import annotations
import math
import numpy as np
from qclean_uwb.drivesim import pattern_apply as PA,observation as O,hs_lut as HL

class CartesianPoleField:
    def __init__(self,banks):
        self.freq=np.asarray(banks[0].freqs_hz,float)
        self.scale=math.sin(math.radians(4))
        self.terms=[(i,j) for deg in range(1,5) for i in range(deg+1) for j in [deg-i]]
        self.coeff=[];self.origin=[];self.fit_receipts=[]
        for bank in banks:
            assert np.array_equal(self.freq,bank.freqs_hz)
            ti=np.flatnonzero((bank.theta>1e-9)&(bank.theta<=math.radians(4)+1e-8))
            pi=np.arange(0,len(bank.phi)-1,5)
            p=bank.phi[pi]
            # Convert original theta=0 spherical components to Cartesian FIRST.
            th=np.zeros_like(bank.phi);et,ep=PA.sph_basis(th,bank.phi)
            cart0=bank.e_theta[:,0,:,None]*et[None]+bank.e_phi[:,0,:,None]*ep[None]
            origin=cart0[:,:-1].mean(axis=1)
            samples=[];coords=[]
            for it in ti:
                th=np.full(len(pi),bank.theta[it]);et,ep=PA.sph_basis(th,p)
                vals=bank.e_theta[:,it,pi,None]*et[None]+bank.e_phi[:,it,pi,None]*ep[None]
                samples.append(vals.transpose(1,0,2))
                coords.append(np.c_[np.sin(th)*np.cos(p),np.sin(th)*np.sin(p)]/self.scale)
            q=np.concatenate(coords);y=np.concatenate(samples)-origin[None]
            X=np.stack([q[:,0]**i*q[:,1]**j for i,j in self.terms],axis=1)
            beta=np.linalg.lstsq(X,y.reshape(len(y),-1),rcond=None)[0].reshape(len(self.terms),len(self.freq),3)
            fit=np.einsum('nt,tfc->nfc',X,beta)+origin[None]
            true=y+origin[None]
            self.fit_receipts.append({'n_training_fields':len(y),'degree':4,'theta_max_deg':4.,
                'complex_relative_RMS':float(np.linalg.norm(fit-true)/np.linalg.norm(true))})
            self.coeff.append(beta);self.origin.append(origin)
        self.coeff=np.asarray(self.coeff);self.origin=np.asarray(self.origin)

    def field(self,port,q):
        a,b=np.asarray(q)/self.scale
        m=np.array([a**i*b**j for i,j in self.terms])
        ma=np.array([i*a**(i-1)*b**j if i else 0. for i,j in self.terms])/self.scale
        mb=np.array([j*a**i*b**(j-1) if j else 0. for i,j in self.terms])/self.scale
        beta=self.coeff[port]
        return self.origin[port]+np.einsum('t,tfc->fc',m,beta),np.stack([np.einsum('t,tfc->fc',ma,beta),np.einsum('t,tfc->fc',mb,beta)])

    def s_jac(self,anchor,robot_z,x,y,psi,mount):
        u,v=float(x-anchor[0]),float(y-anchor[1]);h=float(anchor[2]-robot_z)
        d=math.sqrt(u*u+v*v+h*h);a=np.array([u,v])/d
        da=(np.eye(2)-np.outer(a,a))/d
        angle=psi+math.radians(mount);c,s=math.cos(angle),math.sin(angle)
        R=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
        dR=np.array([[-s,-c,0.],[c,-s,0.],[0.,0.,0.]])
        RTX=np.diag([1.,-1.,-1.]);Rt=R[:2,:2].T
        qt=np.array([a[0],-a[1]]);qr=-Rt@a
        Jt=np.zeros((2,3));Jt[:,:2]=np.diag([1.,-1.])@da
        Jr=np.zeros((2,3));Jr[:,:2]=-Rt@da;Jr[:,2]=[qr[1],-qr[0]]
        et,det=self.field(0,qt);ET=et@RTX.T*PA.SCALE
        dET=np.einsum('qfc,qj->jfc',det,Jt)@RTX.T*PA.SCALE
        H=[];dH=[]
        for port in range(2):
            er,der=self.field(port,qr);ER=er@R.T*PA.SCALE
            dER=np.einsum('qfc,qj->jfc',der,Jr)@R.T*PA.SCALE
            dER[2]+=er@dR.T*PA.SCALE
            H.append(np.einsum('fc,fc->f',ER,ET))
            dH.append(np.einsum('jfc,fc->jf',dER,ET)+np.einsum('fc,jfc->jf',ER,dET))
        scale=O.C0/self.freq/(4*np.pi*10)*np.exp(-2j*np.pi*self.freq*10/O.C0)
        hc=np.stack(H,axis=-1)*scale[:,None]
        dh=np.stack(dH,axis=-1)*scale[None,:,None]
        cs=O.cir_batch(np.concatenate([hc[None],dh],axis=0))
        base=O.first_path_batch(cs[:1],self.freq[1]-self.freq[0]);k=int(base['index'][0])
        p=np.abs(cs[0,k])**2;tot=float(p.sum());val=float((p[0]-p[1])/tot)
        dp=2*np.real(np.conj(cs[0,k])[None]*cs[1:,k])
        jac=((dp[:,0]-dp[:,1])-val*dp.sum(axis=1))/tot
        return val,jac,k

class PoleSafeModel:
    def __init__(self,lut,banks):
        self.original_lut=lut;self.field=CartesianPoleField(banks)
        self.model_version='CARTESIAN_FIELD_DEG4_CORE1_BLEND1_3_FP_V1'

    def scalar(self,anchor,z,x,y,psi,mount=0.,with_jac=False):
        u,v=x-anchor[0],y-anchor[1];rho=math.hypot(u,v);height=anchor[2]-z
        theta=math.degrees(math.atan2(rho,height))
        if theta>=3.:
            return HL.s_model(self.original_lut,anchor,z,x,y,psi,mount,with_jac=with_jac)
        val,J,tap=self.field.s_jac(anchor,z,x,y,psi,mount)
        if theta<=1.:
            return (val,J) if with_jac else val
        t=(theta-1)/2;w=t**3*(10-15*t+6*t*t);dw=30*t*t*(t-1)**2/2
        outer,K=HL.s_model(self.original_lut,anchor,z,x,y,psi,mount,with_jac=True)
        dtheta=np.array([height*u/(rho*(rho*rho+height*height)),height*v/(rho*(rho*rho+height*height)),0.])*180/np.pi
        result=(1-w)*val+w*outer
        deriv=(1-w)*J+w*K+dw*dtheta*(outer-val)
        return (float(result),deriv) if with_jac else float(result)

    def __call__(self,anchor,z,x,y,psi,mount=0.,with_jac=False):
        xx,yy,pp=np.broadcast_arrays(x,y,psi)
        if xx.ndim==0:return self.scalar(anchor,z,float(xx),float(yy),float(pp),mount,with_jac)
        result=[self.scalar(anchor,z,float(a),float(b),float(c),mount,with_jac) for a,b,c in zip(xx.flat,yy.flat,pp.flat)]
        if with_jac:
            return np.array([r[0] for r in result]).reshape(xx.shape),np.array([r[1] for r in result]).reshape(xx.shape+(3,))
        return np.array(result).reshape(xx.shape)

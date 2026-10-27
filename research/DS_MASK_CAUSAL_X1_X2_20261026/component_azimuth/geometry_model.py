"""Source FFD observation, actual range/FP tap, analytic within-active-cell Jacobian.

No pose GT, native LoS channel, training labels or future samples are arguments.
Range prediction remains the frozen continuous ranging surrogate d+B_OLD.
Polarization prediction uses source complex fields, ACTUAL hypothesized range,
and the frozen two-port Hann/leading-edge observation chain. This is not a
normalized Bayesian measurement likelihood. Angular interpolation cell and
first-path detector changes are genuinely nonsmooth and returned as diagnostics.
A source-only Cartesian polynomial cap (0.1--0.5 deg blend) regularizes the
north pole. It is fitted only to 1/3-degree source-bank rings, never RF labels.
"""
from __future__ import annotations
import numpy as np
from p0_initial import load_banks, ROOT, OUT, P, O, ANCHOR_ROTATION
from p3_rf_adapter4 import B_OLD

class GeometryFFD:
 def __init__(self,banks=None):
  self.banks=load_banks() if banks is None else banks
  self.freqs=self.banks[0].freqs_hz;self.nf=len(self.freqs)
  self.window=.5-.5*np.cos(2*np.pi*np.arange(self.nf)/(self.nf-1))
  self.cap=self._fit_caps()

 def _field(self,bank,th,ph,gradient):
  """Independent complex bilinear interpolation and analytic vector derivatives."""
  tt=np.clip((th-bank.t0)/bank.dt,0,bank.nt-1)
  pp=((ph-bank.p0)%(2*np.pi))/bank.dp
  it=np.minimum(np.floor(tt).astype(int),bank.nt-2)
  ip=np.minimum(np.floor(pp).astype(int),bank.np-2)
  wt=tt-it;wp=pp-ip
  val=[];gt=[];gp=[]
  for e in (bank.e_theta,bank.e_phi):
   a,b,c,d=[e[:,ii,jj].T for ii,jj in ((it,ip),(it,ip+1),(it+1,ip),(it+1,ip+1))]
   lo=(1-wp[:,None])*a+wp[:,None]*b;hi=(1-wp[:,None])*c+wp[:,None]*d
   val.append((1-wt[:,None])*lo+wt[:,None]*hi)
   if gradient:
    gt.append((hi-lo)/bank.dt)
    gp.append(((1-wt[:,None])*(b-a)+wt[:,None]*(d-c))/bank.dp)
  ct,st,cp,sp=np.cos(th),np.sin(th),np.cos(ph),np.sin(ph)
  t=np.column_stack([ct*cp,ct*sp,-st]);p=np.column_stack([-sp,cp,np.zeros_like(sp)])
  F=val[0][...,None]*t[:,None]+val[1][...,None]*p[:,None]
  if not gradient:return P.SCALE*F,None,None,np.column_stack([it,ip])
  unit=np.column_stack([st*cp,st*sp,ct]);dp=np.column_stack([-cp,-sp,np.zeros_like(cp)])
  Ft=gt[0][...,None]*t[:,None]+gt[1][...,None]*p[:,None]-val[0][...,None]*unit[:,None]
  Fp=gp[0][...,None]*t[:,None]+gp[1][...,None]*p[:,None]+val[0][...,None]*ct[:,None,None]*p[:,None]+val[1][...,None]*dp[:,None]
  return P.SCALE*F,P.SCALE*Ft,P.SCALE*Fp,np.column_stack([it,ip])

 def _fit_caps(self):
  """Fit local Cartesian Taylor chart solely to source FFD rings 1 and 3 deg.
  Ring 2 is NOT fit: it is reserved for a source-grid validation below.
  Constant E(0) is fixed to the complex64 source pole average, not estimated.
  """
  self.cap_scale=np.sin(np.radians(3.));self.powers=[(i,j) for total in (1,2,3) for i in range(total+1) for j in [total-i]]
  caps=[]
  for bank in self.banks:
   def cart_nodes(deg):
    ph=bank.phi[:-1];th=np.full(len(ph),np.radians(deg));tt,pp=P.sph_basis(th,ph)
    e=(bank.e_theta[:,deg,:-1,None]*tt[None]+bank.e_phi[:,deg,:-1,None]*pp[None]).transpose(1,0,2)*P.SCALE
    q=np.column_stack([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
    return q,e
   _,pole=cart_nodes(0);e0=pole.mean(axis=0)
   qs=[];es=[]
   for theta in (1,3):
    q,e=cart_nodes(theta);qs.append(q);es.append(e)
   q=np.concatenate(qs);e=np.concatenate(es);u=q[:,0]/self.cap_scale;v=q[:,1]/self.cap_scale
   A=np.column_stack([u**i*v**j for i,j in self.powers]);target=(e-e0).reshape(len(q),-1)
   coeff=np.linalg.lstsq(A,target,rcond=None)[0].reshape(len(self.powers),self.nf,3)
   caps.append((e0,coeff))
  return caps

 def _cartesian_field(self,bank_index,q,gradient):
  """Field vector and derivative with respect to local unit-direction q."""
  bank=self.banks[bank_index];rho=np.hypot(q[:,0],q[:,1]);qnorm2=np.sum(q*q,axis=1)
  th=np.arctan2(rho,q[:,2]);ph=np.arctan2(q[:,1],q[:,0])
  F,Ft,Fp,cells=self._field(bank,th,ph,gradient)
  inner=np.radians(.1);outer=np.radians(.5);cap=th<outer
  if gradient:
   safe=np.maximum(rho,1e-30)
   dt=np.column_stack([q[:,2]*q[:,0]/(qnorm2*safe),q[:,2]*q[:,1]/(qnorm2*safe),-rho/qnorm2])
   dp=np.column_stack([-q[:,1]/safe**2,q[:,0]/safe**2,np.zeros(len(q))])
   J=Ft[...,None]*dt[:,None,None,:]+Fp[...,None]*dp[:,None,None,:]
  else:J=None
  if np.any(cap):
   Q=q[cap];uu=Q[:,0]/self.cap_scale;vv=Q[:,1]/self.cap_scale;e0,coef=self.cap[bank_index]
   A=np.column_stack([uu**i*vv**j for i,j in self.powers]);E=e0[None]+np.einsum('na,afi->nfi',A,coef)
   along=np.einsum('ni,nfi->nf',Q,E)
   Ec=E-Q[:,None,:]*along[:,:,None]  # enforce transverse physical field
   if gradient:
    dA=np.zeros((len(Q),len(self.powers),3))
    for col,(i,j) in enumerate(self.powers):
     if i:dA[:,col,0]=i*uu**(i-1)*vv**j/self.cap_scale
     if j:dA[:,col,1]=j*uu**i*vv**(j-1)/self.cap_scale
    dE=np.einsum('nak,afi->nfik',dA,coef)
    dalong=E+np.einsum('ni,nfik->nfk',Q,dE)
    Jc=dE-np.eye(3)[None,None]*along[:,:,None,None]-Q[:,None,:,None]*dalong[:,:,None,:]
   z=np.clip((th[cap]-inner)/(outer-inner),0,1);w=6*z**5-15*z**4+10*z**3
   if gradient:
    dw=(30*z**4-60*z**3+30*z**2)/(outer-inner)
    J[cap]=(1-w[:,None,None,None])*Jc+w[:,None,None,None]*J[cap]+(F[cap]-Ec)[...,None]*dw[:,None,None,None]*dt[cap,None,None,:]
   F[cap]=(1-w[:,None,None])*Ec+w[:,None,None]*F[cap]
   # This chart is not separated by old spherical FFD azimuth cells.
   cells[th<=inner]=-1
  return F,J,cells,cap

 def spectrum(self,states,case,gradient=True):
  x=np.atleast_2d(np.asarray(states,float))
  if x.shape[1] not in (3,4) or not np.isfinite(x).all():raise ValueError('INVALID_STATE')
  anchor=np.asarray(case['anchor'],float);u=x[:,0]-anchor[0];v=x[:,1]-anchor[1];height=float(anchor[2]-case['robot_z_m'])
  if height<=0:raise ValueError('SOURCE_MODEL_REQUIRES_UP_TAG_DOWN_ANCHOR')
  rho=np.hypot(u,v);dist=np.sqrt(rho*rho+height*height);n=len(x)
  yaw=x[:,2]+np.radians(case['mount_deg']);co,si=np.cos(yaw),np.sin(yaw)
  d=np.column_stack([u,v,np.full(n,-height)])/dist[:,None]
  dr=np.column_stack([u/dist,v/dist,np.zeros(n)])
  real_dist=dist.copy();real_dr=dr.copy()
  D=np.zeros((n,3,3));D[:,:,0]=(np.array([1,0,0])[None]-d*dr[:,0,None])/dist[:,None];D[:,:,1]=(np.array([0,1,0])[None]-d*dr[:,1,None])/dist[:,None]
  d,dist,dr,D=self.geometry(x,case,d,dist,dr,D)
  def rot(F):
   a=F.copy();a[:,:,0]=co[:,None]*F[:,:,0]-si[:,None]*F[:,:,1];a[:,:,1]=si[:,None]*F[:,:,0]+co[:,None]*F[:,:,1];return a
  qt=d@ANCHOR_ROTATION
  T,Jt,cell_t,cap_t=self._cartesian_field(0,qt,gradient);T=T@ANCHOR_ROTATION.T
  qr=np.column_stack([-co*d[:,0]-si*d[:,1],si*d[:,0]-co*d[:,1],-d[:,2]])
  if gradient:
   Dqt=np.einsum('ij,njk->nik',ANCHOR_ROTATION.T,D)
   dT=np.einsum('nfij,njk->nfik',Jt,Dqt);dT=np.einsum('ij,nfjk->nfik',ANCHOR_ROTATION,dT)
   Dqr=-D.copy();Dqr[:,0,:]=-co[:,None]*D[:,0,:]-si[:,None]*D[:,1,:];Dqr[:,1,:]=si[:,None]*D[:,0,:]-co[:,None]*D[:,1,:]
   Dqr[:,:,2]=np.column_stack([qr[:,1],-qr[:,0],np.zeros(n)])
  spectra=[];dspectra=[];cells=[]
  fdelta=self.freqs-self.freqs[0]
  factor=O.C0/self.freqs[None,:]/(4*np.pi*dist[:,None])*np.exp(-2j*np.pi*fdelta[None,:]*dist[:,None]/O.C0)
  for ib in range(2):
   R,Jr,cell,cap_r=self._cartesian_field(ib,qr,gradient);R=rot(R);cells.append(cell)
   z=np.einsum('nfi,nfi->nf',R,T);spectra.append(z*factor)
   if gradient:
    local_dR=np.einsum('nfij,njk->nfik',Jr,Dqr)
    dR=local_dR.copy();dR[:,:,0,:]=co[:,None,None]*local_dR[:,:,0,:]-si[:,None,None]*local_dR[:,:,1,:];dR[:,:,1,:]=si[:,None,None]*local_dR[:,:,0,:]+co[:,None,None]*local_dR[:,:,1,:]
    dR[:,:,:,2]+=np.stack([-R[:,:,1],R[:,:,0],np.zeros_like(R[:,:,0])],axis=-1)
    dz=np.einsum('nfik,nfi->nfk',dR,T)+np.einsum('nfi,nfik->nfk',R,dT)
    dfactor=factor[:,:,None]*(-1/dist[:,None,None]-2j*np.pi*fdelta[None,:,None]/O.C0)*dr[:,None,:]
    dspectra.append(dz*factor[:,:,None]+z[:,:,None]*dfactor)
  h=np.stack(spectra,axis=2);dh=np.stack(dspectra,axis=2) if gradient else None
  return h,dh,real_dist,real_dr,np.column_stack([cell_t,*cells]),rho

 def physical_h_col(self,states,case):
  h,_,dist,_,_,_=self.spectrum(states,case,gradient=False)
  return h*np.exp(-2j*np.pi*self.freqs[0]*dist/O.C0)[:,None,None]

 def batch(self,states,case,gradient=True,return_diagnostics=False):
  h,dh,dist,dr,cells,rho=self.spectrum(states,case,gradient)
  cir=np.fft.ifft(h*self.window[None,:,None],n=4*self.nf,axis=1)*self.nf
  obs=O.first_path_batch(cir,float(self.freqs[1]-self.freqs[0]));idx=obs['index'];n=len(h);ii=np.arange(n);amp=np.abs(cir)
  branch=amp.max(axis=1).argmax(axis=1)
  strong=amp[ii,:,branch];threshold=.3*strong.max(axis=1)
  # Dimensionless margin to the detector's active inequality. The leading
  # edge below/above margins reveal imminent tap transitions, not RF noise.
  above=strong[ii,idx]-threshold
  below=threshold-np.where(idx>0,strong[ii,np.maximum(idx-1,0)],0.)
  margin=np.minimum(above,below)/np.maximum(strong.max(axis=1),np.finfo(float).tiny)
  pred=np.column_stack([dist+B_OLD,obs['s']]);J=None
  if gradient:
   dcir=np.fft.ifft(dh*self.window[None,:,None,None],n=4*self.nf,axis=1)*self.nf
   cf=cir[ii,idx];dcp=dcir[ii,idx]
   power=np.abs(cf)**2;dpower=2*np.real(cf.conj()[...,None]*dcp)
   den=power.sum(axis=1)
   jac=(dpower[:,0]-dpower[:,1]-obs['s'][:,None]*dpower.sum(axis=1))/den[:,None]
   J=np.zeros((n,2,4));J[:,0,:3]=dr;J[:,1,:3]=jac
   if not np.isfinite(J).all():raise RuntimeError('NONFINITE_SOURCE_JACOBIAN')
  if not np.isfinite(pred).all():raise RuntimeError('NONFINITE_SOURCE_OBSERVER')
  diag=dict(tap=idx,strong_port=branch,cells=cells,fp_margin=margin,native_range=obs['range_m'],rho=rho)
  return (pred,J,diag) if return_diagnostics else (pred,J)

 def model(self,state,case):
  h,H=self.batch(np.asarray(state)[None,:],case,gradient=True)
  return h[0],H[0]

 def geometry(self,x,case,d,dist,dr,D):
  # d is anchor-to-tag; both antennas consume this same vector.
  if getattr(self,'explicit',None) is not None:
   uu,rr=self.explicit
   return -np.broadcast_to(uu,d.shape).copy(),np.broadcast_to(rr,dist.shape).copy(),dr,D
  modes=getattr(self,'modes',None)
  if modes is None:return d,dist,dr,D
  modes=np.broadcast_to(np.asarray(modes),len(x));gt=np.broadcast_to(self.gt,(len(x),4))
  a=np.asarray(case['anchor']);height=a[2]-case['robot_z_m']
  vx=x[:,0]-a[0];vy=x[:,1]-a[1];rho=np.hypot(vx,vy)
  assert np.all(rho>1e-9),'undefined azimuth axis'
  beta=np.arctan2(-vy,-vx);el=np.arctan2(height,rho)
  gx=gt[:,0]-a[0];gy=gt[:,1]-a[1];grho=np.hypot(gx,gy)
  gb=np.arctan2(-gy,-gx);ge=np.arctan2(height,grho)
  az=(modes=='CUT_ALL')|(modes=='CUT_AZ');ee=(modes=='CUT_ALL')|(modes=='CUT_EL');rr=(modes=='CUT_ALL')|(modes=='CUT_R')
  beta=np.where(az,gb,beta);el=np.where(ee,ge,el)
  cb,sb,ce,se=np.cos(beta),np.sin(beta),np.cos(el),np.sin(el)
  changed=az|ee
  dnew=-np.column_stack([ce*cb,ce*sb,se])
  db=np.column_stack([-vy/rho**2,vx/rho**2,np.zeros(len(x))]);db[az]=0
  de=np.column_stack([-height*vx/(rho*dist**2),-height*vy/(rho*dist**2),np.zeros(len(x))]);de[ee]=0
  dd_db=np.column_stack([ce*sb,-ce*cb,np.zeros(len(x))])
  dd_de=np.column_stack([se*cb,se*sb,-ce])
  deriv=dd_db[:,:,None]*db[:,None,:]+dd_de[:,:,None]*de[:,None,:]
  d[changed]=dnew[changed];D[changed]=deriv[changed]
  dist[rr]=np.sqrt(grho[rr]**2+height**2);dr[rr]=0
  return d,dist,dr,D

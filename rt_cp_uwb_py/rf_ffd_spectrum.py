"""Real-direction FFD coupling of the propagating TT spectrum only.

No evanescent continuation is invented from a sampled far-field bank. This
diagnostic is NOT a corrected full lossy-volume channel or a CIR producer.
"""
import numpy as np
from .rf_layered_reference import validate,tt_coefficients,_gauss,C0
from .rf_volume_channel import Z0


def grid_fields_many(theta_deg,phi_deg,e_theta,e_phi,directions,rotation=None):
    rotation=np.eye(3) if rotation is None else np.asarray(rotation,float)
    directions=np.asarray(directions,float)
    if rotation.shape!=(3,3) or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-10,rtol=0) or abs(np.linalg.det(rotation)-1)>1e-10:
        raise ValueError('INVALID_ROTATION')
    if directions.ndim!=2 or directions.shape[1]!=3 or not np.isfinite(directions).all() or not np.allclose(np.linalg.norm(directions,axis=1),1,atol=1e-9,rtol=0):
        raise ValueError('REAL_UNIT_DIRECTIONS_REQUIRED')
    th=np.asarray(theta_deg);ph=np.asarray(phi_deg);et=np.asarray(e_theta);ep=np.asarray(e_phi)
    if th.ndim!=1 or ph.ndim!=1 or min(len(th),len(ph))<2 or np.any(np.diff(th)<=0) or np.any(np.diff(ph)<=0) or abs(th[0])>1e-8 or abs(th[-1]-180)>1e-8 or abs(ph[-1]-ph[0]-360)>1e-8 or et.shape!=(len(th),len(ph)) or ep.shape!=et.shape:
        raise ValueError('INVALID_FULL_SPHERE_GRID')
    local=directions@rotation;t=np.arccos(np.clip(local[:,2],-1,1));p=np.arctan2(local[:,1],local[:,0])
    td=np.degrees(t);pd=(np.degrees(p)-ph[0])%360+ph[0]
    i=np.clip(np.searchsorted(th,td,side='right')-1,0,len(th)-2);j=np.clip(np.searchsorted(ph,pd,side='right')-1,0,len(ph)-2)
    a=(td-th[i])/(th[i+1]-th[i]);b=(pd-ph[j])/(ph[j+1]-ph[j])
    def interp(f):return (1-a)*((1-b)*f[i,j]+b*f[i,j+1])+a*((1-b)*f[i+1,j]+b*f[i+1,j+1])
    vt=np.column_stack((np.cos(t)*np.cos(p),np.cos(t)*np.sin(p),-np.sin(t)))
    vp=np.column_stack((-np.sin(p),np.cos(p),np.zeros(len(p))))
    result=(interp(et)[:,None]*vt+interp(ep)[:,None]*vp)@rotation.T
    if not np.isfinite(result).all():raise ValueError('NONFINITE_FFD')
    return result*np.sqrt(2*np.pi/Z0)  # P1 bank: 1 W incident; no re-normalization.


def propagating_ffd_tt(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m,
                       tx_pattern,rx_emitted_pattern,*,order=256,n_phi=512,frame=None):
    validate(epsilon,frequency_hz,air_distance_m,thickness_m,rho_m)
    frame=np.eye(3) if frame is None else np.asarray(frame,float)
    if frame.shape!=(3,3) or not np.allclose(frame.T@frame,np.eye(3),atol=1e-10,rtol=0) or abs(np.linalg.det(frame)-1)>1e-10:raise ValueError('INVALID_FRAME')
    if order<16 or n_phi<16:raise ValueError('INSUFFICIENT_QUADRATURE')
    nodes,weights=_gauss(order);q=(nodes+1)/2;weights=weights/2
    phi=2*np.pi*np.arange(n_phi)/n_phi;cp=np.cos(phi);sp=np.sin(phi)
    k=2*np.pi*frequency_hz/C0;n=np.sqrt(complex(epsilon));total=None
    for start in range(0,order,16):
        z=q[start:start+16,None];s=np.sqrt(1-z*z);shape=(len(z),n_phi)
        direction=np.stack((s*cp,s*sp,np.broadcast_to(z,shape)),axis=-1).reshape(-1,3)@frame.T
        sv=np.broadcast_to(np.stack((-sp,cp,np.zeros(n_phi)),axis=-1),(len(z),n_phi,3)).reshape(-1,3)@frame.T
        pv=np.stack((z*cp,z*sp,np.broadcast_to(-s,shape)),axis=-1).reshape(-1,3)@frame.T
        tx=np.asarray(tx_pattern(direction));rx=np.asarray(rx_emitted_pattern(-direction))
        if tx.ndim!=3 or rx.ndim!=3 or tx.shape[:2]!=direction.shape or rx.shape[:2]!=direction.shape:raise ValueError('PATTERN_SHAPE_M_3_PORTS')
        if not np.isfinite(tx).all() or not np.isfinite(rx).all():raise ValueError('NONFINITE_PATTERN')
        for field in (tx,rx):
            if np.linalg.norm(np.einsum('ni,nip->np',direction,field))>1e-9*max(1.,np.linalg.norm(field)):raise ValueError('PATTERN_NOT_TRANSVERSE')
        ts=np.einsum('ni,nip->np',sv,tx);tp=np.einsum('ni,nip->np',pv,tx)
        rs=np.einsum('ni,nip->np',sv,rx);rp=np.einsum('ni,nip->np',pv,rx)
        te,tm,q1=tt_coefficients(z,epsilon)
        phase=np.exp(-1j*k*(rho_m*s*cp+air_distance_m*z+thickness_m*(q1-n)))
        w=weights[start:start+len(z),None]*phase/n_phi
        part=np.einsum('n,np,nq->pq',(w*te).ravel(),rs,ts)+np.einsum('n,np,nq->pq',(w*tm).ravel(),rp,tp)
        total=part if total is None else total+part
    scaled=-1j*k*total*(C0/frequency_hz)/(4*np.pi)
    return {'H_propagating':scaled*np.exp(-1j*k*n*thickness_m),'scaled_H_propagating':scaled,
        'scope':'propagating spectrum only; reciprocal emitted RX, no conjugation',
        'evanescent_qualified':False,'finite_frequency_correction_applied':False,
        'production_admission':False,'complete_channel_admission':False,'CIR_qualified':False}

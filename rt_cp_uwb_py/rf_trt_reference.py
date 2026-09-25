"""Independent first-return planar wave reference at finite-scene endpoints.

Finite visibility comes from separately audited scene paths. This reference
checks vector boundary factors and phase, NOT finite-body spherical spreading.
"""
import numpy as np


def first_return_field(path,epsilon,frequency_hz,incident_polarization):
    if path['choices']!='TRT':raise ValueError('TRT_REQUIRED')
    events=path['events'];points=np.asarray(path['points'],float);n=np.asarray(events[0]['normal'],float)
    if any(abs(abs(n@e['normal'])-1)>1e-8 for e in events):raise ValueError('PARALLEL_SLAB_REQUIRED')
    if abs(n@(points[3]-points[1]))>1e-7:raise ValueError('SAME_FRONT_FACE_REQUIRED')
    ep=complex(epsilon)
    if ep.real<=0 or ep.imag>0 or frequency_hz<=0:raise ValueError('PASSIVE_POSITIVE_INPUT_REQUIRED')
    k=np.asarray(path['launch_direction'],float);pol=np.asarray(incident_polarization,complex)
    pol=pol-k*(k@pol);pol/=np.linalg.norm(pol)
    tangential=k-n*(n@k);s=np.linalg.norm(tangential);q0=abs(n@k)
    if q0<1e-4:raise ValueError('GRAZING_REFERENCE_UNSUPPORTED')
    if s<1e-10:
        tangent=np.cross(n,np.eye(3)[np.argmin(abs(n))]);tangent/=np.linalg.norm(tangent)
    else:tangent=tangential/s
    te=np.cross(tangent,n);te/=np.linalg.norm(te)
    kout=k-2*(k@n)*n;tmout=tangent-n*(tangent@kout)/(n@kout)
    q1=np.sqrt(ep-s*s);d=abs(n@(points[2]-points[1]))
    L=abs(n@(points[1]-points[0]))+abs(n@(points[4]-points[3]))
    phase=np.exp(-2j*np.pi*frequency_hz/299792458.*(tangential@(points[4]-points[0])+q0*L+2*q1*d))
    rTE=(q0-q1)/(q0+q1);rTM=(1/q0-ep/q1)/(1/q0+ep/q1)
    aTE=-(1-rTE*rTE)*rTE;aTM=-(1-rTM*rTM)*rTM
    return phase*(aTE*(te@pol)*te+aTM*(tangent@pol)*tmout)

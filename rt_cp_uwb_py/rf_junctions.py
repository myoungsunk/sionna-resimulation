"""Passive isotropic multi-medium planar junctions, using exp(+j omega t).

This is a constitutive/stratified-wave solver, not Sionna's path producer.
Complex epsilon has nonpositive imaginary part. Fields propagate as exp(-j k z).
The scattering recursion avoids growing exponentials in opaque finite layers.
All amplitudes use tangential electric fields; TM reflection has the opposite
sign to a reflected local-p convention (including Sionna's).
"""
from dataclasses import dataclass
import numpy as np

C0=299792458.0
EPS0=8.8541878128e-12

def epsilon_from_conductivity(epsilon_r,conductivity,frequency_hz):
    if frequency_hz<=0 or conductivity<0 or epsilon_r<=0:
        raise ValueError('PASSIVE_POSITIVE_FREQUENCY_REQUIRED')
    return complex(epsilon_r,-conductivity/(2*np.pi*frequency_hz*EPS0))

def normal_wavenumber(epsilon,tangential_index):
    """Outgoing branch: positive phase normal and non-growing propagation."""
    epsilon=complex(epsilon)
    if not np.isfinite(epsilon) or epsilon.imag>1e-13 or epsilon.real<=0:
        raise ValueError('PASSIVE_DIELECTRIC_REQUIRED')
    q=complex(np.sqrt(epsilon-complex(tangential_index)**2))
    if q.imag>0 or (q.imag==0 and q.real<0):q=-q
    return q

def admittance(epsilon,tangential_index,polarization):
    q=normal_wavenumber(epsilon,tangential_index)
    if abs(q)<1e-14:raise ValueError('EXACT_GRAZING_SINGULARITY')
    if polarization=='TE':return q
    if polarization=='TM':return complex(epsilon)/q
    raise ValueError('POLARIZATION_MUST_BE_TE_OR_TM')

@dataclass(frozen=True)
class Interface:
    reflection: complex
    transmission: complex
    q_incident: complex
    q_transmitted: complex
    y_incident: complex
    y_transmitted: complex

def interface(epsilon_incident,epsilon_transmitted,tangential_index=0.,polarization='TE'):
    yi=admittance(epsilon_incident,tangential_index,polarization)
    yt=admittance(epsilon_transmitted,tangential_index,polarization)
    if abs(yi+yt)<1e-14:raise ValueError('SINGULAR_INTERFACE')
    return Interface((yi-yt)/(yi+yt),2*yi/(yi+yt),normal_wavenumber(epsilon_incident,tangential_index),
        normal_wavenumber(epsilon_transmitted,tangential_index),yi,yt)

def snell_lossless(n_incident,n_transmitted,angle_radians):
    """Real direction for lossless fixtures; lossy directions are not approximated."""
    if n_incident<=0 or n_transmitted<=0 or not 0<=angle_radians<np.pi/2:
        raise ValueError('LOSSLESS_SNELL_INPUT')
    s=n_incident*np.sin(angle_radians)/n_transmitted
    return None if s>1 else float(np.arcsin(s))

def stack(epsilon_media,thickness_m,frequency_hz,tangential_index=0.,polarization='TE'):
    """Coherent arbitrary finite layers between two semi-infinite terminals.

    r is at the entrance; t is at the exit (physical in-medium propagation).
    Power fractions are reported only with a lossless propagating incident
    terminal, avoiding the incident/reflected interference ambiguity in loss.
    The returned complex fields remain valid for absorbing terminals.
    """
    eps=[complex(e) for e in epsilon_media];d=np.asarray(thickness_m,float)
    if len(eps)<2 or len(d)!=len(eps)-2 or np.any(~np.isfinite(d)) or np.any(d<0) or frequency_hz<=0:
        raise ValueError('INVALID_STACK')
    pairs=[interface(a,b,tangential_index,polarization) for a,b in zip(eps[:-1],eps[1:])]
    rr=pairs[-1].reflection;tt=pairs[-1].transmission;k0=2*np.pi*frequency_hz/C0
    for j in range(len(pairs)-2,-1,-1):
        front=pairs[j];p=np.exp(-1j*k0*front.q_transmitted*d[j]);den=1+front.reflection*rr*p*p
        if abs(den)<1e-14:raise ValueError('SINGULAR_STACK')
        tt=front.transmission*p*tt/den
        rr=(front.reflection+rr*p*p)/den
    yi=pairs[0].y_incident;yt=pairs[-1].y_transmitted
    power_allowed=abs(eps[0].imag)<1e-13 and abs(complex(tangential_index).imag)<1e-13 and yi.real>1e-14
    R=float(abs(rr)**2) if power_allowed else None
    T=float(yt.real/yi.real*abs(tt)**2) if power_allowed else None
    A=float(1-R-T) if power_allowed else None
    return {'r':rr,'t':tt,'R':R,'T':T,'A':A,'power_flux_defined':power_allowed,
        'reference_planes':'physical entrance and exit','polarization':polarization,'time_convention':'exp(+j omega t)'}

def snell_tangential_index(epsilon_incident,angle_radians):
    if not 0<=angle_radians<np.pi/2:raise ValueError('ANGLE_RANGE')
    return normal_wavenumber(epsilon_incident,0)*np.sin(angle_radians)

def prism_ray_interval(triangle,normal,thickness,origin,direction,tolerance=1e-10):
    """Exact convex prism clipping along a supplied line; no assumed refraction."""
    tri=np.asarray(triangle,float);n=np.asarray(normal,float);o=np.asarray(origin,float);v=np.asarray(direction,float)
    if thickness<=0 or np.linalg.norm(v)==0:raise ValueError('INVALID_PRISM_RAY')
    n=n/np.linalg.norm(n);planes=[(n,float(n@tri[0])),(-n,float(-n@(tri[0]-n*thickness)))]
    center=tri.mean(0)
    for a,b in zip(tri,np.roll(tri,-1,axis=0)):
        outward=np.cross(b-a,n);outward/=np.linalg.norm(outward)
        if outward@(center-a)>0:outward=-outward
        planes.append((outward,float(outward@a)))
    low,high=-np.inf,np.inf
    for pn,offset in planes:
        den=float(pn@v);num=offset-float(pn@o)
        if abs(den)<1e-14:
            if num < -tolerance:return None
            continue
        t=num/den
        if den>0:high=min(high,t)
        else:low=max(low,t)
    return (low,high) if high-low>tolerance and np.isfinite([low,high]).all() else None

def merge_medium_intervals(intervals,tolerance=1e-9):
    """Union same-material volumes; forbid overlapping distinct media.

    Air gaps are retained. Records are (start,end,material,owner).
    """
    if not intervals:return []
    bounds=sorted({float(x) for row in intervals for x in row[:2]});out=[]
    for lo,hi in zip(bounds,bounds[1:]):
        if hi-lo<=tolerance:continue
        mid=(lo+hi)/2;active=[r for r in intervals if r[0]-tolerance<mid<r[1]+tolerance]
        materials={r[2] for r in active}
        if len(materials)>1:raise ValueError('OVERLAPPING_DISTINCT_MEDIA:'+','.join(sorted(materials)))
        mat=next(iter(materials)) if materials else 'air';owners=sorted({r[3] for r in active})
        if out and out[-1]['material']==mat and abs(out[-1]['end']-lo)<=tolerance:
            out[-1]['end']=hi;out[-1]['owners']=sorted(set(out[-1]['owners']+owners))
        else:out.append({'start':lo,'end':hi,'material':mat,'owners':owners})
    return out

def vector_interface(k_incident,e_incident,epsilon_incident,epsilon_transmitted,normal):
    """3-D Maxwell boundary event with a complex dimensionless wave vector k/k0.

    Tangential complex k is conserved. No real-index substitution is used.
    This returns local plane-wave branches, not a receiver-connected ray path.
    Singular/grazing/ambiguous branches fail instead of being silently accepted.
    """
    k=np.asarray(k_incident,complex);e=np.asarray(e_incident,complex);n=np.asarray(normal,float)
    if k.shape!=(3,) or e.shape!=(3,) or n.shape!=(3,) or not np.isfinite([*k,*e,*n]).all() or np.linalg.norm(n)==0:
        raise ValueError('INVALID_VECTOR_INTERFACE')
    n=n/np.linalg.norm(n);scale=max(1.,abs(epsilon_incident),np.linalg.norm(k)**2)
    if abs(k@k-epsilon_incident)>1e-9*scale or abs(k@e)>1e-9*max(1.,np.linalg.norm(k)*np.linalg.norm(e)):
        raise ValueError('INCIDENT_MAXWELL_CONSTRAINT')
    # Validate passivity before selecting outgoing roots.
    normal_wavenumber(epsilon_incident,0);normal_wavenumber(epsilon_transmitted,0)
    kn=k@n
    if kn.real<=1e-12:raise ValueError('INCIDENT_DIRECTION_OR_GRAZING')
    tangent=k-kn*n
    qt=complex(np.sqrt(complex(epsilon_transmitted)-tangent@tangent))
    if qt.imag>0 or (qt.imag==0 and qt.real<0):qt=-qt
    kr=tangent-kn*n;kt=tangent+qt*n
    axis=np.eye(3)[np.argmin(abs(n))];u=np.cross(n,axis);u/=np.linalg.norm(u);v=np.cross(n,u)
    def modes(wave):
        s=np.cross(n,wave)
        if np.linalg.norm(s)<1e-12:s=u.astype(complex)
        s=s/np.linalg.norm(s);p=np.cross(wave,s);p=p/np.linalg.norm(p)
        return np.column_stack([s,p])
    er=modes(kr);et=modes(kt);hr=np.column_stack([np.cross(kr,er[:,i]) for i in range(2)]);ht=np.column_stack([np.cross(kt,et[:,i]) for i in range(2)])
    hi=np.cross(k,e);proj=np.array([u,v])
    matrix=np.block([[proj@er,-proj@et],[proj@hr,-proj@ht]]);rhs=-np.concatenate([proj@e,proj@hi])
    if np.linalg.cond(matrix)>1e12:raise ValueError('SINGULAR_VECTOR_INTERFACE')
    coeff=np.linalg.solve(matrix,rhs);eref=er@coeff[:2];etrans=et@coeff[2:];href=np.cross(kr,eref);htrans=np.cross(kt,etrans)
    flux_in=float(np.real(np.cross(e+eref,np.conj(hi+href)))@n)
    flux_out=float(np.real(np.cross(etrans,np.conj(htrans)))@n)
    residual=float(max(np.max(abs(proj@(e+eref-etrans))),np.max(abs(proj@(hi+href-htrans)))))
    if flux_out<-1e-9 or abs(flux_in-flux_out)>1e-8*max(1.,abs(flux_in)):
        raise ValueError('OUTGOING_FLUX_BRANCH_NOT_SUPPORTED')
    return {'k_reflected':kr,'k_transmitted':kt,'e_reflected':eref,'e_transmitted':etrans,
        'normal_flux_incident_plus_reflected':flux_in,'normal_flux_transmitted':flux_out,
        'boundary_residual':residual,'tangential_k_residual':float(np.max(abs(proj@(kt-k))))}

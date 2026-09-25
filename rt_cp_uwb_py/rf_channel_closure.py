"""Bounded numerical recovery and independent slab checks; no admission bypass."""
import numpy as np
from .rf_volume_channel import ray_tube_spreading, STEPS, CONVERGENCE_RTOL
from .channel import ifft_to_cir


def planar_reflection_spreading(scene, path, frequency_hz, epsilon):
    """Shrink a local derivative stencil, preserving visibility and tolerances."""
    if any(c != 'R' for c in path['choices']):
        raise ValueError('AIR_PLANAR_REFLECTION_ONLY')
    failures = []
    recoverable = {'RAY_TUBE_FINAL_SEGMENT_OCCLUDED', 'RAY_TUBE_TOPOLOGY_CHANGED',
                   'RAY_TUBE_INTERFACE_PLANE_CHANGED', 'RAY_TUBE_STEP_CONVERGENCE_FAILED'}
    for exponent in range(13):
        try:
            result = ray_tube_spreading(scene,path,frequency_hz,epsilon,
                                       angular_steps=tuple(h/2**exponent for h in STEPS))
            length = sum(np.linalg.norm(b-a) for a,b in zip(np.asarray(path['points'])[:-1],np.asarray(path['points'])[1:]))
            error = abs(result['amplitude_per_m']*length-1)
            if error > CONVERGENCE_RTOL:
                raise ValueError('PLANAR_IMAGE_SPREADING_MISMATCH')
            return dict(result, image_reference_per_m=1/length,
                        image_relative_error=float(error), rejected_stencils=failures)
        except ValueError as exc:
            if str(exc) not in recoverable: raise
            failures.append(dict(exponent=exponent,reason=str(exc)))
    raise ValueError('LOCAL_STENCIL_NOT_ESTABLISHED')


def slab_reflection_check(epsilon, frequency_hz, thickness_m, sine):
    """Air/slab/air plane waves: echo series versus characteristic matrix.

    Tangential electric TE/TM amplitudes; exp(+jwt), passive epsilon imag<=0.
    This is NOT finite-body point-source spreading or antenna qualification.
    """
    if not (0 <= sine < 1 and thickness_m > 0 and frequency_hz > 0) or complex(epsilon).imag > 0:
        raise ValueError('PASSIVE_PROPAGATING_SLAB_REQUIRED')
    q0=np.sqrt(1-sine*sine); q1=np.sqrt(complex(epsilon)-sine*sine)
    delta=2*np.pi*frequency_hz/299792458.*q1*thickness_m
    z=np.exp(-2j*delta); results={}
    for name,y0,y1 in [('TE',q0,q1),('TM',1/q0,epsilon/q1)]:
        r=(y0-y1)/(y0+y1)
        first=(1-r*r)*(-r)*z
        total=r*(1-z)/(1-r*r*z)
        transmission=(1-r*r)*np.exp(-1j*delta)/(1-r*r*z)
        c=np.cos(delta); s=np.sin(delta)
        admittance=(1j*y1*s+c*y0)/(c+1j*s*y0/y1)
        matrix=(y0-admittance)/(y0+admittance)
        results[name]=dict(first_internal_return=first,total_reflection=total,
                           matrix_reflection=matrix,absolute_error=float(abs(total-matrix)),
                           outgoing_power=float(abs(total)**2+abs(transmission)**2))
    return results


def contribution_cir(h, frequencies):
    """Transform explicitly partial contributions; never infer missing paths=0."""
    frequencies=np.asarray(frequencies,float); h=np.asarray(h,complex)
    if frequencies.ndim != 1 or len(frequencies)<2 or not np.isfinite(frequencies).all() or np.any(np.diff(frequencies)<=0):
        raise ValueError('STRICTLY_INCREASING_FINITE_FREQUENCIES_REQUIRED')
    if h.ndim < 1 or h.shape[0] != len(frequencies) or not np.isfinite(h).all():
        raise ValueError('FINITE_FREQUENCY_FIRST_CHANNEL_REQUIRED')
    cir,time=ifft_to_cir(np.moveaxis(h,0,-1),frequencies,'hann')
    return np.moveaxis(cir,-1,0),time

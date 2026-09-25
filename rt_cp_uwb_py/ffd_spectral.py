"""Explicit complex spectral interpolation; no historical loader mutation."""
import numpy as np
from scipy.interpolate import CubicSpline

MODEL_ID='ffd_complex_cubic_spline_v1'


def interpolate_complex_frequency(frequencies, fields, requested):
    """Interpolate real and imaginary field components jointly on frequency axis 0.

    Uses not-a-knot cubic splines. This preserves source nodes but is only a
    candidate until domain-specific heldout and phase/CIR gates pass.
    """
    f=np.asarray(frequencies,dtype=float)
    x=np.asarray(requested,dtype=float)
    e=np.asarray(fields,dtype=complex)
    if f.ndim!=1 or len(f)<4 or e.ndim<1 or e.shape[0]!=len(f):
        raise ValueError('spectral shape or insufficient support')
    if not np.isfinite(f).all() or not np.isfinite(x).all() or not np.isfinite(e).all() or np.any(np.diff(f)<=0):
        raise ValueError('invalid spectral values')
    if np.any(x<f[0]) or np.any(x>f[-1]):
        raise ValueError('FFD extrapolation forbidden')
    scale=f[-1]-f[0]
    return CubicSpline((f-f[0])/scale,e,axis=0,extrapolate=False)((x-f[0])/scale)

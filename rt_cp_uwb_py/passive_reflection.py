"""Opt-in passive completion of the historical phenomenological Jones model.

J_new = J_old / max(1, ||J_old||_2). This is the least uniform attenuation
that makes the reflection operator contractive, preserving relative complex
entries and any existing reciprocity symmetry. It is not a measured material
model or a completion of transmission/scattering energy balance.
"""
from contextlib import contextmanager
from threading import Lock
import numpy as np
from . import core, channel

MODEL_ID = 'passive_uniform_jones_v1'
_LEGACY = core.jones_reflection
_LOCK = Lock()


def contract_reflection(matrices):
    """Return new (...,2,2) matrices and per-matrix positive attenuation."""
    value = np.asarray(matrices, dtype=np.complex128)
    if value.ndim < 2 or value.shape[-2:] != (2, 2):
        raise ValueError('expected (...,2,2) Jones matrices')
    if not np.isfinite(value).all():
        raise ValueError('nonfinite Jones matrix')
    largest = np.linalg.svd(value, compute_uv=False)[..., 0]
    # One outward ULP protects against rounding; it is not a fitted tolerance.
    divisor = np.where(largest > 1., np.nextafter(largest, np.inf), 1.)
    scale = 1. / divisor
    return value * scale[..., None, None], scale


def passive_jones_reflection(material, theta_i, freqs_hz):
    old = _LEGACY(material, theta_i, freqs_hz)
    new, _ = contract_reflection(np.moveaxis(old, -1, 0))
    return np.moveaxis(new, 0, -1)


@contextmanager
def passive_channel_runtime():
    """Process-local adapter for native channel.build_channel/path_jones APIs.

    Do not combine with FE convention patches or use simultaneous threads.
    Caller must record MODEL_ID; historical input seals are not engine approval.
    """
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError('passive reflection runtime already active')
    old_core, old_channel = core.jones_reflection, channel.jones_reflection
    try:
        if old_core is not _LEGACY or old_channel is not _LEGACY:
            raise RuntimeError('conflicting Jones runtime binding')
        core.jones_reflection = channel.jones_reflection = passive_jones_reflection
        yield
    finally:
        core.jones_reflection, channel.jones_reflection = old_core, old_channel
        _LOCK.release()

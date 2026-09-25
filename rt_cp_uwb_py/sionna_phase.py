"""Explicit R-only Sionna coefficient/delay boundary for corrected producers."""
import numpy as np
from .specular_delay import refined_delay, propagation_phase


def buffer_delays(buffer, tx, rx, surfaces, specular_code):
    """Keep internal coefficient order; reject unsupported interactions."""
    count = int(buffer.buffer_size)
    depth = int(buffer.max_depth)
    if not 0 <= depth <= 3:
        raise ValueError('R-only adapter requires max_depth <= 3')
    delays, keys = [], []
    vertices = [np.asarray(buffer.get_vertex(k, True).numpy()).T
                for k in range(1, depth + 1)]
    events = [np.asarray(buffer.get_interaction_type(k, True).numpy()).ravel()
              for k in range(1, depth + 1)]
    for index in range(count):
        hits, ended = [], False
        for point, event in zip(vertices, events):
            code = int(event[index])
            if code == 0:
                ended = True
            elif ended or code != int(specular_code):
                raise ValueError('Non-specular or noncontiguous interaction')
            else:
                hits.append(point[index])
        delay, sequence = refined_delay(tx, rx, hits, surfaces)
        delays.append(delay); keys.append(sequence)
    if len({tuple(k) for k in keys}) != count:
        raise ValueError('Duplicate specular path identity')
    return np.asarray(delays, dtype=np.float64), keys


def coherent_path_sum(coefficients, frequency_hz, delays_s):
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    delays = np.asarray(delays_s, dtype=np.float64)
    if coefficients.ndim == 0 or delays.ndim != 1 or coefficients.shape[-1] != len(delays):
        raise ValueError('Coefficient/delay path count mismatch')
    if not np.isfinite(coefficients).all() or not np.isfinite(delays).all():
        raise ValueError('Nonfinite RF input')
    return np.sum(coefficients * propagation_phase(frequency_hz, delays), axis=-1)

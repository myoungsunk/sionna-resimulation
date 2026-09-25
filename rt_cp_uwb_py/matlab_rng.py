from __future__ import annotations

import math
from functools import lru_cache

import numpy as np


_TWO_POW_53 = 9007199254740992.0
_TWO_POW_26 = 67108864.0
_ZIGGURAT_N = 256
_ZIGGURAT_R = 3.654152885361009


@lru_cache(maxsize=1)
def _normal_ziggurat_breakpoints() -> np.ndarray:
    # Breakpoints for MATLAB's current 256-section normal ziggurat.
    # z[0] is zero and z[-1] is the start of the infinite tail.
    z = np.zeros(_ZIGGURAT_N, dtype=float)
    z[-1] = _ZIGGURAT_R
    area = _ZIGGURAT_R * math.exp(-0.5 * _ZIGGURAT_R * _ZIGGURAT_R)
    area += math.sqrt(math.pi / 2.0) * math.erfc(_ZIGGURAT_R / math.sqrt(2.0))
    for idx in range(_ZIGGURAT_N - 2, -1, -1):
        y = area / z[idx + 1] + math.exp(-0.5 * z[idx + 1] * z[idx + 1])
        z[idx] = math.sqrt(max(0.0, -2.0 * math.log(min(y, 1.0))))
    z[0] = 0.0
    return z


def _uniform53_and_section(rng: np.random.RandomState) -> tuple[float, int]:
    words = rng.randint(0, 2**32, size=2, dtype=np.uint32)
    a = int(words[0])
    b = int(words[1])
    u = (((a >> 5) * _TWO_POW_26) + (b >> 6)) / _TWO_POW_53
    return float(u), int(b >> 24)


def _uniform53(rng: np.random.RandomState) -> float:
    return _uniform53_and_section(rng)[0]


def matlab_mt19937_randn(seed: int, size: int | tuple[int, ...]) -> np.ndarray:
    """Generate MATLAB RandStream('mt19937ar') Ziggurat randn samples.

    The returned array is filled in MATLAB column-major order for non-scalar
    shapes.  This is intentionally narrow: it covers the deterministic local
    stream used by +sweep/injectSnr.m.
    """

    shape = (int(size),) if isinstance(size, (int, np.integer)) else tuple(int(x) for x in size)
    n = int(np.prod(shape))
    rng = np.random.RandomState(int(seed) % (2**32 - 1) or 1)
    z = _normal_ziggurat_breakpoints()
    f = np.exp(-0.5 * z * z)
    out = np.empty(n, dtype=float)
    produced = 0

    while produced < n:
        u01, section = _uniform53_and_section(rng)
        u = 2.0 * u01 - 1.0
        sign = -1.0 if u < 0.0 else 1.0
        if section < _ZIGGURAT_N - 1:
            upper = float(z[section + 1])
            lower = float(z[section])
            x = abs(u) * upper
            if x < lower:
                out[produced] = sign * x
                produced += 1
                continue
            y = float(f[section + 1] + _uniform53(rng) * (f[section] - f[section + 1]))
            if y < math.exp(-0.5 * x * x):
                out[produced] = sign * x
                produced += 1
            continue

        upper = float(z[-1])
        lower = float(z[-2])
        x = abs(u) * upper
        if x < lower:
            out[produced] = sign * x
            produced += 1
            continue
        while True:
            u1 = max(_uniform53(rng), np.finfo(float).tiny)
            u2 = max(_uniform53(rng), np.finfo(float).tiny)
            tail_x = -math.log(u1) / upper
            tail_y = -math.log(u2)
            if 2.0 * tail_y > tail_x * tail_x:
                out[produced] = sign * (upper + tail_x)
                produced += 1
                break

    return out.reshape(shape, order="F")

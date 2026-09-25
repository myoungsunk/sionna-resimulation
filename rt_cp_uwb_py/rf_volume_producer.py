"""Bounded TX/RX shooting through explicit volume states.

Output fields are propagated plane-wave fields, NOT spherical-wave channel
coefficients. Ray-tube spreading, caustics, antennas and CIR admission remain
separate gates. Failed shots are evidence of search failure, not absent paths.
"""
from itertools import product
import numpy as np
from scipy.optimize import least_squares
from .rf_junctions import C0


def _unit(v):
    v = np.asarray(v, float)
    if v.shape != (3,) or not np.isfinite(v).all() or np.linalg.norm(v) < 1e-14:
        raise ValueError('INVALID_DIRECTION')
    return v / np.linalg.norm(v)


def _basis(direction):
    u = _unit(np.cross(direction, np.eye(3)[np.argmin(abs(direction))]))
    return u, np.cross(direction, u)


def _energy(k, e):
    return _unit(np.real(np.cross(e, np.conj(np.cross(k, e)))))


def _air_endpoint(scene, point):
    for prism in scene.prisms:
        if all(n@point <= offset+scene.tolerance for n,offset in prism.planes()):
            raise ValueError('ENDPOINT_IN_VOLUME_OR_ON_BOUNDARY')
    for surface in scene.ideal_surfaces:
        tri=np.asarray(surface.triangle,float)
        normal=_unit(np.cross(tri[1]-tri[0],tri[2]-tri[0]))
        if abs(normal@(point-tri[0])) > scene.tolerance:
            continue
        uv=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),point-tri[0],rcond=None)[0]
        if min(uv) >= -scene.tolerance and sum(uv) <= 1+scene.tolerance:
            raise ValueError('ENDPOINT_ON_IDEAL_BOUNDARY')


def connect_branch(scene, tx, rx, frequency_hz, epsilon, choices, seed,
                   polarization=(0, 1, 0), tolerance_m=1e-7, max_nfev=40):
    """Solve two launch angles for a specified R/T word; air endpoints only.

    Every trial re-queries finite boundaries and transports complex k and E.
    The final segment is checked for visibility; no straight-through shortcut.
    """
    tx = np.asarray(tx, float); rx = np.asarray(rx, float)
    if tx.shape != (3,) or rx.shape != (3,) or not np.isfinite([tx, rx]).all():
        raise ValueError('INVALID_ENDPOINT')
    if frequency_hz <= 0 or not np.isfinite(frequency_hz) or tolerance_m <= 0:
        raise ValueError('INVALID_FREQUENCY_OR_TOLERANCE')
    if np.linalg.norm(rx-tx) <= tolerance_m:
        raise ValueError('COINCIDENT_ENDPOINTS')
    if abs(epsilon('air', frequency_hz)-1) > 1e-12:
        raise ValueError('AIR_ENDPOINT_CONTRACT')
    _air_endpoint(scene,tx); _air_endpoint(scene,rx)
    if any(c not in ('R', 'T') for c in choices):
        raise ValueError('BRANCH_MUST_BE_R_OR_T')
    seed = _unit(seed); u, v = _basis(seed)
    pol = np.asarray(polarization, complex)
    if pol.shape != (3,) or not np.isfinite(pol).all():
        raise ValueError('INVALID_POLARIZATION')

    def shot(x):
        direction = _unit(seed + x[0]*u + x[1]*v)
        e = pol - direction*(direction@pol)
        if np.linalg.norm(e) < 1e-12:
            raise ValueError('POLARIZATION_NULL')
        e /= np.linalg.norm(e)
        state = scene.evaluate_branch(tx, direction, e, 'air', frequency_hz, epsilon, choices)
        if len(state['events']) != len(choices):
            raise ValueError('BRANCH_TERMINATED_BEFORE_REQUESTED_DEPTH')
        d = _energy(state['wavevector'], state['electric_field'])
        distance = float((rx-state['position'])@d)
        miss = state['position'] + distance*d - rx
        return state, d, distance, miss, direction

    errors = []
    def residual(x):
        try:
            return shot(x)[3]
        except ValueError as exc:
            errors.append(str(exc))
            return np.full(3, 1e6)

    fit = least_squares(residual, [0., 0.], max_nfev=max_nfev,
                        ftol=1e-12, xtol=1e-12, gtol=1e-12)
    state, direction, distance, miss, launch = shot(fit.x)
    if np.linalg.norm(miss) > tolerance_m or distance <= tolerance_m:
        raise ValueError('RECEIVER_CONNECTION_NOT_FOUND')
    if state['material'] != 'air':
        raise ValueError('RECEIVER_NOT_IN_AIR')
    hit = scene.next_boundary(state['position'], direction, state['material'])
    if hit is not None and hit['distance_m'] <= distance+tolerance_m:
        raise ValueError('FINAL_SEGMENT_OCCLUDED_OR_RX_ON_BOUNDARY')
    delta = rx-state['position']
    phase = np.exp(-1j*2*np.pi*frequency_hz/C0*(state['wavevector']@delta))
    points = [tx, *[e['point'] for e in state['events']], rx]
    return {
        'choices': ''.join(choices), 'events': state['events'], 'points': points,
        'launch_direction': launch, 'arrival_energy_direction': direction,
        'receiver_material': state['material'], 'receiver_wavevector': state['wavevector'],
        'receiver_plane_wave_field': state['electric_field']*phase,
        'final_segment_phase': phase, 'connection_error_m': float(np.linalg.norm(miss)),
        'geometric_length_m': sum(float(np.linalg.norm(b-a)) for a,b in zip(points, points[1:])),
        'optimizer_evaluations': fit.nfev, 'trial_errors': sorted(set(errors)),
        'channel_coefficient_admitted': False,
    }


def generate_paths(scene, tx, rx, frequency_hz, epsilon, *, max_events=3,
                   seeds=None, polarization=(0, 1, 0), max_shots=256,
                   tolerance_m=1e-7):
    """Enumerate bounded R/T words and shoot each from deterministic seeds.

    Depth counts physical interfaces, unlike a collapsed native slab event.
    Search budget exhaustion and all rejected shots are returned explicitly.
    This function never asserts completeness, even when the budget suffices.
    """
    if not isinstance(max_events, int) or not 0 <= max_events <= 12:
        raise ValueError('MAX_EVENTS_OUT_OF_RANGE')
    if not isinstance(max_shots, int) or max_shots < 1:
        raise ValueError('INVALID_SHOT_BUDGET')
    direct = _unit(np.asarray(rx)-np.asarray(tx))
    directions = [direct] if seeds is None else [direct, *[_unit(s) for s in seeds]]
    if seeds is None:
        directions += [s*axis for axis in np.eye(3) for s in (-1, 1)]
    words = [w for depth in range(max_events+1) for w in product('RT', repeat=depth)]
    paths = []; rejected = []; attempted = 0
    planned = len(words)*len(directions)
    for word in words:
        for direction in directions:
            if attempted >= max_shots:
                break
            attempted += 1
            try:
                path = connect_branch(scene, tx, rx, frequency_hz, epsilon, word,
                                      direction, polarization, tolerance_m)
                duplicate = any(old['choices'] == path['choices'] and
                    all(np.linalg.norm(a-b) <= tolerance_m for a,b in zip(old['points'],path['points']))
                    for old in paths)
                if not duplicate:
                    paths.append(path)
            except ValueError as exc:
                rejected.append({'choices': ''.join(word), 'seed': direction,
                                 'reason': str(exc)})
        if attempted >= max_shots:
            break
    return {'paths': paths, 'rejected_shots': rejected, 'attempted_shots': attempted,
            'planned_shots': planned, 'budget_exhausted': attempted < planned,
            'max_physical_interface_events': max_events, 'complete': False,
            'production_admission': False, 'channel_coefficient_admitted': False,
            'status': 'CONNECTED_VOLUME_PATHS_DEVELOPMENT_ONLY' if paths else 'NO_CONNECTION_ESTABLISHED'}


def channel_coefficients(result):
    """Prevent accidental adoption by the old spherical-wave/CIR consumer."""
    raise ValueError('VOLUME_SPREADING_AND_CHANNEL_QUALIFICATION_REQUIRED')

"""Geometry-only producer helpers; actual antenna envelope remains unqualified.

This additive module leaves the earlier development snapshot untouched.
"""
import hashlib
import math
import random


SETTINGS = {
    'schema': 1, 'seed_namespace': 'C1_C3_GEOMETRY_PRODUCER_20260913_V1',
    'max_attempts': 256, 'dt_s': .1, 'epsilon_m': 1e-8,
    'low_speed_m_s': 1e-4, 'yaw_step_rad': math.pi/4,
    'orientation': 'continuous_commanded_heading_tracking; low-speed hold',
    'initial_yaw': 'first non-low-speed displacement heading; zero if stationary',
    'yaw_interpolation': 'linear_unwrapped_between_frames',
    'position_interpolation': 'linear_between_frames',
    'differentiation': 'forward; last backward',
    'envelope_radius_m': 0., 'envelope_status': 'POINT_ONLY_PHYSICAL_ENVELOPE_HOLD',
    'trajectory_retry': 'whole 500-frame affine XY transform; no frame deletion',
    'retry_scale_fraction': [.25, .65], 'tag_wall_margin_m': .55,
    'D5': 'HOLD', 'production_ready': False,
}


def random_for(key, attempt):
    data = f"{SETTINGS['seed_namespace']}|{key}|{attempt}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(data).digest(), 'big'))


def commanded_orientation(points, g):
    """Explicit orientation policy, not an exact tangent or a motor model.

    No changes to positions. Slew-limited heading is separately reported from
    target tangent, so orientation lag cannot be hidden from downstream users.
    """
    dt = SETTINGS['dt_s']
    velocity = [g.mul(g.sub(b,a), 1/dt) for a,b in zip(points, points[1:])]
    if not velocity: raise ValueError('SHORT_TRAJECTORY')
    velocity.append(velocity[-1])
    initial = next((math.atan2(v[1],v[0]) for v in velocity if math.hypot(v[0],v[1]) > SETTINGS['low_speed_m_s']), 0.)
    yaw, errors, previous = [], [], initial
    for v in velocity:
        delta = 0.
        if math.hypot(v[0], v[1]) > SETTINGS['low_speed_m_s']:
            target = math.atan2(v[1],v[0])
            delta = math.atan2(math.sin(target-previous), math.cos(target-previous))
            # Deterministic positive turn for the ambiguous exact pi reversal.
            if abs(abs(delta)-math.pi) < 1e-12: delta = math.pi
            step = max(-SETTINGS['yaw_step_rad'], min(SETTINGS['yaw_step_rad'], delta))
            previous += step
            delta -= step
        yaw.append(previous)
        errors.append(delta)
    return dict(velocity=velocity, yaw_unwrapped_rad=yaw, tangent_error_rad=errors)


def position_gate(points, anchors, size, solids, g):
    for p in list(points)+list(anchors):
        g.vec(p)
        if not all(g.EPS < x < h-g.EPS for x,h in zip(p,size)): raise ValueError('ENDPOINT_ROOM_BOUNDARY')
        if not g.clear(p,p,solids): raise ValueError('ENDPOINT_SOLID_COLLISION')
    for a,b in zip(points, points[1:]):
        if not g.clear(a,b,solids): raise ValueError('SWEPT_SOLID_COLLISION')
    if any(g.length(g.sub(a,p)) <= g.EPS for a in anchors for p in points):
        raise ValueError('COINCIDENT_ENDPOINTS')


def transformed_points(original, size, key, attempt):
    if attempt == 0: return original
    rng = random_for(key, attempt)
    low = [min(p[i] for p in original) for i in range(2)]
    high = [max(p[i] for p in original) for i in range(2)]
    ranges = [high[i]-low[i] for i in range(2)]
    lengths = [(size[i]-1.1)*rng.uniform(*SETTINGS['retry_scale_fraction']) for i in range(2)]
    starts = [rng.uniform(.55, size[i]-.55-lengths[i]) for i in range(2)]
    return [[starts[i]+((p[i]-low[i])/ranges[i] if ranges[i]>1e-10 else .5)*lengths[i] for i in range(2)]+[p[2]] for p in original]


def select_panel(tx, points, anchors, condition, size, solids, g):
    representative = 62 if len(points)==125 else 0
    rejected = []
    for index,p in enumerate(g.candidate_panels(tx, points[representative], condition)):
        try:
            if any(not all(g.EPS < x < h-g.EPS for x,h in zip(c,size)) for c in g.panel_corners(p)):
                raise ValueError('PANEL_ROOM_BOUNDARY')
            if any(g.panel_box_overlap(p,*box) for box in solids): raise ValueError('PANEL_SOLID_COLLISION')
            if any(g.surface_distance(x,p) <= g.EPS for x in list(anchors)+list(points)):
                raise ValueError('PANEL_ENDPOINT_COLLISION')
            if any(g.panel_hit(a,b,p) for a,b in zip(points,points[1:])): raise ValueError('PANEL_SWEPT_COLLISION')
            rx = points[representative]
            if condition == 'side_reflector_present':
                if not g.clear(tx,rx,solids) or g.panel_hit(tx,rx,p) or g.reflection_point(tx,rx,p,solids) is None:
                    raise ValueError('REFERENCE_SIDE_GEOMETRY')
            elif not g.panel_hit(tx,rx,p,interior=True): raise ValueError('REFERENCE_BLOCKAGE')
            return p, rejected
        except ValueError as error:
            rejected.append(dict(candidate=index,reason=str(error)))
    raise ValueError('PANEL_CANDIDATES_EXHAUSTED:'+str(rejected))


def link_truth(tx, rx, panel, solids, g):
    blocked = not g.clear(tx,rx,solids) or (panel is not None and g.panel_hit(tx,rx,panel))
    return dict(los_clear=not blocked, los_blocked=bool(blocked),
                panel_specular_path_geometrically_valid=None if panel is None else g.reflection_point(tx,rx,panel,solids) is not None,
                metal_surface_distance_m=None,
                geometry_truth_status='POINT_GEOMETRY_ONLY_ENVELOPE_HOLD')

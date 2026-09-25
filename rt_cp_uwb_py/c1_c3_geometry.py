"""RF-free geometry primitives. Development gates, not campaign admission.

All boundary contacts count as collisions. AABB obstacles must describe actual
occupied solids; enclosing unrelated surfaces in a box is forbidden upstream.
"""
import math
import hashlib
import json

EPS = 1e-8  # metres; fixed before tests, not fitted to outcomes
LOW_SPEED = 1e-4  # m/s
MAX_YAW_STEP = math.pi / 4  # numerical heading rejection, not robot dynamics


def vec(p):
    if len(p) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in p):
        raise ValueError('INVALID_VECTOR')
    return tuple(p)


def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def add(a, b): return tuple(x+y for x, y in zip(a, b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def length(a): return math.sqrt(dot(a, a))


def unit(a):
    a = vec(a)
    if length(a) <= EPS: raise ValueError('DEGENERATE_DIRECTION')
    return mul(a, 1/length(a))


def panel(center, normal, width, height):
    """Vertical finite panel; dimensions in metres."""
    center, normal = vec(center), unit(normal)
    if abs(normal[2]) > EPS: raise ValueError('NONVERTICAL_PANEL')
    if not all(math.isfinite(x) and x > 2*EPS for x in (width, height)):
        raise ValueError('INVALID_PANEL_SIZE')
    return dict(center=center, normal=normal, u=(-normal[1], normal[0], 0.),
                v=(0., 0., 1.), half=(width/2, height/2))


def segment_box(a, b, lo, hi):
    """Closed segment/slab intersection, including grazing and interior start."""
    a, b, lo, hi = map(vec, (a, b, lo, hi))
    if any(x > y for x, y in zip(lo, hi)): raise ValueError('INVALID_BOX')
    start, end = 0., 1.
    for x, d, lower, upper in zip(a, sub(b, a), lo, hi):
        if abs(d) <= EPS:
            if x < lower-EPS or x > upper+EPS: return False
        else:
            t0, t1 = sorted(((lower-EPS-x)/d, (upper+EPS-x)/d))
            start, end = max(start, t0), min(end, t1)
            if start > end: return False
    return True


def panel_hit(a, b, p, interior=False):
    """Finite intersection; coplanar overlap is collision but not blockage proof."""
    a, b = vec(a), vec(b)
    da, db = dot(sub(a, p['center']), p['normal']), dot(sub(b, p['center']), p['normal'])
    if abs(da-db) <= EPS:
        if abs(da) > EPS or interior: return False
        local = lambda x: (dot(sub(x, p['center']), p['u']), dot(sub(x, p['center']), p['v']), 0.)
        return segment_box(local(a), local(b), (-p['half'][0], -p['half'][1], 0.), (*p['half'], 0.))
    t = da/(da-db)
    if t < 0 or t > 1: return False
    q = sub(add(a, mul(sub(b, a), t)), p['center'])
    margin = -EPS if interior else EPS
    return all(abs(dot(q, axis)) <= half+margin for axis, half in zip((p['u'], p['v']), p['half']))


def clear(a, b, solids):
    return not any(segment_box(a, b, lo, hi) for lo, hi in solids)


def reflection_point(tx, rx, p, solids=()):
    """Image solution with same-side, finite-face and both-leg visibility gates."""
    tx, rx = vec(tx), vec(rx)
    a, b = dot(sub(tx, p['center']), p['normal']), dot(sub(rx, p['center']), p['normal'])
    if a*b <= EPS*EPS: return None
    image = sub(tx, mul(p['normal'], 2*a))
    q = add(image, mul(sub(rx, image), a/(a+b)))
    delta = sub(q, p['center'])
    if any(abs(dot(delta, axis)) >= half-EPS for axis, half in zip((p['u'], p['v']), p['half'])): return None
    if not clear(tx, q, solids) or not clear(q, rx, solids): return None
    return q


def candidate_panels(tx, rx, condition):
    """Fixed ordered geometry-only candidates; caller must retain all rejections.

    Reference anchor is an input, never reselected on candidate failure.
    Panel/room/solid and antenna-volume admission remain mandatory upstream.
    """
    tx, rx = vec(tx), vec(rx)
    heading = unit((rx[0]-tx[0], rx[1]-tx[1], 0.))
    lateral = (-heading[1], heading[0], 0.)
    mid = mul(add(tx, rx), .5)
    if condition == 'occluder_present':
        return [panel(add(tx, mul(sub(rx, tx), f)), heading, .8, 1.7) for f in (.5, .4, .6, .3, .7)]
    if condition == 'side_reflector_present':
        return [panel(add(mid, mul(lateral, d)), lateral, 1.2, 1.5) for d in (1., -1., 1.5, -1.5, 2., -2.)]
    raise ValueError('UNSUPPORTED_CONDITION_OR_D5_HOLD')


def panel_corners(p):
    return [add(p['center'], add(mul(p['u'], a*p['half'][0]), mul(p['v'], b*p['half'][1])))
            for a, b in ((-1, -1), (-1, 1), (1, -1), (1, 1))]


def panel_box_overlap(p, lo, hi):
    """Separating-axis theorem for a vertical rectangle and occupied AABB."""
    lo, hi = vec(lo), vec(hi)
    if any(a > b for a, b in zip(lo, hi)): raise ValueError('INVALID_BOX')
    center, half = mul(add(lo, hi), .5), mul(sub(hi, lo), .5)
    # For a vertical rectangle, these are all distinct nonzero SAT axes.
    for axis in ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.), p['u'], p['normal']):
        radius_p = sum(abs(dot(axis, direction))*h for direction, h in zip((p['u'], p['v']), p['half']))
        radius_b = sum(abs(x)*h for x, h in zip(axis, half))
        if abs(dot(sub(p['center'], center), axis)) > radius_p+radius_b+EPS: return False
    return True


def surface_distance(point, p):
    delta = sub(vec(point), p['center'])
    return math.sqrt(dot(delta, p['normal'])**2 + sum(max(0., abs(dot(delta, axis))-h)**2
                     for axis, h in zip((p['u'], p['v']), p['half'])))


def choose_panel(tx, rx, condition, room_size, solids, endpoints, envelope_radius):
    """Bounded candidate search; return failures for every attempted placement.

    All anchors and the representative tag must be supplied in endpoints.
    C3 still needs the full-phase swept-volume test after this placement.
    """
    if envelope_radius is None or not math.isfinite(envelope_radius) or envelope_radius < 0:
        raise ValueError('ENVELOPE_REQUIRED')
    room_size = vec(room_size)
    if any(x <= 0 for x in room_size): raise ValueError('INVALID_ROOM')
    if not endpoints: raise ValueError('ENDPOINTS_REQUIRED')
    rejected = []
    for i, p in enumerate(candidate_panels(tx, rx, condition)):
        reason = None
        if any(not all(EPS < x < edge-EPS for x, edge in zip(c, room_size)) for c in panel_corners(p)):
            reason = 'PANEL_OUTSIDE_ROOM'
        elif any(panel_box_overlap(p, lo, hi) for lo, hi in solids): reason = 'PANEL_SOLID_COLLISION'
        elif any(surface_distance(e, p) <= envelope_radius+EPS for e in endpoints): reason = 'PANEL_ENDPOINT_COLLISION'
        elif condition == 'side_reflector_present' and (not clear(tx, rx, solids) or panel_hit(tx, rx, p) or reflection_point(tx, rx, p, solids) is None):
            reason = 'REFERENCE_SIDE_GEOMETRY'
        elif condition == 'occluder_present' and not panel_hit(tx, rx, p, interior=True): reason = 'REFERENCE_BLOCKAGE'
        if reason is None: return p, rejected
        rejected.append(dict(candidate=i, reason=reason))
    raise ValueError('CANDIDATES_EXHAUSTED:'+json.dumps(rejected, sort_keys=True))


def shared_scene_hash(anchor_views):
    """Hash complete physical views, excluding only observer-specific identity.

    Caller supplies exactly scene, objects and tag_pose in each view; this avoids
    treating a supplied hash or bounds_valid flag as proof of scene equality.
    """
    if len(anchor_views) != 4: raise ValueError('FOUR_ANCHOR_VIEWS_REQUIRED')
    if any(set(v) != {'scene', 'objects', 'tag_pose'} for v in anchor_views): raise ValueError('VIEW_SCHEMA')
    serialized = [json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False) for v in anchor_views]
    if len(set(serialized)) != 1: raise ValueError('COMMON_SCENE_MISMATCH')
    return hashlib.sha256(serialized[0].encode()).hexdigest()


def validate_fixed_phase(positions, panels, references, condition, anchors, radius):
    """125-frame phase, one room-fixed panel/reference, truth for all anchors.

    Swept sphere is conservatively bounded in the panel's local coordinates.
    This may reject near-corner clearance; it cannot certify a real envelope.
    Scene/structure and room-boundary tests must also pass independently.
    """
    if len(positions) != 125 or len(panels) != 125 or len(references) != 125:
        raise ValueError('PHASE_FRAME_COMPLETENESS')
    if len(anchors) != 4 or len(set(references)) != 1 or references[0] not in range(4):
        raise ValueError('REFERENCE_DRIFT_OR_SCHEMA')
    if any(p != panels[0] for p in panels): raise ValueError('ROOM_FIXED_OBJECT_MOVED')
    if radius is None or not math.isfinite(radius) or radius < 0: raise ValueError('ENVELOPE_REQUIRED')
    p = panels[0]
    local = lambda x: tuple(dot(sub(vec(x), p['center']), axis) for axis in (p['u'], p['v'], p['normal']))
    lo, hi = (-p['half'][0]-radius, -p['half'][1]-radius, -radius), (p['half'][0]+radius, p['half'][1]+radius, radius)
    if any(segment_box(local(a), local(b), lo, hi) for a,b in zip(positions, positions[1:])):
        raise ValueError('TAG_PANEL_SWEPT_COLLISION')
    if any(surface_distance(a,p) <= radius+EPS for a in anchors): raise ValueError('ANCHOR_PANEL_COLLISION')
    if condition not in ('side_reflector_present', 'occluder_present'): raise ValueError('CONDITION_OR_D5_HOLD')
    # Phase-relative 62 maps to global 187 or 312. No all-frame guarantee.
    tx, rx = anchors[references[0]], positions[62]
    if condition == 'occluder_present' and not panel_hit(tx, rx, p, interior=True): raise ValueError('REPRESENTATIVE_BLOCKAGE_MISSING')
    if condition == 'side_reflector_present' and (panel_hit(tx,rx,p) or reflection_point(tx,rx,p) is None):
        raise ValueError('REPRESENTATIVE_REFLECTION_MISSING')
    return [[dict(panel_blocks_los=panel_hit(a,r,p), panel_specular_geometry=reflection_point(a,r,p) is not None)
             for a in anchors] for r in positions]


def trajectory_kinematics(positions, solids, dt=.1, initial_yaw=0., radius=None):
    """Piecewise-linear swept sphere proxy plus finite-difference heading.

    Radius must be explicit; a fixture radius does not qualify the real antenna.
    Abrupt reversals fail; no silent yaw smoothing or trajectory modification.
    """
    if radius is None or not math.isfinite(radius) or radius < 0: raise ValueError('ENVELOPE_REQUIRED')
    if not math.isfinite(dt) or dt <= 0 or not math.isfinite(initial_yaw): raise ValueError('INVALID_TIME_OR_YAW')
    points = list(map(vec, positions))
    if len(points) < 2: raise ValueError('SHORT_TRAJECTORY')
    expanded = [(sub(lo, (radius,)*3), add(hi, (radius,)*3)) for lo, hi in solids]
    if any(not clear(a, b, expanded) for a, b in zip(points, points[1:])):
        raise ValueError('SWEPT_COLLISION')
    velocity = [mul(sub(b, a), 1/dt) for a, b in zip(points, points[1:])]
    velocity.append(velocity[-1])  # forward difference, last backward
    yaw, previous = [], initial_yaw
    for v in velocity:
        if math.hypot(v[0], v[1]) > LOW_SPEED:
            delta = math.atan2(math.sin(math.atan2(v[1], v[0])-previous), math.cos(math.atan2(v[1], v[0])-previous))
            if abs(delta) > MAX_YAW_STEP: raise ValueError('YAW_DISCONTINUITY_REGENERATE_TRAJECTORY')
            previous += delta
        yaw.append(previous)
    return dict(velocity=velocity, yaw_unwrapped_rad=yaw, interpolation='piecewise_linear')

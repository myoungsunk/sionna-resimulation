"""S0: normalise every RF target of the full native Sionna campaign.

Reads the relocated inputs (R), the native geometry manifest (G) and the
STATIC9 pose contract; produces lean target records plus shared pose and
condition-panel tables. No RF arrays are loaded, nothing is moved.

Identity: target_id = sha256 of the canonical JSON of IDENTITY_KEYS, with
absent keys written as explicit null. Never derived from list index or
coordinates.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .g2_full_panels import panel_material_spec, panel_ply, panel_triangles
from .l1_l2_rf_synthesis import historical_mount_frames

L_FAMILIES = ('L1', 'L1multi', 'L2static', 'L2multi')
COMMON_FAMILIES = ('C1_static', 'C1_multi', 'C3')
STATIC9_FAMILY = 'STATIC9_NATIVE_OVERLAY'
FAMILY_ORDER = L_FAMILIES + COMMON_FAMILIES + (STATIC9_FAMILY,)
EXPECTED_COUNTS = dict(L1=12000, L1multi=12000, L2static=3000, L2multi=6000, C1_static=6000,
                       C1_multi=6000, C3=120000, STATIC9_NATIVE_OVERLAY=9)
EXPECTED_TOTAL, EXPECTED_SCENES, EXPECTED_FRAMES, EXPECTED_RELOCATED = 165009, 101, 37500, 41
IDENTITY_KEYS = ('family', 'case_id', 'anchor_id', 'epoch_id', 'unit_id', 'frame', 'phase', 'condition_id',
                 'comparison_cell_id', 'sample_index', 'replicate')
CLEARANCE_M = 0.01  # same endpoint clearance used by the relocation POST_AUDIT
IDEAL_SHEETS = ('PEC', 'EPS4_LOSSLESS')  # reflection-only sheets, no volume (rf_volume_inputs)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def identity(**fields):
    unknown = set(fields) - set(IDENTITY_KEYS)
    if unknown:
        raise ValueError('UNKNOWN_IDENTITY_KEYS:' + ','.join(sorted(unknown)))
    return {k: fields.get(k) for k in IDENTITY_KEYS}


def quat_wxyz_to_matrix(q):
    w, x, y, z = (float(v) for v in q)
    n = math.sqrt(w*w + x*x + y*y + z*z)
    if not math.isfinite(n) or abs(n-1) > 1e-9:
        raise ValueError('QUATERNION_NOT_UNIT')
    return [[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
            [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
            [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]]


def check_rotation(m):
    m = np.asarray(m, float)
    if m.shape != (3, 3) or not np.isfinite(m).all():
        raise ValueError('ROTATION_NOT_FINITE_3X3')
    if not np.allclose(m.T@m, np.eye(3), atol=1e-9) or abs(np.linalg.det(m)-1) > 1e-9:
        raise ValueError('ROTATION_NOT_PROPER')
    return m.tolist()


def check_point(p):
    if len(p) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p):
        raise ValueError('ENDPOINT_NOT_FINITE')
    return [float(v) for v in p]


class Registry:
    """Content-addressed table (pose / panel) shared by many targets."""

    def __init__(self):
        self.items = {}

    def add(self, record):
        key = digest(record)[:16]
        if self.items.setdefault(key, record) != record:
            raise ValueError('REGISTRY_KEY_COLLISION')
        return key


def read_frames(path, needed):
    """Stream FRAMES.jsonl; verify every canonical hash; keep needed frames."""
    frames, total, keys = {}, 0, set()
    with Path(path).open(encoding='utf8') as f:
        for line in f:
            row = json.loads(line); total += 1
            key = row['unit_id'], row['frame']
            if key in keys:
                raise ValueError('DUPLICATE_FRAME')
            keys.add(key)
            if digest(row['physical']) != row['canonical_scene_hash']:
                raise ValueError('FRAME_SHA_MISMATCH')
            if key in needed:
                p = row['physical']
                frames[key] = dict(hash=row['canonical_scene_hash'], tag=p['tag_pose'], size=p['scene']['size'],
                                   object=p.get('object'))
    return frames, total


def build_targets(relocated_root, geometry_root, static9_path):
    """Return (targets, poses, panels, census). Raises on any contract breach."""
    R, G = Path(relocated_root), Path(geometry_root)
    poses, panels = Registry(), Registry()
    targets, issues = [], []
    manifest = json.loads((G/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
    mesh_scenes = {s['scene_id'] for s in manifest['scenes']}
    changes = json.loads((R/'CHANGED_LINKS.json').read_text(encoding='utf8'))
    changed = {(c['family'], c['case_id']): c for c in changes}

    def add(record, tx_rot, rx_rot, source):
        record['tx'], record['rx'] = check_point(record['tx']), check_point(record['rx'])
        record['pose_id'] = poses.add(dict(tx_rotation=check_rotation(tx_rot), rx_rotation=check_rotation(rx_rot)))
        record['geometric_range_m'] = float(np.linalg.norm(np.subtract(record['rx'], record['tx'])))
        record['source_sha256'] = digest(source)
        record['target_id'] = digest(record['identity'])
        change = changed.get((record['family'], record['identity']['case_id']))
        record['rx_relocated'] = change is not None
        if change and (record['rx'] != change['new'] or record['scene_id'] != change['scene_id']):
            raise ValueError('RELOCATION_MISMATCH')
        targets.append(record)

    # L families: historical mount frames from the source row (all rows use defaults; see census).
    l_rooms = {}
    for fam in L_FAMILIES:
        doc = json.loads((R/'inputs_v6'/fam/'INPUT.json').read_text(encoding='utf8'))
        for sid, scene in doc['scenes'].items():
            l_rooms.setdefault(sid, scene['size'])
        for row in doc['links']:
            tx_rot, rx_rot = historical_mount_frames(row.get('source_row', {}))
            add(dict(identity=identity(family=fam, case_id=row['case_id'], anchor_id=row['anchor_id'],
                                       epoch_id=row['epoch_id']),
                     family=fam, scene_id=row['scene_id'], tx=row['tx'], rx=row['rx'], condition=row['condition'],
                     frame_ref=None, panel_id=None, room_size=l_rooms[row['scene_id']]),
                tx_rot, rx_rot, row)

    # Common families: bind (unit_id, frame) to FRAMES and build the condition panel.
    common = []
    with (R/'common/LINKS.jsonl').open(encoding='utf8') as f:
        for line in f:
            common.append(json.loads(line))
    frames, frame_total = read_frames(R/'common/FRAMES.jsonl', {(r['unit_id'], r['frame']) for r in common})
    for row in common:
        fr = frames.get((row['unit_id'], row['frame']))
        if fr is None:
            raise ValueError('MISSING_FRAME')
        if fr['tag']['position'] != row['rx'] or fr['hash'] != row['scene_hash']:
            raise ValueError('LINK_FRAME_MISMATCH')
        mount = dict(row, rx_azimuth_deg=math.degrees(fr['tag']['yaw_rad']))
        tx_rot, rx_rot = historical_mount_frames(mount)
        panel_id = None
        if fr['object']:
            obj = fr['object']
            spec = panel_material_spec(obj)
            corners, _ = panel_triangles(obj['panel'])
            panel_id = panels.add(dict(spec={k: v for k, v in spec.items() if k != 'object_id'},
                                       panel=obj['panel']))
        add(dict(identity=identity(family=row['family'], case_id=row['case_id'], anchor_id=row['anchor_id'],
                                   unit_id=row['unit_id'], frame=row['frame'], phase=row['phase'],
                                   condition_id=row['condition_id']),
                 family=row['family'], scene_id=row['room_id'], tx=row['tx'], rx=row['rx'],
                 condition=row['condition_id'], panel_id=panel_id, room_size=fr['size'],
                 frame_ref=dict(unit_id=row['unit_id'], frame=row['frame'], canonical_scene_hash=fr['hash'],
                                object_id=fr['object']['object_id'] if fr['object'] else None)),
            tx_rot, rx_rot, row)

    # STATIC9 open fixtures: explicit wxyz quaternion -> rotation, open scene by contract.
    static9 = json.loads(Path(static9_path).read_text(encoding='utf8'))
    for cell in static9['comparison_cells']:
        for i, s in enumerate(cell['trajectory']['samples']):
            add(dict(identity=identity(family=STATIC9_FAMILY, comparison_cell_id=cell['comparison_cell_id'],
                                       sample_index=i),
                     family=STATIC9_FAMILY, scene_id=cell['comparison_cell_id'], tx=s['tx_position_m'],
                     rx=s['rx_position_m'], condition=cell['comparison_condition']['control_id'],
                     frame_ref=None, panel_id=None, room_size=None),
                quat_wxyz_to_matrix(s['tx_orientation_wxyz']), quat_wxyz_to_matrix(s['rx_orientation_wxyz']), s)

    # Contract checks: counts, uniqueness, scene coverage, relocation, room containment.
    counts = {fam: sum(t['family'] == fam for t in targets) for fam in FAMILY_ORDER}
    ids = [t['target_id'] for t in targets]
    scenes = {t['scene_id'] for t in targets}
    relocated = [t for t in targets if t['rx_relocated']]
    if counts != EXPECTED_COUNTS or len(targets) != EXPECTED_TOTAL:
        issues.append(dict(check='COUNTS', counts=counts))
    if len(set(ids)) != len(ids):
        issues.append(dict(check='DUPLICATE_TARGET_ID', duplicates=len(ids)-len(set(ids))))
    if scenes != mesh_scenes or len(scenes) != EXPECTED_SCENES:
        issues.append(dict(check='SCENE_COVERAGE', missing=sorted(scenes-mesh_scenes),
                           unused=sorted(mesh_scenes-scenes)))
    if frame_total != EXPECTED_FRAMES or len(frames) != EXPECTED_FRAMES:
        issues.append(dict(check='FRAMES', total=frame_total, bound=len(frames)))
    if len(relocated) != EXPECTED_RELOCATED or len(changed) != EXPECTED_RELOCATED:
        issues.append(dict(check='RELOCATED', bound=len(relocated), declared=len(changed)))
    outside = [t['target_id'] for t in targets if t['room_size'] is not None
               and not all(0 < v < s for p in (t['tx'], t['rx']) for v, s in zip(p, t['room_size']))]
    if outside:
        issues.append(dict(check='OUTSIDE_ROOM', targets=outside[:20], count=len(outside)))
    census = dict(targets=len(targets), family_counts=counts, scenes=len(scenes), frames_total=frame_total,
                  frames_bound=len(frames), relocated_rx_rows=len(relocated), poses=len(poses.items),
                  condition_panels=len(panels.items),
                  panel_targets=sum(t['panel_id'] is not None for t in targets),
                  panel_materials={k: sum(p['spec']['kind'] == k for p in panels.items.values())
                                   for k in ('PEC', 'dielectric')},
                  l_mount_semantics='historical_mount_frames(source_row): no boresight/azimuth keys present, '
                                    'so TX boresight -z and RX yaw 0 for all L rows',
                  static9_rotation='explicit wxyz quaternion conversion; contract poses are identity',
                  issues=issues)
    return targets, poses.items, panels.items, census


# ------------------------------------------------------------ clearance vs G
def read_ascii_ply(path):
    lines = Path(path).read_text(encoding='ascii').splitlines()
    nv = int(next(l for l in lines if l.startswith('element vertex')).split()[-1])
    nf = int(next(l for l in lines if l.startswith('element face')).split()[-1])
    start = lines.index('end_header') + 1
    verts = np.array([[float(x) for x in l.split()[:3]] for l in lines[start:start+nv]])
    faces = [[int(x) for x in l.split()[1:]] for l in lines[start+nv:start+nv+nf]]
    tris = [(verts[f[0]], verts[f[i]], verts[f[i+1]]) for f in faces for i in range(1, len(f)-1)]
    return np.array(tris)


def point_triangle_distance(points, tris):
    """Exact min distance from each point (P,3) to a set of triangles (T,3,3)."""
    p = points[:, None, :]
    a, b, c = tris[None, :, 0], tris[None, :, 1], tris[None, :, 2]
    ab, ac, ap = b-a, c-a, p-a
    n = np.cross(ab, ac); nn = np.einsum('...i,...i', n, n)
    # Projection inside the triangle -> plane distance; else nearest edge.
    w = np.cross(ab, ap); u_ = np.cross(ap, ac)
    inside = (np.einsum('...i,...i', w, n) >= 0) & (np.einsum('...i,...i', u_, n) >= 0) & \
             (np.einsum('...i,...i', w, n) + np.einsum('...i,...i', u_, n) <= nn)
    plane = np.abs(np.einsum('...i,...i', ap, n)) / np.sqrt(np.where(nn > 0, nn, 1))

    def seg(s0, s1):
        d = s1-s0; t = np.clip(np.einsum('...i,...i', p-s0, d)/np.maximum(np.einsum('...i,...i', d, d), 1e-300), 0, 1)
        return np.linalg.norm(p-(s0+t[..., None]*d), axis=-1)
    edge = np.minimum(np.minimum(seg(a, b), seg(b, c)), seg(c, a))
    return np.where(inside & (nn > 0), plane, edge).min(axis=1)


def prism_boundary(tris, thickness):
    """Boundary triangles and inward planes of slabs extruded along -n (NEGATIVE_NORMAL).

    Same convention as rf_volume_inputs/VolumePrism: the sheet is the air-side
    face, material occupies [sheet - thickness*n, sheet].
    """
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    n = np.cross(b-a, c-a); n /= np.linalg.norm(n, axis=1)[:, None]
    off = n*thickness
    a2, b2, c2 = a-off, b-off, c-off
    faces = [(a, b, c), (a2, c2, b2)]
    for p0, p1, q0, q1 in ((a, b, a2, b2), (b, c, b2, c2), (c, a, c2, a2)):
        faces += [(p0, q0, q1), (p0, q1, p1)]
    boundary = np.stack([np.stack(f, axis=1) for f in faces], axis=1)  # (T, 8, 3, 3)
    return boundary, n


def inside_prisms(points, tris, n, thickness, tol=1e-12):
    """(P,T) mask: point strictly inside the extruded slab of triangle T."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    p = points[:, None, :]
    h = np.einsum('ptk,tk->pt', p-a[None], n)
    inside = (h < -tol) & (h > -thickness+tol)
    for e0, e1 in ((a, b), (b, c), (c, a)):
        q = np.cross(e1-e0, n)
        centroid = (a+b+c)/3
        q = np.where((np.einsum('tk,tk->t', q, centroid-e0) > 0)[:, None], q, -q)  # point inward
        inside &= np.einsum('ptk,tk->pt', p-e0[None], q) > tol
    return inside


def endpoint_clearance(targets, panels, geometry_root, chunk=512):
    """Signed clearance of every TX/RX to the scene material (negative = inside a slab).

    Slabs: one-sided prisms (NEGATIVE_NORMAL), exactly as the relocation
    POST_AUDIT measured. Ideal PEC/EPS4 sheets: distance to the sheet.
    Condition panels (no geometric extrusion in the native model): distance
    to the sheet minus half the panel thickness, reported separately.
    """
    G = Path(geometry_root)
    manifest = {s['scene_id']: s for s in json.loads((G/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))['scenes']}
    by_scene = {}
    for i, t in enumerate(targets):
        by_scene.setdefault(t['scene_id'], []).append(i)
    violations, worst = [], {}
    for sid, idx in by_scene.items():
        pts = np.array([targets[i][r] for i in idx for r in ('tx', 'rx')])
        uniq, inv = np.unique(pts, axis=0, return_inverse=True)
        clear = np.full(len(uniq), np.inf); owner = np.full(len(uniq), '', dtype=object)
        for m in manifest[sid]['materials']:
            tris = read_ascii_ply(G/m['mesh'])
            for s0 in range(0, len(uniq), chunk):
                q = uniq[s0:s0+chunk]
                if m['material_id'] in IDEAL_SHEETS:
                    d = point_triangle_distance(q, tris)
                else:
                    boundary, n = prism_boundary(tris, m['thickness_m'])
                    d = point_triangle_distance(q, boundary.reshape(-1, 3, 3))
                    d = np.where(inside_prisms(q, tris, n, m['thickness_m']).any(axis=1), -d, d)
                better = d < clear[s0:s0+chunk]
                clear[s0:s0+chunk] = np.where(better, d, clear[s0:s0+chunk])
                owner[s0:s0+chunk] = np.where(better, m['object_name'], owner[s0:s0+chunk])
        clear = clear[inv.reshape(-1)].reshape(-1, 2); owner = owner[inv.reshape(-1)].reshape(-1, 2)
        for k, i in enumerate(idx):
            t = targets[i]
            t['clearance_m'] = [float(v) if math.isfinite(v) else None for v in clear[k]]
            t['clearance_owner'] = [o or None for o in owner[k]]
            t['panel_clearance_m'] = None
            if t['panel_id']:
                corners, faces = panel_triangles(panels[t['panel_id']]['panel'])
                tris = np.array([[corners[j] for j in f] for f in faces])
                th = panels[t['panel_id']]['spec']['thickness_m']
                t['panel_clearance_m'] = [float(v) for v in
                                          point_triangle_distance(np.array([t['tx'], t['rx']]), tris) - th/2]
            values = [v for v in t['clearance_m'] + (t['panel_clearance_m'] or []) if v is not None]
            if t['family'] != STATIC9_FAMILY and values and min(values) < CLEARANCE_M:
                violations.append(dict(target_id=t['target_id'], family=t['family'], scene_id=sid,
                                       rx_relocated=t['rx_relocated'], clearance_m=t['clearance_m'],
                                       owner=t['clearance_owner'], panel_clearance_m=t['panel_clearance_m']))
        finite = clear[np.isfinite(clear)]
        worst[sid] = float(finite.min()) if finite.size else None
    return dict(threshold_m=CLEARANCE_M,
                rule='slabs: signed distance to one-sided NEGATIVE_NORMAL prism; ideal sheets: distance; '
                     'condition panels: sheet distance minus half thickness',
                violations=violations, min_clearance_by_scene=worst)

"""Endpoint relocation overlay (revision R3) for the full native campaign.

Decision 2026-09-27: every TX/RX closer than 1 cm to scene material (native
geometry G, one-sided NEGATIVE_NORMAL slab prisms / ideal sheets) or to its
condition panel is moved with the same placement rule as the 41-row R2
relocation (MOVES.json):

- horizontal only (z unchanged), one of 8 compass directions (4 axes, 4 diagonals);
- shift in whole millimetres, the smallest shift that reaches >= 1 cm clearance;
- ties at the same shift: larger resulting clearance, then fixed direction order;
- candidate must stay strictly inside the room box with >= 1 cm margin, keep
  >= 1 cm from every condition panel referenced by any linked row, and every
  millimetre along the path must stay outside material.

All rows referencing the same (scene, role, coordinate) are updated together.
The 1 cm value is the synthetic placement rule already used; it is not a
physical near-field threshold, and moving to 1 cm does not make the far-field
antenna pattern model valid near metal.

The overlay is applied on top of the R2 inputs at load time; R2 files are not
modified.
"""
import json
import math
from pathlib import Path

import numpy as np

from .g2_full_inputs import (CLEARANCE_M, IDEAL_SHEETS, digest, inside_prisms, point_triangle_distance,
                             prism_boundary, read_ascii_ply)
from .g2_full_panels import panel_triangles

REVISION_ID = 'SIONNA_G2_ENDPOINT_RELOCATION_20260927_R3'
DIAG = math.sqrt(.5)
DIRECTIONS = (('+x', (1., 0.)), ('-x', (-1., 0.)), ('+y', (0., 1.)), ('-y', (0., -1.)),
              ('+x+y', (DIAG, DIAG)), ('+x-y', (DIAG, -DIAG)), ('-x+y', (-DIAG, DIAG)), ('-x-y', (-DIAG, -DIAG)))
MAX_SHIFT_MM = 500


class SceneClearance:
    """Signed clearance of points to one scene's native material (negative = inside a slab)."""

    def __init__(self, geometry_root, scene):
        G = Path(geometry_root)
        self.parts = []
        for m in scene['materials']:
            tris = read_ascii_ply(G/m['mesh'])
            if m['material_id'] in IDEAL_SHEETS:
                self.parts.append((m['object_name'], tris, None, None, None))
            else:
                boundary, n = prism_boundary(tris, m['thickness_m'])
                self.parts.append((m['object_name'], tris, boundary.reshape(-1, 3, 3), n, m['thickness_m']))

    def __call__(self, points):
        points = np.atleast_2d(np.asarray(points, float))
        best = np.full(len(points), np.inf); owner = np.full(len(points), None, dtype=object)
        for name, tris, boundary, n, th in self.parts:
            if boundary is None:
                d = point_triangle_distance(points, tris)
            else:
                d = point_triangle_distance(points, boundary)
                d = np.where(inside_prisms(points, tris, n, th).any(axis=1), -d, d)
            owner = np.where(d < best, name, owner); best = np.minimum(best, d)
        return best, owner


def panel_clearance(points, panels):
    points = np.atleast_2d(np.asarray(points, float))
    best = np.full(len(points), np.inf)
    for p in panels:
        corners, faces = panel_triangles(p['panel'])
        tris = np.array([[corners[j] for j in f] for f in faces])
        best = np.minimum(best, point_triangle_distance(points, tris) - p['spec']['thickness_m']/2)
    return best


def endpoint_groups(targets):
    """(scene, role, coordinate) -> target indices; STATIC9 open fixtures excluded."""
    groups = {}
    for i, t in enumerate(targets):
        if t['family'] == 'STATIC9_NATIVE_OVERLAY':
            continue
        for k, role in enumerate(('tx', 'rx')):
            groups.setdefault((t['scene_id'], role, tuple(t[role])), []).append((i, k))
    return groups


def search_move(point, clear_fn, panels, room_size, threshold=CLEARANCE_M):
    """Smallest whole-mm horizontal move (8 directions) reaching the threshold."""
    point = np.asarray(point, float)
    for mm in range(1, MAX_SHIFT_MM+1):
        passing = []
        for name, (dx, dy) in DIRECTIONS:
            unit = np.array([dx, dy, 0.])
            cand = point + unit*mm/1000.
            if room_size is not None and not all(threshold <= c <= s-threshold for c, s in zip(cand, room_size)):
                continue
            path = point + unit[None, :]*np.arange(1, mm+1)[:, None]/1000.
            scene_path, _ = clear_fn(path)
            if (scene_path <= 0).any():
                continue  # would cross or enter material on the way
            c_scene = scene_path[-1]
            c_panel = panel_clearance(cand, panels)[0] if panels else np.inf
            c = min(c_scene, c_panel)
            if c >= threshold:
                passing.append((c, -[d[0] for d in DIRECTIONS].index(name), name, cand))
        if passing:
            c, _, name, cand = max(passing, key=lambda x: (x[0], x[1]))
            return dict(direction=name, shift_m=mm/1000., after=cand.tolist(), clearance_after_m=float(c))
    raise ValueError('NO_RELOCATION_WITHIN_%d_MM' % MAX_SHIFT_MM)


def plan_relocations(targets, panels, geometry_root, room_sizes):
    """Return the move list for every endpoint group below the clearance threshold.

    room_sizes: target index -> room box size (None for open scenes).
    """
    G = Path(geometry_root)
    manifest = {s['scene_id']: s for s in json.loads((G/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))['scenes']}
    cache, moves = {}, []
    for (sid, role, coord), members in sorted(endpoint_groups(targets).items(), key=lambda kv: repr(kv[0])):
        if sid not in cache:
            cache[sid] = SceneClearance(G, manifest[sid])
        clear_fn = cache[sid]
        linked_panels = [panels[targets[i]['panel_id']] for i, _ in members if targets[i]['panel_id']]
        linked_panels = list({digest(p): p for p in linked_panels}.values())
        before_scene, owner = clear_fn([coord])
        before = min(before_scene[0], panel_clearance([coord], linked_panels)[0] if linked_panels else np.inf)
        if before >= CLEARANCE_M:
            continue
        sizes = {json.dumps(room_sizes[i]) for i, _ in members}
        if len(sizes) != 1:
            raise ValueError('INCONSISTENT_ROOM_SIZE_FOR_ENDPOINT')
        move = search_move(coord, clear_fn, linked_panels, room_sizes[members[0][0]])
        rows = sorted({(targets[i]['family'], targets[i]['identity']['case_id']) for i, _ in members})
        frames = sorted({(targets[i]['frame_ref']['unit_id'], targets[i]['frame_ref']['frame'])
                         for i, _ in members if targets[i]['frame_ref']})
        moves.append(dict(scene_id=sid, role=role, before=list(coord), after=move['after'],
                          shift_m=move['shift_m'], direction=move['direction'], z_unchanged=True,
                          clearance_before_m=float(before), nearest_before=owner[0],
                          clearance_after_m=move['clearance_after_m'], threshold_m=CLEARANCE_M,
                          linked_rows=[dict(family=f, case_id=c) for f, c in rows],
                          linked_frames=[dict(unit_id=u, frame=fr) for u, fr in frames]))
    return moves


def overlay_index(overlay):
    """(family, case_id, role) -> move; raises on conflicting assignments."""
    index = {}
    for move in overlay['moves']:
        for row in move['linked_rows']:
            key = row['family'], row['case_id'], move['role']
            if key in index:
                raise ValueError('ROW_RELOCATED_TWICE')
            index[key] = move
    return index


def relocate_l_row(row, moves):
    """Apply R3 moves to an L INPUT link (fields as updated by R2)."""
    row = json.loads(json.dumps(row))
    for role, move in moves.items():
        if row[role] != move['before']:
            raise ValueError('RELOCATION_BEFORE_MISMATCH')
        row[role] = list(move['after'])
        src = row.get('source_row')
        if src is not None:
            for axis, v in zip('xyz', move['after']):
                src[f'{role}_{axis}_m'] = v
    rng = float(np.linalg.norm(np.subtract(row['rx'], row['tx'])))
    row['true_range_m'] = rng
    if row.get('source_row') is not None:
        row['source_row']['true_dist_m'] = rng
    row['endpoint_relocation'] = dict(revision=REVISION_ID, roles=sorted(moves),
                                      old={r: m['before'] for r, m in moves.items()})
    return row


def frame_moves(overlay):
    """(unit_id, frame) -> RX move for every frame linked to a relocated RX."""
    out = {}
    for move in overlay['moves']:
        if move['role'] != 'rx':
            continue
        for fr in move['linked_frames']:
            key = fr['unit_id'], fr['frame']
            if out.setdefault(key, move) is not move:
                raise ValueError('FRAME_RELOCATED_TWICE')
    return out


def relocate_frame(frame, move):
    """Move the frame tag pose and recompute its canonical hash."""
    frame = json.loads(json.dumps(frame))
    if frame['physical']['tag_pose']['position'] != move['before']:
        raise ValueError('FRAME_TAG_BEFORE_MISMATCH')
    frame['physical']['tag_pose']['position'] = list(move['after'])
    frame['previous_canonical_scene_hash'] = frame['canonical_scene_hash']
    frame['canonical_scene_hash'] = digest(frame['physical'])
    return frame


def relocate_common_row(row, moves, new_scene_hash):
    """Apply R3 moves to a common link, mirroring the R2 rx_relocation record."""
    row = json.loads(json.dumps(row))
    previous_hash = row['scene_hash']
    for role, move in moves.items():
        if row[role] != move['before']:
            raise ValueError('RELOCATION_BEFORE_MISMATCH')
        row[role] = list(move['after'])
    previous = {k: row.get(k) for k in ('geometry_truth_status', 'los_blocked', 'los_clear',
                                         'metal_surface_distance_m', 'panel_specular_path_geometrically_valid')}
    row.update(geometry_truth_status='ENDPOINT_RELOCATED_REQUIRES_RECOMPUTE', los_blocked=None, los_clear=None,
               metal_surface_distance_m=None, panel_specular_path_geometrically_valid=None,
               scene_hash=new_scene_hash,
               endpoint_relocation=dict(revision=REVISION_ID, roles=sorted(moves),
                                        old={r: m['before'] for r, m in moves.items()},
                                        previous_geometry_truth=previous, previous_scene_hash=previous_hash))
    return row

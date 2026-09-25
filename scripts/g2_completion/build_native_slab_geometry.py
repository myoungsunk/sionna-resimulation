"""Additive conversion of the 101-scene envelope into native Sionna slab inputs."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_native_geometry import (
    AREA_TOLERANCE, POSITION_TOLERANCE, basis, clip_coplanar_owners,
    hollow_column_thickness, polygon_from_triangles, read_ply, write_ply,
)

SOURCE = ROOT / 'results/SIONNA_G2_P2_UNIFIED_20260924_01a0d21c_R3'
NATIVE = ROOT / 'results/SIONNA_NATIVE41_20260925_01a0d812'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf8')


def source_triangles(source, lineage):
    meshes = {r['mesh'] for r in lineage['mesh_face_ranges'] if r['mesh']}
    cache = {}
    for name in meshes:
        vertices, faces = read_ply(source / name)
        cache[name] = vertices[faces]
    return {r['wall_id']: cache[r['mesh']][r['first_face']:r['first_face'] + r['face_count']]
            if r['mesh'] else np.empty((0, 3, 3)) for r in lineage['mesh_face_ranges']}


def convert(lineage, actual):
    walls = deepcopy(lineage['walls'])
    byscene, columns = defaultdict(list), defaultdict(list)
    for w in walls:
        byscene[w['scene_id']].append(w)
        if w['source_id'].startswith('surface:') and ':hall_column_' in w['source_id']:
            columns[(w['scene_id'], w['source_id'].split(':')[-1].rsplit('_', 1)[0])].append(w)
    column_decisions = []
    for (scene, name), group in columns.items():
        points = np.concatenate([w['corners'] for w in group])
        # This conversion is intentionally restricted to verified vertical box columns.
        assert len(group) == 4 and all(abs(basis(w['corners'])[1][2][2]) < 1e-10 for w in group)
        assert all(np.max(np.abs(basis(w['corners'])[1][2])) > 1 - 1e-10 for w in group)
        thickness = hollow_column_thickness(points)
        spans = np.ptp(points, axis=0)
        column_decisions.append(dict(scene_id=scene, structure=name, outer_size_m=spans.tolist(),
            original_thickness_m=sorted({w['thickness'] for w in group}),
            selected_panel_thickness_m=thickness, inner_air_size_xy_m=(spans[:2] - 2*thickness).tolist(),
            model='four concrete slab panels with an air cavity; open ends meet floor/ceiling',
            solid_column_equivalence=False, structural_load_capacity_claim=False))
        for w in group:
            w['thickness'] = thickness
            w['native_recipe'] = 'HOLLOW_CONCRETE_COLUMN_PANEL'
    changes, converted = [], {}
    oldwalls = {w['wall_id']: w for w in lineage['walls']}
    for scene_walls in byscene.values():
        owners = [(w['wall_id'], actual[w['wall_id']]) for w in scene_walls
                  if w['source_id'].startswith('surface:')]
        for w in scene_walls:
            wid = w['wall_id']
            old = oldwalls[wid]
            ts = actual[wid]
            cuts = []
            if w['source_id'].startswith('asset:') and len(ts):
                ts, cuts = clip_coplanar_owners(ts, w['corners'], owners)
            if w['material'] == 'PEC':
                w['material'], w['thickness'] = 'metal', .001
                w['native_recipe'] = 'IDEAL_PEC_REPLACED_BY_NATIVE_METAL_SLAB'
            elif w['material'] == 'EPS4_LOSSLESS':
                w['thickness'] = .1  # Explicit native 2.0.1 DEFAULT_THICKNESS, formerly implicit.
                w['native_recipe'] = 'EXPLICIT_NATIVE_EPS4_SLAB'
            w.setdefault('native_recipe', 'SINGLE_PHYSICAL_PLATE' if w['recipe'] == 'UNIFIED_SINGLE_PANEL'
                         else 'HOLLOW_FURNITURE_PANEL' if w['source_id'].startswith('asset:')
                         else 'SINGLE_ARCHITECTURAL_SLAB')
            w['source_recipe'] = w.pop('recipe')
            w['recipe'] = w['native_recipe']
            w['layer_offsets_m'] = [-w['thickness'], 0]
            w['material_side'] = 'REFERENCE_ONLY_NATIVE_SLAB_NO_VOLUME_TRACKING'
            converted[wid] = ts
            if cuts or (old['material'], old['thickness']) != (w['material'], w['thickness']):
                changes.append(dict(scene_id=w['scene_id'], source_id=w['source_id'], wall_id=wid,
                    before_material=old['material'], after_material=w['material'],
                    before_thickness_m=old['thickness'], after_thickness_m=w['thickness'],
                    before_triangles=len(actual[wid]), after_triangles=len(ts),
                    removed_area_m2=sum(c['removed_area_m2'] for c in cuts), owners=cuts,
                    action='ARCHITECTURE_OWNS_CONTACT' if cuts else w['native_recipe']))
    return walls, converted, changes, column_decisions


def audit(walls, actual, original):
    """Readback audit: all new triangles remain on/in original surfaces; unique coplanar ownership."""
    issues, scenes, coverage = [], defaultdict(list), []
    for w in walls:
        ts = actual[w['wall_id']]
        frame = basis(w['corners'])
        poly = polygon_from_triangles(ts, frame)
        before = polygon_from_triangles(original[w['wall_id']], frame)
        if poly.difference(before).area > AREA_TOLERANCE:
            issues.append([w['wall_id'], 'ADDED_GEOMETRY_OUTSIDE_ORIGINAL'])
        if len(ts):
            cross = np.cross(ts[:, 1] - ts[:, 0], ts[:, 2] - ts[:, 0])
            if np.any(cross @ frame[1][2] <= 1e-12):
                issues.append([w['wall_id'], 'WINDING_OR_DEGENERATE'])
            if abs(np.linalg.norm(cross, axis=1).sum()/2 - poly.area) > AREA_TOLERANCE:
                issues.append([w['wall_id'], 'DUPLICATE_TRIANGLES'])
            if np.max(np.abs((ts.reshape(-1, 3) - frame[0]) @ frame[1][2])) > POSITION_TOLERANCE:
                issues.append([w['wall_id'], 'OFF_REFERENCE_PLANE'])
            scenes[w['scene_id']].append((w, ts, poly, frame))
        if w['source_id'].endswith(':floor'):
            if not len(ts) or np.max(np.abs(ts[:, :, 2])) > POSITION_TOLERANCE or w['thickness'] != .2:
                issues.append([w['wall_id'], 'FLOOR_CONTRACT'])
        coverage.append(dict(wall_id=w['wall_id'], before_area_m2=before.area, after_area_m2=poly.area))
    comparisons = 0
    for entries in scenes.values():
        for i, (wa, ta, pa, fa) in enumerate(entries):
            loa, hia = ta.min(axis=(0, 1)), ta.max(axis=(0, 1))
            for wb, tb, pb, fb in entries[i+1:]:
                if np.any(tb.min(axis=(0, 1)) > hia + POSITION_TOLERANCE) or np.any(tb.max(axis=(0, 1)) < loa - POSITION_TOLERANCE):
                    continue
                if abs(fa[1][2] @ fb[1][2]) < 1-1e-10:
                    continue
                if np.max(np.abs((tb.reshape(-1, 3) - fa[0]) @ fa[1][2])) > POSITION_TOLERANCE:
                    continue
                comparisons += 1
                area = pa.intersection(polygon_from_triangles(tb, fa)).area
                if area > AREA_TOLERANCE:
                    issues.append([wa['wall_id'], wb['wall_id'], 'COPLANAR_DUPLICATE', area])
    return dict(status='PASS' if not issues else 'FAIL', issues=issues, walls=len(walls),
                coplanar_pairs_tested=comparisons, coverage=coverage,
                geometry_addition_area_zero=True if not issues else None,
                scope='reference-sheet coverage, winding, ownership and floor; not finite-edge wave accuracy')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=SOURCE)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    out, source = args.out.resolve(), args.source.resolve()
    lineage = read(source/'SOURCE_SURFACE_LINEAGE.json')
    manifest = read(source/'SCENE_MESH_MANIFEST.json')
    original = source_triangles(source, lineage)
    walls, actual, changes, columns = convert(lineage, original)
    plan = dict(scenes=len(manifest['scenes']), columns=len(columns), changed_wall_records=len(changes),
                actions=dict(Counter(c['action'] for c in changes)), moved_instances=0, tx_rx_moved=0,
                full_channel_recalculation=False, pathsolver_calls=0)
    if args.dry_run:
        print(json.dumps(dict(status='DRY_RUN_OK', **plan)))
        return
    if not out.is_relative_to(ROOT/'results'):
        raise ValueError('OUTPUT_MUST_BE_NEW_RESULTS_REVISION')
    out.mkdir(parents=True, exist_ok=False)
    input_paths = [source/n for n in ['SOURCE_SURFACE_LINEAGE.json', 'SCENE_MESH_MANIFEST.json',
                   'PROTOTYPE_DESIGNS.json', 'SOURCE_PART_MAPPING.json', 'COORDINATE_AND_LAYER_CONTRACT.json']]
    for s in manifest['scenes']:
        for m in s['materials']:
            assert sha(source/m['mesh']) == m['sha256']
            input_paths.append(source/m['mesh'])
    input_paths += [NATIVE/'CONFIG.json', NATIVE/'INPUTS.zip', NATIVE/'production_v2/MANIFEST.json']
    inputs = {str(p): sha(p) for p in input_paths}
    native_config = read(NATIVE/'CONFIG.json')
    config = dict(source_root=str(source), output_root=str(out), command=sys.argv,
                  timestamp_utc=datetime.now(timezone.utc).isoformat(), **plan)
    save(out/'RUN_CONFIG.json', config)
    contract = dict(backend='native Sionna RT 2.0.1 RadioMaterial/ITURadioMaterial',
        source='https://nvlabs.github.io/sionna/_modules/sionna/rt/radio_materials/radio_material.html',
        representation='one RF reference sheet per physical slab; no duplicate inner/back boundary',
        floor_top_z_m=0., floor_material_z_m=[-.2, 0.],
        column_model='synthetic hollow concrete panel box; no solid-column equivalence',
        column_thickness_rule='min(0.05 m, minimum horizontal outer span / 4)',
        furniture_model='existing connected hollow panel envelopes; all exterior empty spaces retained',
        contacts='architecture owns coplanar contact; remove only coincident furniture patch',
        edges='native locally planar slab approximation; no volume-union or coupled-junction solver',
        ideal_mappings={'PEC': 'native ITU metal, 0.001 m', 'EPS4_LOSSLESS': 'epsilon_r=4, sigma=0, explicit native default 0.1 m'},
        volume_solver_compatible=False, source_part_count=lineage['source_parts'],
        power_noise_ffd_coordinates='unchanged', g2_pass=False, sealed=False)
    save(out/'MODEL_CONTRACT.json', contract)
    save(out/'COLUMN_DECISIONS.json', columns)
    save(out/'GEOMETRY_CHANGES.json', changes)
    with (out/'GEOMETRY_CHANGES.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in changes[0] if k != 'owners'])
        writer.writeheader()
        writer.writerows({k:v for k,v in c.items() if k != 'owners'} for c in changes)
    new_scenes, ranges = [], []
    for s in manifest['scenes']:
        grouped = defaultdict(list)
        for w in walls:
            if w['scene_id'] == s['scene_id']:
                grouped[(w['material'], w['thickness'])].append(w)
        materials = []
        for (material, thickness), group in sorted(grouped.items()):
            name = material + '_t' + format(thickness, '.8g').replace('.', 'p')
            mesh = 'SIONNA_SCENES/' + s['scene_id'] + '/' + name + '.ply'
            triangles = []
            for w in group:
                ts = actual[w['wall_id']]
                ranges.append(dict(scene_id=s['scene_id'], wall_id=w['wall_id'], source_id=w['source_id'],
                    material=material, thickness=thickness, first_face=len(triangles), face_count=len(ts), mesh=mesh))
                triangles.extend(ts)
            if not triangles:
                for r in ranges:
                    if r['mesh'] == mesh:
                        r['mesh'] = None
                continue
            write_ply(out/mesh, triangles)
            v, f = read_ply(out/mesh)
            materials.append(dict(object_name=name, material_id=material, thickness_m=thickness, mesh=mesh,
                sha256=sha(out/mesh), vertices=len(v), triangles=len(f), bounds_min=v.min(0).tolist(), bounds_max=v.max(0).tolist()))
        new_scenes.append(dict(scene_id=s['scene_id'], source_kind=s['source_kind'], materials=materials,
                               source_parts=s['source_parts'], model='NATIVE_SLAB_SHEETS'))
    save(out/'SCENE_MESH_MANIFEST.json', dict(status='NATIVE_SLAB_GEOMETRY_GENERATED', scenes=new_scenes))
    new_lineage = dict(source_parts=lineage['source_parts'], walls=walls, mesh_face_ranges=ranges,
                       inactive_parts=lineage['inactive_parts'], excluded_internal_walls=lineage['excluded_internal_walls'])
    save(out/'SOURCE_SURFACE_LINEAGE.json', new_lineage)
    mapping = read(source/'SOURCE_PART_MAPPING.json')
    face_counts = {r['wall_id']: r['face_count'] for r in ranges}
    for row in mapping['rows']:
        row['active_native_wall_ids'] = [w for w in row['new_wall_ids'] if face_counts.get(w, 0)]
        if 'COLUMN_CAP' in row['intervention']:
            row['native_disposition'] = 'OPEN_HOLLOW_COLUMN_END_ARCHITECTURAL_OWNER'
    save(out/'SOURCE_PART_MAPPING.json', mapping)
    # Read the emitted files back before auditing, rather than trusting in-memory triangles.
    readback = source_triangles(out, new_lineage)
    check = audit(walls, readback, original)
    save(out/'GEOMETRY_AUDIT.json', check)
    if check['issues']:
        raise ValueError(str(check['issues'][:12]))
    before_scenes = {s['scene_id']: s for s in manifest['scenes']}
    changed_scenes = []
    for s in new_scenes:
        signature = lambda doc: sorted((m['material_id'], m['thickness_m'] or 0, m['sha256']) for m in doc['materials'])
        if signature(s) != signature(before_scenes[s['scene_id']]):
            changed_scenes.append(s['scene_id'])
    affected = [r['link_id'] for r in native_config['rows'] if r['scene_id'] in changed_scenes]
    native_config.update(geometry_root=str(out), model=contract['representation'],
                         geometry_manifest_sha256=sha(out/'SCENE_MESH_MANIFEST.json'),
                         geometry_contract_sha256=sha(out/'MODEL_CONTRACT.json'),
                         source_native_revision=str(NATIVE), channel_status='RECOMPUTE_REQUIRED_FOR_CHANGED_SCENES')
    save(out/'CONFIG.json', native_config)
    save(out/'CHANNEL_INVALIDATION.json', dict(changed_scene_ids=changed_scenes, affected_native41_link_ids=affected,
        old_channels_preserved=True, old_channels_valid_for_new_geometry=False if affected else True,
        recomputation_executed=False, scope='shape conversion; no G2/CIR promotion'))
    # Binding payload consumed by the existing native runtime. FFD banks remain at CONFIG.bank_root.
    with zipfile.ZipFile(out/'INPUTS.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ['CONFIG.json', 'SCENE_MESH_MANIFEST.json', 'MODEL_CONTRACT.json']:
            z.write(out/name, name)
        for s in new_scenes:
            for m in s['materials']:
                z.write(out/m['mesh'], m['mesh'])
        with zipfile.ZipFile(NATIVE/'INPUTS.zip') as oldzip:
            for name in oldzip.namelist():
                if name.startswith('dynamic/'):
                    z.writestr(name, oldzip.read(name))
        runtime = ROOT/'scripts/g2_completion/sionna_native_runtime.py'
        z.write(runtime, runtime.name)
        inputs[str(runtime)] = sha(runtime)
    assert all(sha(p) == h for p,h in inputs.items())
    save(out/'GENERATION_MANIFEST.json', dict(timestamp_utc=config['timestamp_utc'], command=sys.argv,
        config_sha256=sha(out/'RUN_CONFIG.json'), inputs=inputs,
        code={str(p):sha(p) for p in [Path(__file__), ROOT/'rt_cp_uwb_py/g2_native_geometry.py']},
        outputs={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
    summary = dict(status='NATIVE_SLAB_GEOMETRY_LOCAL_PASS', **plan, meshes=sum(len(s['materials']) for s in new_scenes),
        triangles=sum(m['triangles'] for s in new_scenes for m in s['materials']),
        removed_contact_area_m2=sum(c['removed_area_m2'] for c in changes),
        changed_scenes=len(changed_scenes), affected_native41_rows=len(affected),
        runtime_readback='PENDING', g2_pass=False, sealed=False)
    save(out/'STATUS.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()

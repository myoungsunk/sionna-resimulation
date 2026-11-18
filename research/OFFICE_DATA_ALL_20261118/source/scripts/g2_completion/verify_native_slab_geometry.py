"""Independent closure checks for the additive native slab conversion."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_native_geometry import basis, polygon_from_triangles, read_ply


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def triangles(root, lineage):
    meshes = {}
    output = {}
    coverage = {}
    for r in lineage['mesh_face_ranges']:
        name = r['mesh']
        if name and name not in meshes:
            v, f = read_ply(root/name)
            meshes[name] = v[f]
            coverage[name] = np.zeros(len(f), dtype=int)
        if name:
            output[r['wall_id']] = meshes[name][r['first_face']:r['first_face']+r['face_count']]
            coverage[name][r['first_face']:r['first_face']+r['face_count']] += 1
        else:
            output[r['wall_id']] = np.empty((0,3,3))
    assert all(np.all(n == 1) for n in coverage.values()), 'FACE_OWNERSHIP'
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    out = a.out.resolve()
    c = read(out/'RUN_CONFIG.json')
    source = Path(c['source_root'])
    old, new = read(source/'SOURCE_SURFACE_LINEAGE.json'), read(out/'SOURCE_SURFACE_LINEAGE.json')
    before, after = triangles(source,old), triangles(out,new)
    assert set(before) == set(after)
    oldwalls = {w['wall_id']:w for w in old['walls']}
    owners = defaultdict(list)
    for w in old['walls']:
        if w['source_id'].startswith('surface:') and len(before[w['wall_id']]):
            owners[w['scene_id']].append(before[w['wall_id']])
    removed = 0
    area = 0.
    for w in new['walls']:
        wid = w['wall_id']
        assert w['corners'] == oldwalls[wid]['corners'], 'REFERENCE_POSE_CHANGED'
        if np.array_equal(before[wid], after[wid]):
            continue
        assert w['source_id'].startswith('asset:'), 'ARCHITECTURE_GEOMETRY_CHANGED'
        frame = basis(w['corners'])
        original = polygon_from_triangles(before[wid],frame)
        result = polygon_from_triangles(after[wid],frame)
        overlaps = []
        for t in owners[w['scene_id']]:
            if np.max(np.abs((t.reshape(-1,3)-frame[0])@frame[1][2])) <= 1e-6:
                overlaps.append(polygon_from_triangles(t,frame))
        owner = unary_union(overlaps)
        expected = original.difference(owner)
        assert expected.symmetric_difference(result).area < 1e-8, 'NOT_EXACT_CONTACT_SUBTRACTION'
        removed += 1
        area += original.area-result.area
    columns = read(out/'COLUMN_DECISIONS.json')
    groups = defaultdict(list)
    for w in new['walls']:
        if w['recipe'] == 'HOLLOW_CONCRETE_COLUMN_PANEL':
            groups[(w['scene_id'],w['source_id'].split(':')[-1].rsplit('_',1)[0])].append(w)
    assert len(columns) == len(groups) == 72
    for column in columns:
        group = groups[(column['scene_id'],column['structure'])]
        assert len(group) == 4
        points = np.concatenate([w['corners'] for w in group])
        size = np.ptp(points,axis=0)
        t = column['selected_panel_thickness_m']
        assert all(w['material']=='concrete' and w['thickness']==t for w in group)
        assert np.all(size[:2]-2*t >= size[:2]/2-1e-12)
        np.testing.assert_allclose(size[:2]-2*t,column['inner_air_size_xy_m'],atol=1e-12,rtol=0)
    # Each source solid thin panel is represented by exactly one sheet, not front/back surfaces.
    panels = defaultdict(list)
    for w in new['walls']:
        if w['recipe'] == 'SINGLE_PHYSICAL_PLATE':
            panels[(w['scene_id'],w['source_id'])].append(w)
    assert all(len(v)==1 for v in panels.values())
    mapping = read(out/'SOURCE_PART_MAPPING.json')
    oldmapping = read(source/'SOURCE_PART_MAPPING.json')
    keys=lambda m:{(r['scene_id'],r['source_id']) for r in m['rows']}
    assert keys(mapping)==keys(oldmapping) and len(mapping['rows'])==len(oldmapping['rows'])==2383
    config = read(out/'CONFIG.json')
    native = Path(config['source_native_revision'])
    oldconfig = read(native/'CONFIG.json')
    preserved_fields = ['rows','ports','bank_sha256','noise','detector','solver','bank_root']
    assert all(config[k]==oldconfig[k] for k in preserved_fields)
    dynamic=0
    with zipfile.ZipFile(native/'INPUTS.zip') as oldzip, zipfile.ZipFile(out/'INPUTS.zip') as newzip:
        for name in oldzip.namelist():
            if name.startswith('dynamic/'):
                assert oldzip.read(name)==newzip.read(name)
                dynamic+=1
    generated = read(out/'GENERATION_MANIFEST.json')
    assert all(sha(p)==h for p,h in generated['inputs'].items())
    assert all(sha(out/p)==h for p,h in generated['outputs'].items())
    runtime = read(out/'RUNTIME_READBACK.json')
    assert runtime['status']=='PASS_NATIVE_SCENE_READBACK' and not runtime['failures']
    assert runtime['pathsolver_calls']==0 and runtime['scene_count']==101
    assert runtime['source_runtime_sha256']==sha(ROOT/'scripts/g2_completion/sionna_native_runtime.py')
    prototypes=read(source/'PROTOTYPE_DESIGNS.json')['prototypes']
    for proto in prototypes.values():
        for b in proto['boxes']:
            if not b['single_panel']:
                assert np.all(np.array(b['hi'])-b['lo']-2*b['thickness']>0), 'HOLLOW_PANEL_SPACE'
    result=dict(status='PASS_NATIVE_SLAB_GEOMETRY_CLOSURE', scenes=101, source_parts=2383,
        original_reference_planes_preserved=len(new['walls']), exact_contact_subtractions=removed,
        removed_contact_area_m2=area, hollow_columns=72, single_panel_sources=len(panels),
        tx_rx_rows_unchanged=len(config['rows']), dynamic_panels_unchanged=dynamic,
        source_hashes_verified=len(generated['inputs']), generated_hashes_verified=len(generated['outputs']),
        native_runtime_pass=True, material_frequency_checks=runtime['material_frequency_checks'],
        pathsolver_calls=0, full_channel_recalculation=False,
        g2_pass=False, sealed=False, timestamp_utc=datetime.now(timezone.utc).isoformat())
    (out/'INDEPENDENT_VERIFICATION.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()


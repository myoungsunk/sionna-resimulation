"""RF-free check that condition panels bind the decided native materials.

1. Maps every FRAMES.jsonl condition object through panel_material_spec.
2. For representative frames (one dielectric occluder per C family, one of
   each metal condition) loads the real scene meshes and the panel into
   Sionna RT, sets scene.frequency to bins 0/128/256 and reads back the
   material actually bound to the panel object. No PathSolver call.

Usage:
    python scripts/g2_completion/check_condition_panel_binding.py \
        --out results/SIONNA_FULL_RESIM_20260925_01a0d86d/01_local_checks/condition_panel_binding
"""
import argparse
import collections
import datetime
import hashlib
import importlib.metadata
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_panels import (CONTRACT_ID, EPS0, make_panel_material, material_readback,
                                        panel_material_spec, panel_ply)

R = ROOT/'results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2'
G = ROOT/'results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b'
BINS = [0, 128, 256]
FREQ = lambda k: 6250400000. + 1950000.*k


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def census():
    """Map every condition object; pick representative (family, condition) frames."""
    links = {}
    with (R/'common/LINKS.jsonl').open(encoding='utf8') as f:
        for line in f:
            l = json.loads(line)
            links.setdefault((l['unit_id'], l['frame']), (l['family'], l['condition_id'], l['room_id']))
    counts = collections.Counter(); picks = {}
    with (R/'common/FRAMES.jsonl').open(encoding='utf8') as f:
        for line in f:
            r = json.loads(line); obj = r['physical']['object']
            if not obj:
                continue
            spec = panel_material_spec(obj)
            family, condition, room = links[(r['unit_id'], r['frame'])]
            counts[(family, condition, spec['kind'], spec['thickness_m'])] += 1
            wanted = (family, condition) if spec['kind'] == 'dielectric' else ('ANY', condition)
            picks.setdefault(wanted, dict(unit_id=r['unit_id'], frame=r['frame'], family=family,
                                          condition=condition, scene_id=room, object=obj))
    return counts, picks


def bind(rt, mi, pick, manifest, tmp):
    scene = rt.load_scene()
    objects = []
    for item in manifest[pick['scene_id']]['materials']:
        model = item['material_id']
        mat = (rt.RadioMaterial(name='rm_'+item['object_name'], thickness=item['thickness_m'],
                                relative_permittivity=4., conductivity=0.) if model == 'EPS4_LOSSLESS' else
               rt.ITURadioMaterial(name='rm_'+item['object_name'], itu_type='metal' if model == 'PEC' else model,
                                   thickness=.001 if model == 'PEC' else item['thickness_m']))
        objects.append(rt.SceneObject(fname=str(G/item['mesh']), name=item['object_name'], radio_material=mat))
    spec = panel_material_spec(pick['object'])
    ply = Path(tmp)/f"{pick['unit_id']}_{pick['frame']}.ply"
    ply.write_text(panel_ply(pick['object']['panel']), encoding='ascii')
    objects.append(rt.SceneObject(fname=str(ply), name='dynamic_panel',
                                  radio_material=make_panel_material(rt, spec)))
    scene.edit(add=objects)
    bound = scene.objects['dynamic_panel'].radio_material
    readings = []
    for k in BINS:
        scene.frequency = FREQ(k)
        rb = material_readback(bound)
        rb.update(bin=k, frequency_hz=FREQ(k))
        if spec['kind'] == 'dielectric':
            rb['tan_delta_implied'] = rb['conductivity_s_m']/(2*math.pi*FREQ(k)*EPS0*rb['relative_permittivity'])
        readings.append(rb)
    bbox = scene.objects['dynamic_panel'].mi_mesh.bbox()
    if spec['kind'] == 'dielectric':
        ok = all(math.isclose(r['relative_permittivity'], 12., rel_tol=1e-6)
                 and math.isclose(r['thickness_m'], .020, rel_tol=1e-6)
                 and math.isclose(r['tan_delta_implied'], .35, rel_tol=1e-5) for r in readings)
        ok &= readings[0]['conductivity_s_m'] < readings[-1]['conductivity_s_m']
    else:
        ok = all(r['type'] == 'ITURadioMaterial' and math.isclose(r['thickness_m'], .001, rel_tol=1e-6)
                 for r in readings)
    return dict(pick={k: v for k, v in pick.items() if k != 'object'}, object_id=pick['object']['object_id'],
                source_material=pick['object']['material'], spec=spec, readback=readings,
                panel_bbox=[list(map(float, bbox.min)), list(map(float, bbox.max))],
                scene_objects=len(scene.objects), passed=bool(ok))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out if a.out.is_absolute() else ROOT/a.out
    out.mkdir(parents=True, exist_ok=True)
    counts, picks = census()
    import mitsuba as mi
    mi.set_variant('llvm_ad_mono_polarized')
    import sionna.rt as rt
    manifest = {s['scene_id']: s for s in json.loads((G/'SCENE_MESH_MANIFEST.json').read_text())['scenes']}
    with tempfile.TemporaryDirectory() as tmp:
        cases = [bind(rt, mi, p, manifest, tmp) for _, p in sorted(picks.items())]
    for c in cases:
        r = c['readback']
        print(f"{'PASS' if c['passed'] else 'FAIL'} {c['pick']['family']:9} {c['pick']['condition']:24} "
              f"{r[0]['type']:16} eps={r[0]['relative_permittivity']:.3g} d={r[0]['thickness_m']:.4f} m "
              f"sigma={[round(x['conductivity_s_m'], 4) for x in r]}")
    by_kind = collections.Counter()
    for (fam, cond, kind, th), n in counts.items():
        by_kind[(kind, th)] += n
    status = 'PASS' if all(c['passed'] for c in cases) and set(by_kind) == {('PEC', .001), ('dielectric', .020)} \
        else 'FAIL'
    receipt = dict(status=status, contract_id=CONTRACT_ID, pathsolver_calls=0,
                   timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv,
                   versions={n: importlib.metadata.version(n) for n in ('sionna-rt', 'mitsuba', 'drjit')},
                   frames_mapped={f'{k[0]}/{k[1]}/{k[2]}/{k[3]}m': n for k, n in sorted(counts.items())},
                   frames_by_material={f'{k}/{t}m': n for (k, t), n in sorted(by_kind.items())},
                   representative_cases=cases,
                   code_sha256={p: sha(ROOT/p) for p in ('rt_cp_uwb_py/g2_full_panels.py',
                                                        'scripts/g2_completion/check_condition_panel_binding.py')},
                   inputs_sha256={p: sha(ROOT/p) for p in (
                       str((R/'common/LINKS.jsonl').relative_to(ROOT)),
                       str((R/'common/FRAMES.jsonl').relative_to(ROOT)),
                       str((G/'SCENE_MESH_MANIFEST.json').relative_to(ROOT)))})
    (out/'BINDING_RECEIPT.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print(json.dumps(dict(status=status, frames_by_material=receipt['frames_by_material'])))
    sys.exit(0 if status == 'PASS' else 1)


if __name__ == '__main__':
    main()

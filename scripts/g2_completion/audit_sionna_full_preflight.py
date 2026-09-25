"""Read-only pre-simulation audit for SIONNA_FULL_RESIM_20260925_01a0d86d.

Runs before S0/S1. Makes no RF/PathSolver calls and never modifies inputs.
Writes AUDIT.json (+ a config/provenance MANIFEST.json) into --out.

Usage:
    python scripts/g2_completion/audit_sionna_full_preflight.py \
        --out results/SIONNA_FULL_RESIM_20260925_01a0d86d/00_preflight_audit
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

R = ROOT/'results/SIONNA_G2_RX_RELOCATED_20260924_01a0d320_R2'
G = ROOT/'results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b'
B = ROOT/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank'
C = ROOT/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json'
CAMPAIGN = ROOT/'results/SIONNA_FULL_RESIM_20260925_01a0d86d'
STATIC9 = ROOT/'inputs/reference/COMMON_ENVIRONMENT_POSE_CONTRACT.json'
FILE_LIST = ROOT/'reports/common/SIONNA_FULL_RESIM_GITHUB_FILES_20260925_01a0d87a.csv'
WINDOWS_ROOT = 'D:\\codex\\raytracing_modules\\rt_cp_uwb\\'

L_FAMILIES = ['L1', 'L1multi', 'L2static', 'L2multi']
PORTS = ['RHCP', 'LHCP', 'LP_X', 'LP_Y', 'LP_plus45', 'LP_minus45']
EXPECTED = dict(L1=12000, L1multi=12000, L2static=3000, L2multi=6000,
                C1_static=6000, C1_multi=6000, C3=120000, STATIC9_NATIVE_OVERLAY=9)
EXPECTED_TOTAL, EXPECTED_SCENES, EXPECTED_FRAMES = 165009, 101, 37500
N_BINS, N_ARMS = 257, 3
F0, DF = 6250400000., 1950000.
# ITU-R P.2040 validity ranges (GHz) as implemented by Sionna RT ITURadioMaterial.
ITU_RANGES_GHZ = dict(concrete=(1, 100), brick=(1, 10), plasterboard=(1, 100), wood=(0.001, 100),
                      glass=(0.1, 100), ceiling_board=(1, 100), chipboard=(1, 100),
                      floorboard=(50, 100), metal=(1, 100), marble=(1, 60))
NATIVE_EXTRA_MATERIALS = {'EPS4_LOSSLESS', 'PEC'}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def lfs_pointer(data):
    """Return (oid, size) for a Git LFS pointer file, else None."""
    if not data.startswith(b'version https://git-lfs'):
        return None
    oid = re.search(rb'oid sha256:([0-9a-f]{64})', data).group(1).decode()
    size = int(re.search(rb'size (\d+)', data).group(1))
    return oid, size


def classify_digest(path, expected_sha, expected_bytes=None):
    """Compare a checkout file with a digest recorded on Windows.

    EXACT: identical bytes. CRLF_ONLY: identical after LF->CRLF conversion
    (git text normalisation). LFS_POINTER: pointer oid matches, content absent.
    MISMATCH: content differs. ABSENT: no file.
    """
    path = Path(path)
    if not path.is_file():
        return 'ABSENT'
    data = path.read_bytes()
    pointer = lfs_pointer(data)
    if pointer:
        return 'LFS_POINTER' if pointer[0] == expected_sha else 'MISMATCH'
    if sha_bytes(data) == expected_sha and (expected_bytes is None or len(data) == int(expected_bytes)):
        return 'EXACT'
    crlf = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    if sha_bytes(crlf) == expected_sha:
        return 'CRLF_ONLY'
    return 'MISMATCH'


def windows_to_repo(path):
    if not path.startswith(WINDOWS_ROOT):
        return None
    return ROOT/path[len(WINDOWS_ROOT):].replace('\\', '/')


class Audit:
    def __init__(self):
        self.checks = []

    def add(self, cid, area, status, summary, **detail):
        assert status in ('PASS', 'FAIL', 'WARN', 'INFO', 'BLOCKER')
        self.checks.append(dict(id=cid, area=area, status=status, summary=summary, detail=detail))
        print(f'[{status:7}] {cid} {summary}', flush=True)


# ---------------------------------------------------------------- A. delivery
def audit_delivery(audit):
    rows = list(csv.DictReader(FILE_LIST.open(encoding='utf-8-sig')))
    tally = collections.Counter(); mismatches = []; absent = []
    for r in rows:
        if r['delivery'] == 'IMPLEMENT_THEN_GITHUB':
            state = 'ABSENT' if not (ROOT/r['repository_or_data_path']).exists() else 'PRESENT'
            tally[('IMPLEMENT_THEN_GITHUB', state)] += 1
            continue
        state = classify_digest(ROOT/r['repository_or_data_path'], r['sha256'], r['bytes'])
        tally[(r['delivery'], state)] += 1
        if state == 'MISMATCH':
            mismatches.append(r['repository_or_data_path'])
        if state == 'ABSENT':
            absent.append(r['repository_or_data_path'])
    summary = {f'{d}:{s}': n for (d, s), n in sorted(tally.items())}
    audit.add('A1', 'delivery', 'PASS' if not mismatches else 'FAIL',
              f'upload list {len(rows)} rows vs checkout; content mismatches={len(mismatches)}',
              tally=summary, mismatches=mismatches)
    audit.add('A2', 'delivery', 'BLOCKER' if absent else 'PASS',
              f'listed data files absent from their declared path: {len(absent)}', absent=absent)
    code_drift = [m for m in mismatches if m.endswith('.py')]
    audit.add('A6', 'delivery', 'BLOCKER' if code_drift else 'PASS',
              f'code differs from the Windows digest in the upload list/plan snapshot: {code_drift}',
              note='sionna_native_runtime.py SHA is part of the verification chain '
                   '(RUNTIME_READBACK source_runtime_sha256=9dc7dfa5...); reconcile with the Windows '
                   'original before staging')
    root_banks = sorted(p.name for p in ROOT.glob('*_bank.npz'))
    audit.add('A3', 'delivery', 'WARN' if root_banks else 'PASS',
              'FFD bank NPZ files are at repository root, not at bank/ path used by CONFIG/runners',
              root_files=root_banks, expected_dir=str(B.relative_to(ROOT)))
    dupes = []
    for p in ROOT.glob('SIONNA_FULL_RESIM_*'):
        twin = ROOT/'reports/common'/p.name
        if twin.exists():
            dupes.append(dict(root=p.name, identical=sha_file(p) == sha_file(twin)))
    audit.add('A4', 'delivery', 'WARN' if dupes else 'PASS',
              'plan/upload documents duplicated at repo root and reports/common (living log may diverge)',
              duplicates=dupes)
    missing_pkg = [n for n in ('requirements-sionna-full-local.txt', 'runtime/sionna-full/RUNTIME_LOCK.json')
                   if not (ROOT/n).exists()]
    audit.add('A5', 'delivery', 'WARN' if missing_pkg else 'PASS',
              'no dependency lock for local checks (numpy/scipy/scikit-learn/shapely/pytest needed)',
              missing=missing_pkg)


# ----------------------------------------------------------- B. plan snapshot
def audit_snapshot(audit):
    snap = json.loads((CAMPAIGN/'PLAN_INPUT_SNAPSHOT.json').read_text(encoding='utf8'))
    result = {}
    for src, digest in snap['inputs_sha256'].items():
        local = windows_to_repo(src)
        if local is None:
            local = STATIC9 if src.endswith('COMMON_ENVIRONMENT_POSE_CONTRACT.json') else None
        state = classify_digest(local, digest) if local else 'OUTSIDE_REPO'
        if state == 'ABSENT' and local and local.name.endswith('_bank.npz'):
            state = 'AT_ROOT:' + classify_digest(ROOT/local.name, digest)
        result[src] = state
    counts = collections.Counter(result.values())
    bad = {k: v for k, v in result.items() if v in ('MISMATCH', 'ABSENT', 'OUTSIDE_REPO')}
    audit.add('B1', 'snapshot', 'FAIL' if bad else 'PASS',
              f'PLAN_INPUT_SNAPSHOT {len(result)} source SHAs vs checkout: {dict(counts)}', drift=bad)
    arithmetic = sum(EXPECTED.values())
    calls = arithmetic*N_BINS*N_ARMS
    ok = (snap['total_planned_rows'] == arithmetic == EXPECTED_TOTAL
          and snap['baseline_pathsolver_calls'] == calls and snap['family_counts'] == EXPECTED)
    audit.add('B2', 'snapshot', 'PASS' if ok else 'FAIL',
              f'plan arithmetic: {arithmetic} targets x {N_BINS} bins x {N_ARMS} arms = {calls:,} PathSolver calls')
    return snap


# --------------------------------------------------------------- C. targets
def load_targets():
    """Stream all RF targets as light dicts (no RF arrays)."""
    targets = []; l_scenes = {}
    for fam in L_FAMILIES:
        doc = json.loads((R/'inputs_v6'/fam/'INPUT.json').read_text(encoding='utf8'))
        for sid, scene in doc['scenes'].items():
            l_scenes.setdefault(sid, scene)
        for row in doc['links']:
            targets.append(dict(family=fam, key=(fam, row['case_id']), scene_id=row['scene_id'],
                                tx=row['tx'], rx=row['rx'], tag_orientation_deg=row.get('tag_orientation_deg'),
                                source_row=row.get('source_row', {})))
    with (R/'common/LINKS.jsonl').open(encoding='utf8') as f:
        for line in f:
            row = json.loads(line)
            targets.append(dict(family=row['family'], key=(row['family'], row['case_id']),
                                scene_id=row['room_id'], tx=row['tx'], rx=row['rx'],
                                unit_id=row['unit_id'], frame=row['frame'], scene_hash=row['scene_hash'],
                                rx_azimuth_deg=row['rx_azimuth_deg'], relocated='rx_relocation' in row))
    static9 = json.loads(STATIC9.read_text(encoding='utf8'))
    for cell in static9['comparison_cells']:
        for i, s in enumerate(cell['trajectory']['samples']):
            targets.append(dict(family='STATIC9_NATIVE_OVERLAY', key=('STATIC9', cell['comparison_cell_id'], i),
                                scene_id=cell['comparison_cell_id'], tx=s['tx_position_m'], rx=s['rx_position_m'],
                                tx_q=s['tx_orientation_wxyz'], rx_q=s['rx_orientation_wxyz']))
    return targets, l_scenes


def load_frames(needed):
    frames = {}; total = 0; hash_bad = 0; keys = set()
    with (R/'common/FRAMES.jsonl').open(encoding='utf8') as f:
        for line in f:
            row = json.loads(line); total += 1
            key = row['unit_id'], row['frame']; keys.add(key)
            digest = sha_bytes(json.dumps(row['physical'], sort_keys=True, separators=(',', ':'),
                                          ensure_ascii=False).encode())
            hash_bad += digest != row['canonical_scene_hash']
            if key in needed:
                phys = row['physical']
                frames[key] = dict(hash=row['canonical_scene_hash'], tag=phys['tag_pose'],
                                   size=phys['scene']['size'], object=phys.get('object'))
    return frames, total, len(keys), hash_bad


def audit_targets(audit):
    targets, l_scenes = load_targets()
    counts = collections.Counter(t['family'] for t in targets)
    keys = [t['key'] for t in targets]
    audit.add('C1', 'targets', 'PASS' if dict(counts) == EXPECTED and len(targets) == EXPECTED_TOTAL else 'FAIL',
              f'target census {len(targets)} (expected {EXPECTED_TOTAL})', family_counts=dict(counts))
    dup = len(keys) - len(set(keys))
    audit.add('C2', 'targets', 'PASS' if dup == 0 else 'FAIL', f'duplicate (family, case_id) keys: {dup}')

    manifest = json.loads((G/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
    mesh_scenes = {s['scene_id'] for s in manifest['scenes']}
    used = {t['scene_id'] for t in targets}
    audit.add('C3', 'targets', 'PASS' if used == mesh_scenes and len(used) == EXPECTED_SCENES else 'FAIL',
              f'scene union {len(used)} vs geometry manifest {len(mesh_scenes)}',
              missing_geometry=sorted(used - mesh_scenes), unused_geometry=sorted(mesh_scenes - used))

    finite_bad = [t['key'] for t in targets
                  if not all(math.isfinite(v) for v in list(t['tx'])+list(t['rx'])) or len(t['tx']) != 3 or len(t['rx']) != 3]
    ranges = np.array([np.linalg.norm(np.subtract(t['rx'], t['tx'])) for t in targets])
    audit.add('C4', 'targets', 'PASS' if not finite_bad and ranges.min() > 0.05 else 'FAIL',
              f'coordinates finite; TX-RX range min={ranges.min():.4f} m max={ranges.max():.3f} m',
              non_finite=[list(map(str, k)) for k in finite_bad[:20]])

    # Common links <-> frames
    common = [t for t in targets if 'unit_id' in t]
    needed = {(t['unit_id'], t['frame']) for t in common}
    frames, total, unique_frames, hash_bad = load_frames(needed)
    missing = needed - set(frames)
    audit.add('C5', 'frames', 'PASS' if total == unique_frames == EXPECTED_FRAMES and hash_bad == 0 else 'FAIL',
              f'FRAMES.jsonl rows={total} unique (unit_id,frame)={unique_frames} canonical-hash mismatches={hash_bad}')
    rx_bad = hash_link_bad = yaw_bad = 0
    for t in common:
        fr = frames.get((t['unit_id'], t['frame']))
        if fr is None:
            continue
        rx_bad += fr['tag']['position'] != t['rx']
        hash_link_bad += fr['hash'] != t['scene_hash']
        yaw_bad += abs(((math.degrees(fr['tag']['yaw_rad']) - t['rx_azimuth_deg'] + 180) % 360) - 180) > 1e-6
    audit.add('C6', 'frames', 'PASS' if not (missing or rx_bad or hash_link_bad) else 'FAIL',
              f'{len(common)} common links -> {len(needed)} frames: missing={len(missing)} '
              f'rx!=tag_pose={rx_bad} scene_hash mismatch={hash_link_bad}')
    audit.add('C7', 'frames', 'PASS' if yaw_bad == 0 else 'WARN',
              f'link rx_azimuth_deg vs frame tag_pose.yaw_rad (mod 360) disagreements: {yaw_bad}',
              note='rx_azimuth_deg is unwrapped (values up to 720 deg); runtime must use the frame yaw')
    dyn_links = [t for t in common if frames.get((t['unit_id'], t['frame']), {}).get('object')]
    dyn_frames = {(t['unit_id'], t['frame']) for t in dyn_links}
    kinds = collections.Counter(frames[k]['object']['material']['kind'] for k in dyn_frames)
    materials = collections.Counter(
        (m['kind'], m['name'], m['eps_r'], m['tan_delta'], m.get('thickness_m'))
        for m in (frames[k]['object']['material'] for k in dyn_frames))
    non_pec = sum(n for k, n in kinds.items() if k != 'PEC')
    audit.add('C8', 'frames', 'PASS' if not non_pec else 'BLOCKER',
              f'dynamic panels required: {len(dyn_links)} links over {len(dyn_frames)} distinct frames '
              f'(41-row payload carried 12); object kinds={dict(kinds)}',
              materials=[dict(kind=k, name=n, eps_r=e, tan_delta=t, thickness_m=th, frames=c)
                         for (k, n, e, t, th), c in materials.items()],
              note='runtime make_scene() binds every dynamic_panel to ITU metal 1 mm and RelocatedInputs '
                   'raises UNSUPPORTED_DYNAMIC_OBJECT for non-PEC; dielectric panels carry no thickness, '
                   'so a native RadioMaterial (eps_r, sigma from tan_delta, thickness) needs a user decision')

    # Room containment: L via INPUT scenes, C via frame scene size. STATIC9 is open by contract.
    outside = []
    for t in targets:
        if t['family'] in L_FAMILIES:
            size = l_scenes[t['scene_id']]['size']
        elif 'unit_id' in t:
            size = frames[(t['unit_id'], t['frame'])]['size']
        else:
            continue
        for role in ('tx', 'rx'):
            if not all(0 < v < s for v, s in zip(t[role], size)):
                outside.append([*map(str, t['key']), role])
    audit.add('C9', 'targets', 'PASS' if not outside else 'FAIL',
              f'TX/RX strictly inside room bounding box (closed scenes): violations={len(outside)}',
              examples=outside[:20])

    # 41 relocated rows
    changes = json.loads((R/'CHANGED_LINKS.json').read_text(encoding='utf8'))
    by_key = {t['key']: t for t in targets}
    reloc_bad = [f"{c['family']}_{c['case_id']}" for c in changes
                 if by_key.get((c['family'], c['case_id']), {}).get('rx') != c['new']
                 or by_key[(c['family'], c['case_id'])]['scene_id'] != c['scene_id']]
    still_old = [f"{c['family']}_{c['case_id']}" for c in changes
                 if by_key.get((c['family'], c['case_id']), {}).get('rx') == c['old']]
    marked = sum(t.get('relocated', False) for t in common)
    audit.add('C10', 'relocation', 'PASS' if len(changes) == 41 and not reloc_bad and not still_old else 'FAIL',
              f'CHANGED_LINKS {len(changes)} rows carry new RX in R inputs; mismatches={len(reloc_bad)} '
              f'old-coordinate rows={len(still_old)}; common rows tagged rx_relocation={marked}')
    cfg = json.loads(C.read_text(encoding='utf8'))
    cfg_rows = {r['link_id']: r for r in cfg['rows']}
    cfg_bad = [k for k, r in cfg_rows.items()
               if by_key.get(tuple([k.rsplit('_', 1)[0], int(k.rsplit('_', 1)[1])]), {}).get('rx') != r['rx']]
    audit.add('C11', 'relocation', 'PASS' if len(cfg_rows) == 41 and not cfg_bad else 'FAIL',
              f'NATIVE41 CONFIG rows ({len(cfg_rows)}) agree with R RX coordinates; mismatches={len(cfg_bad)}')
    return targets, frames, cfg


# ------------------------------------------------------------------ D. poses
def audit_poses(audit, targets, frames, cfg):
    from rt_cp_uwb_py.l1_l2_rf_synthesis import historical_mount_frames

    def check(m):
        m = np.asarray(m, float)
        return np.allclose(m.T@m, np.eye(3), atol=1e-9) and abs(np.linalg.det(m)-1) < 1e-9

    l_rows = [t for t in targets if t['family'] in L_FAMILIES]
    tag = collections.Counter(str(t['tag_orientation_deg']) for t in l_rows)
    pose_keys = sorted({k for t in l_rows for k in t['source_row']
                        if k.startswith('tx_boresight_') or k in ('rx_azimuth_deg', 'rx_tilt_deg')})
    l_rot = {json.dumps([np.round(m, 12).tolist() for m in historical_mount_frames(t['source_row'])])
             for t in l_rows[:: max(1, len(l_rows)//2000)]}
    audit.add('D1', 'pose', 'INFO',
              f'L families: tag_orientation_deg values={dict(tag)}; mount keys in source_row={pose_keys or "none"}; '
              f'distinct (tx,rx) frames in sample={len(l_rot)}',
              note='all L rows fall back to default TX boresight -z and RX yaw 0; confirm this is the intended '
                   'historical mount semantics before S0')
    yaws = sorted({round(frames[(t['unit_id'], t['frame'])]['tag']['yaw_rad'], 12)
                   for t in targets if 'unit_id' in t})
    bad = 0
    for y in yaws:
        tx_r, rx_r = historical_mount_frames({'rx_azimuth_deg': math.degrees(y)})
        bad += not (check(tx_r) and check(rx_r))
    ref = cfg['rows'][0]
    tx0, rx0 = historical_mount_frames({})
    ref_ok = np.allclose(tx0, ref['tx_rotation']) and np.allclose(rx0, ref['rx_rotation'])
    audit.add('D2', 'pose', 'PASS' if bad == 0 and ref_ok else 'FAIL',
              f'rotation matrices orthonormal det=+1 over {len(yaws)} distinct common yaws: failures={bad}; '
              f'reproduces NATIVE41 CONFIG row-0 rotations={ref_ok}')
    qs = [t[k] for t in targets if t['family'] == 'STATIC9_NATIVE_OVERLAY' for k in ('tx_q', 'rx_q')]
    norms = [abs(np.linalg.norm(q)-1) for q in qs]
    identity = sum(q == [1.0, 0.0, 0.0, 0.0] for q in qs)
    audit.add('D3', 'pose', 'PASS' if max(norms) < 1e-9 else 'FAIL',
              f'STATIC9 quaternions (wxyz) unit-norm: max|n-1|={max(norms):.2e}; identity={identity}/{len(qs)}',
              note='no quaternion->rotation converter exists in the repo yet (plan S0 step 5)')


# ---------------------------------------------------------------- E. geometry
def audit_geometry(audit):
    manifest = json.loads((G/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
    status = json.loads((G/'STATUS.json').read_text(encoding='utf8'))
    bad = []; triangles = 0; meshes = 0; materials = collections.Counter(); empty = []
    for s in manifest['scenes']:
        if not s['materials']:
            empty.append(s['scene_id'])
        for m in s['materials']:
            meshes += 1; materials[m['material_id']] += 1
            p = G/m['mesh']
            if not p.is_file() or sha_file(p) != m['sha256']:
                bad.append(m['mesh']); continue
            head = p.read_bytes()[:512].decode('ascii', 'replace')
            faces = int(re.search(r'element face (\d+)', head).group(1))
            triangles += faces
            if faces != m['triangles']:
                bad.append(m['mesh'] + ':triangle_count')
    ok = not bad and meshes == status['meshes'] and triangles == status['triangles']
    audit.add('E1', 'geometry', 'PASS' if ok else 'FAIL',
              f'{meshes} meshes / {triangles} triangles present with matching SHA (STATUS: '
              f'{status["meshes"]}/{status["triangles"]}, {status["status"]})', bad=bad[:20])
    f_lo, f_hi = F0/1e9, (F0+DF*(N_BINS-1))/1e9
    out_of_range = {k: ITU_RANGES_GHZ.get(k) for k in materials
                    if k not in NATIVE_EXTRA_MATERIALS
                    and (k not in ITU_RANGES_GHZ or not ITU_RANGES_GHZ[k][0] <= f_lo <= f_hi <= ITU_RANGES_GHZ[k][1])}
    audit.add('E2', 'geometry', 'PASS' if not out_of_range else 'FAIL',
              f'materials {dict(materials)} valid for ITU-R P.2040 over {f_lo:.4f}-{f_hi:.4f} GHz',
              invalid=out_of_range)
    audit.add('E3', 'geometry', 'WARN' if empty else 'PASS',
              f'scenes with zero meshes (free-space STATIC9): {len(empty)}; runtime calls scene.edit(add=[]) '
              f'for these - verify in pilot', scenes=empty)
    final = json.loads((G/'FINAL_MANIFEST.json').read_text(encoding='utf8'))
    outputs = final.get('outputs', {})
    drift = {}
    for name, digest in outputs.items():
        state = classify_digest(G/name, digest)
        if state not in ('EXACT', 'CRLF_ONLY'):
            drift[name] = state
    audit.add('E4', 'geometry', 'PASS' if not drift else 'FAIL',
              f'geometry FINAL_MANIFEST outputs {len(outputs)} vs checkout: drift={len(drift)}',
              drift=dict(list(drift.items())[:30]))


# ------------------------------------------------------------------- F. bank
def audit_bank(audit, cfg):
    bm = json.loads((B/'BANK_MANIFEST.json').read_text(encoding='utf8'))
    expected_f = F0 + DF*np.arange(N_BINS)
    results = {}
    for port in PORTS:
        name = f'{port}_bank.npz'
        path = B/name if (B/name).is_file() else ROOT/name
        digest = sha_file(path) if path.is_file() and not lfs_pointer(path.read_bytes()[:200]) else None
        row = dict(path=str(path.relative_to(ROOT)), sha_ok=digest == bm['npz_sha256'][name] == cfg['bank_sha256'][name])
        if digest:
            with np.load(path) as z:
                row.update(freq_exact=bool(np.array_equal(z['freqs_hz'], expected_f)),
                           theta=[float(z['theta_deg'][0]), float(z['theta_deg'][-1]), len(z['theta_deg'])],
                           phi=[float(z['phi_deg'][0]), float(z['phi_deg'][-1]), len(z['phi_deg'])],
                           shape=list(z['e_theta'].shape),
                           finite=bool(np.isfinite(z['e_theta']).all() and np.isfinite(z['e_phi']).all()),
                           peak_abs=float(max(np.abs(z['e_theta']).max(), np.abs(z['e_phi']).max())))
        results[port] = row
    ok = all(r['sha_ok'] and r.get('freq_exact') and r.get('finite') and r.get('shape') == [N_BINS, 181, 361]
             for r in results.values())
    audit.add('F1', 'ffd_bank', 'PASS' if ok else 'FAIL',
              f'6 FFD banks: SHA==BANK_MANIFEST==CONFIG, 257-bin grid exact, finite, shape 257x181x361',
              ports=results)
    audit.add('F2', 'ffd_bank', 'PASS' if bm['ports'] == PORTS == cfg['ports'] else 'FAIL',
              f'port order BANK_MANIFEST/CONFIG = {cfg["ports"]} (arms CP=0:2, LP_AXIS=2:4, LP_DIAG=4:6)')
    phi = results['RHCP'].get('phi')
    audit.add('F3', 'ffd_bank', 'INFO' if phi and phi[1]-phi[0] == 360 else 'WARN',
              f'phi grid {phi}; theta grid {results["RHCP"].get("theta")}. BankPort wraps phi mod 360 then '
              f'clips index to n-2, so the 360-deg column duplicates 0 deg (seam continuity relies on the FFD)')


# ------------------------------------------------------------------ G. config
def audit_config(audit, cfg):
    n = cfg['noise']; d = cfg['detector']; s = cfg['solver']
    nv = n['boltzmann_j_per_k']*n['temperature_k']*10**(n['noise_figure_db']/10)*n['receiver_enbw_hz'] \
        / (n['coherent_averages']*n['tx_incident_power_w_per_active_mode'])
    thr = math.sqrt(6*nv*math.log(4112/0.001))
    audit.add('G1', 'config', 'PASS' if math.isclose(nv, n['noise_var_H_bin'], rel_tol=1e-12)
              and math.isclose(thr, d['threshold_value'], rel_tol=1e-12) else 'FAIL',
              f'noise_var_H_bin recomputed {nv:.15e} (config {n["noise_var_H_bin"]:.15e}); '
              f'detector threshold {thr:.6e} (config {d["threshold_value"]:.6e})')
    plan = dict(max_depth=3, samples_per_src=100000, max_num_paths_per_src=1000000, synthetic_array=True,
                los=True, specular_reflection=True, refraction=True, diffraction=False, edge_diffraction=False,
                diffuse_reflection=False, seed=20260924)
    audit.add('G2', 'config', 'PASS' if s == plan else 'FAIL', 'NATIVE41 solver block equals plan section 5',
              config=s)
    audit.add('G3', 'config', 'INFO',
              f'detector statistical_validation.executed={d["statistical_validation"]["executed"]}; '
              f'noise producer_bound={n["producer_bound"]}; hardware_calibrated={n["hardware_calibrated"]}',
              note='must stay un-promoted in all full-run reports (plan section 5)')
    geo = json.loads((G/'CONFIG.json').read_text(encoding='utf8'))
    same = {k: geo.get(k) == cfg.get(k) for k in ('solver', 'noise', 'detector', 'ports', 'bank_sha256',
                                                  'geometry_manifest_sha256', 'geometry_contract_sha256')}
    audit.add('G4', 'config', 'PASS' if all(same.values()) else 'WARN',
              'geometry-revision CONFIG and NATIVE41 CONFIG agree on physics/operating blocks', fields=same)
    m_sha = classify_digest(G/'SCENE_MESH_MANIFEST.json', cfg['geometry_manifest_sha256'])
    c_sha = classify_digest(G/'MODEL_CONTRACT.json', cfg['geometry_contract_sha256'])
    audit.add('G5', 'config', 'PASS' if {m_sha, c_sha} <= {'EXACT', 'CRLF_ONLY'} else 'FAIL',
              f'CONFIG geometry_manifest_sha256 -> {m_sha}; geometry_contract_sha256 -> {c_sha}',
              note='CRLF_ONLY: git stores LF; staging must hash the Windows bytes or re-baseline explicitly')
    absolute = [k for k in ('bank_root', 'geometry_root') if str(cfg.get(k, '')).startswith('D:')]
    audit.add('G6', 'config', 'WARN' if absolute else 'PASS',
              f'CONFIG carries Windows absolute roots {absolute}; full CONFIG needs local/server root mapping')


# -------------------------------------------------------------------- H. code
def audit_code(audit):
    rt = (ROOT/'scripts/g2_completion/sionna_native_runtime.py').read_text(encoding='utf8')
    findings = []
    pats = [
        (r"--stop',type=int,default=41", 'runtime --stop defaults to 41'),
        (r"c\['rows'\]\[a\.start:a\.stop\]", 'runtime reads targets only from CONFIG.rows'),
        (r"mkdir\(parents=True,exist_ok=False\)", 'runtime output dir must not exist: no resume'),
        (r"np\.savez_compressed\(a\.out/\(row\['link_id'\]", 'NPZ written in place (no temp file + atomic rename)'),
        (r"dr\.set_thread_count\(4\)", 'DrJit thread count hard-coded to 4'),
        (r"link_id'\]\+'_NATIVE\.npz'", 'output file names use link_id only (no target_id hash)'),
        (r"indices=\[0,128,256\] if a\.smoke", 'smoke = 3 bins; full = 257 bins'),
    ]
    for pat, msg in pats:
        if re.search(pat, rt):
            findings.append(dict(file='scripts/g2_completion/sionna_native_runtime.py', issue=msg))
    for f, pat, msg in [
        ('run_native41_refresh.py', r"range\(0,41,3\)", '41 rows / 14 lanes fixed'),
        ('run_native41_refresh.py', r"pathsolver_calls'\]==31611", 'call count asserted to 41x771'),
        ('run_native41_refresh.py', r"BANK='/home/KMS/SIONNA_NATIVE41", 'bank bound to previous remote campaign'),
        ('run_native41_refresh.py', r"'--user','1001:1001'", 'container UID:GID hard-coded (plan: use measured id)'),
        ('finish_sionna_native41.py', r"rows'\]==41", '41-row assert'),
        ('summarize_native41_refresh.py', r"len\(labels\)==41", '41-row assert'),
        ('prepare_sionna_native41.py', r"SIONNA_G2_SCOPED41_V3_20260925_01a0d6e5", 'depends on prior results folder not in repo'),
    ]:
        if re.search(pat, (ROOT/'scripts/g2_completion'/f).read_text(encoding='utf8')):
            findings.append(dict(file='scripts/g2_completion/'+f, issue=msg))
    src = (ROOT/'rt_cp_uwb_py/g2_relocated_inputs.py').read_text(encoding='utf8')
    if 'EXPECTED_41_UNIQUE_LINKS' in src:
        findings.append(dict(file='rt_cp_uwb_py/g2_relocated_inputs.py',
                             issue='RelocatedInputs.rows yields only the 41 changed links'))
    audit.add('H1', 'code', 'BLOCKER', f'existing runners are 41-row specific: {len(findings)} hard limits found',
              findings=findings)
    planned = ['rt_cp_uwb_py/g2_full_inputs.py', 'scripts/g2_completion/prepare_sionna_full.py',
               'scripts/g2_completion/run_sionna_full.py', 'scripts/g2_completion/finish_sionna_full.py',
               'scripts/g2_completion/verify_sionna_full.py', 'tests/test_g2_full_inputs.py',
               'tests/test_g2_full_resume.py']
    missing = [p for p in planned if not (ROOT/p).exists()]
    audit.add('H2', 'code', 'BLOCKER' if missing else 'PASS',
              f'full-campaign entry points not implemented: {len(missing)}/{len(planned)}', missing=missing)
    audit.add('H3', 'code', 'WARN',
              'H assembly multiplies paths.a by exp(-j2*pi*f*tau) with absolute f; LOS fixture checks |a| '
              'and tau separately, not the multi-path phase convention',
              action='add a two-path (PEC floor) analytic H(f) fixture to the pilot before S3')
    audit.add('H4', 'code', 'INFO',
              'PathSolver is re-run for every (bin, arm): 771 traces/target although geometry is '
              'frequency- and arm-independent; plan keeps this (no engine optimisation) - capacity must be '
              'measured in S2 pilot')


def audit_tests(audit):
    proc = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], cwd=ROOT,
                          capture_output=True, text=True, timeout=1800)
    tail = proc.stdout.strip().splitlines()[-8:]
    summary = tail[-1] if tail else proc.stderr[-300:]
    missing = sorted(set(re.findall(r"No such file or directory: '([^']+)'", proc.stdout)))
    missing = [str(Path(p).relative_to(ROOT)) if p.startswith(str(ROOT)) else p for p in missing]
    status = 'PASS' if proc.returncode == 0 else ('WARN' if missing else 'FAIL')
    audit.add('T1', 'tests', status, f'pytest: {summary}', missing_fixtures=missing, tail=tail)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--skip-tests', action='store_true')
    a = ap.parse_args()
    out = a.out if a.out.is_absolute() else ROOT/a.out
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    audit = Audit()
    audit_delivery(audit)
    audit_snapshot(audit)
    targets, frames, cfg = audit_targets(audit)
    audit_poses(audit, targets, frames, cfg)
    audit_geometry(audit)
    audit_bank(audit, cfg)
    audit_config(audit, cfg)
    audit_code(audit)
    if not a.skip_tests:
        audit_tests(audit)
    status = collections.Counter(c['status'] for c in audit.checks)
    verdict = ('NOT_READY_FOR_FULL_RUN' if status['BLOCKER'] or status['FAIL'] else 'READY_FOR_S0')
    result = dict(audit_id='SIONNA_FULL_RESIM_20260925_01a0d86d/PREFLIGHT', verdict=verdict,
                  status_counts=dict(status), rf_calls=0, inputs_modified=False,
                  started_utc=started, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  checks=audit.checks)
    (out/'AUDIT.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf8')
    code = [Path(__file__).resolve(), ROOT/'rt_cp_uwb_py/l1_l2_rf_synthesis.py']
    manifest = dict(command=sys.argv, timestamp_utc=result['finished_utc'], python=sys.version,
                    numpy=np.__version__,
                    git_head=subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                            text=True).stdout.strip() or None,
                    code_sha256={str(p.relative_to(ROOT)): sha_file(p) for p in code},
                    inputs_sha256={str(p.relative_to(ROOT)): sha_file(p) for p in
                                   [FILE_LIST, CAMPAIGN/'PLAN_INPUT_SNAPSHOT.json', C, STATIC9,
                                    G/'SCENE_MESH_MANIFEST.json', B/'BANK_MANIFEST.json',
                                    R/'CHANGED_LINKS.json', R/'common/LINKS.jsonl', R/'common/FRAMES.jsonl']
                                   + [R/'inputs_v6'/f/'INPUT.json' for f in L_FAMILIES]},
                    outputs_sha256={'AUDIT.json': sha_file(out/'AUDIT.json')})
    (out/'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(json.dumps(dict(verdict=verdict, status_counts=dict(status))))


if __name__ == '__main__':
    main()

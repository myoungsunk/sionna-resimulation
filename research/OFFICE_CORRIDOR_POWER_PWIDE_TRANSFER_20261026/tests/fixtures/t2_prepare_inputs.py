# Verbatim functions from T2_NEW_ROUTE_BASELINE/prepare_inputs.py
# Commit: 034e57a7209a3bd1bb8857b24fd85c64942e1258
from pathlib import Path
import hashlib,json,sys,importlib.util
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def wrap(x): return (np.asarray(x)+np.pi) % (2*np.pi)-np.pi

def receipt_index(root):
    records, receipts = {}, []
    for name, key in [('ARCHIVE_CONTENTS_AND_SHA.json', 'extracted'),
                      ('SOURCE_RELEASE_SUBSET_RECEIPT.json', 'kept')]:
        for path in root.rglob(name):
            data = json.loads(path.read_text()); receipts.append(dict(path=str(path), sha256=sha(path)))
            for row in data.get(key, []):
                dest = (path.parent/'data'/row['name']).resolve()
                expected = row['sha256'].lower()
                if dest in records and records[dest] != expected:
                    raise ValueError('CONFLICTING_RECEIPT:'+str(dest))
                records[dest] = expected
    if not receipts: raise ValueError('BLOCKED_INPUT:NO_SOURCE_EXTRACTION_SHA_RECEIPT')
    return records, receipts

def prepare_new_route(route_root, route_id):
    """Return frozen motion, exact RF mapping, flags and source identity metadata.

    route_root is one extracted release snapshot directory, containing its
    receipt and data subtree. Per-case files follow */CASES/<id>_M45_FULL/.
    No nearest time/geometry matching, re-created route, or LoS fill is allowed.
    """
    root = Path(route_root)
    if route_id not in ('C01', 'C02', 'C03', 'O01', 'O02', 'O03'):
        raise ValueError('UNKNOWN_ROUTE')
    lock = json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
    expected, receipts = receipt_index(root)
    verified = {}

    def verify(path):
        path = path.resolve()
        if path not in expected: raise ValueError('BLOCKED_INPUT:UNRECEIPTED_FILE:'+str(path))
        value = sha(path)
        if value != expected[path]: raise ValueError('INPUT_SHA_MISMATCH:'+str(path))
        verified[str(path)] = value

    def candidates(suffix):
        found = []
        for path in root.rglob('*'+suffix):
            if 'BATCHES' in path.parts: continue # partial chunks are not full-route duplicates
            data = pd.read_csv(path)
            if 'route_id' not in data or set(data.route_id.astype(str)) != {route_id}: continue
            verify(path); found.append((path, data))
        if not found: raise ValueError('BLOCKED_INPUT:MISSING_'+route_id+'_'+suffix)
        if len({sha(path) for path, _ in found}) != 1:
            raise ValueError('NONIDENTICAL_DUPLICATE_'+suffix)
        return found

    radios = candidates('RADIO_POSE.csv')
    # Published releases omit full motion CSV. Reconstruct only through the
    # frozen original route generator and require identical emitted RF CSV.
    existing_motion=list(root.rglob('*ROUTE_POSE.csv'))
    if not existing_motion:
        source_root=HERE.parents[2]
        generator_path=source_root/'research/POWERJOINT_M45_COMPACT_20261019/02_prepare_routes.py'
        spec=importlib.util.spec_from_file_location('frozen_route_generator',generator_path)
        generator=importlib.util.module_from_spec(spec)
        # Sensor-v2 and scene validators have distinct pinned qclean_uwb roots.
        # Import validators in an isolated module cache, then restore sensor modules.
        saved={k:v for k,v in sys.modules.items() if k=='qclean_uwb' or k.startswith('qclean_uwb.')}
        old_path=sys.path.copy()
        for key in saved: del sys.modules[key]
        try: spec.loader.exec_module(generator)
        finally:
            for key in list(sys.modules):
                if key=='qclean_uwb' or key.startswith('qclean_uwb.'): del sys.modules[key]
            sys.modules.update(saved);sys.path[:]=old_path
        request_path=generator_path.with_name('01_ROUTE_REQUEST.json')
        request=json.loads(request_path.read_text())
        route=next(r for r in request['routes'] if r['id']==route_id)
        rows=generator.generate(request,route)
        generated=root/'reconstructed_motion';generated.mkdir(exist_ok=True)
        check=generated/(route_id+'_RADIO_CHECK.csv')
        generator.emit_csv(check,[r for r in rows if r['rf_sample']])
        if any(check.read_bytes()!=path.read_bytes() for path,_ in radios):
            raise ValueError('BLOCKED_INPUT:ORIGINAL_GENERATOR_RF_CSV_NOT_BYTE_IDENTICAL')
        motion_path=generated/(route_id+'_ROUTE_POSE.csv');generator.emit_csv(motion_path,rows)
        expected[motion_path.resolve()]=sha(motion_path)
        receipts.append(dict(kind='ORIGINAL_GENERATOR_RECONSTRUCTION',generator_sha256=sha(generator_path),request_sha256=sha(request_path),radio_csv_sha256=sha(check),full_motion_sha256=sha(motion_path),original_RF_byte_identical=True))
    motions = candidates('ROUTE_POSE.csv')
    motion_path, motion = motions[0]; radio_path, radio = radios[0]
    required = ['pose_id', 't_s', 'x_m', 'y_m', 'z_m', 'yaw_body_deg', 'yaw_antenna_deg']
    for data in (motion, radio):
        if any(key not in data for key in required): raise ValueError('POSE_COLUMNS_MISSING')
        if not np.isfinite(data[required].to_numpy(float)).all(): raise ValueError('NONFINITE_POSE')
        if not data.pose_id.is_unique: raise ValueError('DUPLICATE_POSE_ID')
        if not np.array_equal(data.pose_id.to_numpy(), data.pose_id.to_numpy(int)):
            raise ValueError('NONINTEGER_POSE_ID')
    t = motion.t_s.to_numpy(float)
    if abs(t[0]) > lock['motion_time_tolerance_s']:
        raise ValueError('MOTION_CLOCK_NOT_STARTING_AT_ZERO')
    if len(t) < 2 or np.max(abs(np.diff(t)-lock['motion_dt_s'])) > lock['motion_time_tolerance_s']:
        raise ValueError('MOTION_NOT_FULL_QUARTER_SECOND_CLOCK')
    if np.max(abs(motion.z_m.to_numpy(float)-.45)) > 1e-12:
        raise ValueError('FROZEN_HEIGHT_CHANGED')
    truth = np.column_stack((motion.x_m, motion.y_m, np.radians(motion.yaw_body_deg)))
    antenna_error = abs(wrap(np.radians(motion.yaw_antenna_deg)-truth[:, 2]-np.pi/4))
    if antenna_error.max() > np.radians(1e-6): raise ValueError('MOUNT_NOT_BODY_PLUS45')
    byid = {int(pose): i for i, pose in enumerate(motion.pose_id)}
    if any(int(pose) not in byid for pose in radio.pose_id): raise ValueError('RF_POSE_ID_NOT_IN_MOTION')
    indices = np.array([byid[int(pose)] for pose in radio.pose_id], int)
    if len(indices) > 1 and not np.all(np.diff(indices) > 0): raise ValueError('RF_ORDER_NOT_MOTION_ORDER')
    aligned = motion.iloc[indices]
    for key in required:
        if np.max(abs(aligned[key].to_numpy(float)-radio[key].to_numpy(float))) > 1e-12:
            raise ValueError('RF_MOTION_VALUE_MISMATCH:'+key)
    if 'rf_sample' not in motion: raise ValueError('MISSING_FROZEN_RF_SAMPLE_MASK')
    if not np.array_equal(np.flatnonzero(motion.rf_sample.to_numpy(int)), indices):
        raise ValueError('RADIO_ROWS_NOT_EXACT_FROZEN_RF_SUBSET')
    dp = np.diff(truth[:, :2], axis=0)
    lateral = -dp[:, 0]*np.sin(truth[:-1, 2])+dp[:, 1]*np.cos(truth[:-1, 2])
    if abs(lateral).max() > lock['legacy_euler_lateral_tolerance_m']:
        raise ValueError('BLOCKED_INPUT:LATERAL_RESIDUAL_EXCEEDS_DECLARED_ROUNDING_BOUND')
    anchors = ['A', 'B'] if route_id.startswith('C') else ['O0']
    cases = []
    for anchor in anchors:
        case_name = f'{route_id}_{anchor}_M45_FULL'
        case_radios = [(path, data) for path, data in radios if path.parent.name == case_name]
        if len(case_radios) != 1: raise ValueError('BLOCKED_INPUT:NONUNIQUE_CASE_RADIO:'+case_name)
        case_path, case_radio = case_radios[0]
        full = case_path.parent/'H_FULL.npy'; los = case_path.parent/'H_DIRECT_LOS.npy'
        verify(full); verify(los)
        flags_path = case_path.parent/'LOS_EXISTS.npy'
        if flags_path.is_file():
            verify(flags_path); flags = np.load(flags_path, allow_pickle=False)
            if flags.ndim != 1 or len(flags) != len(radio) or not np.isin(flags, [0, 1]).all():
                raise ValueError('INVALID_LOS_EXISTS:'+case_name)
            flags = flags.astype(bool)
        elif 'los_exists' in case_radio:
            raw_flags = case_radio.los_exists
            normalized = raw_flags.astype(str).str.lower()
            if not normalized.isin(['true', 'false', '1', '0']).all(): raise ValueError('INVALID_LOS_EXISTS')
            flags = normalized.isin(['true', '1']).to_numpy()
            flags_path = case_path
        else:
            raise ValueError('BLOCKED_INPUT:MISSING_LOS_EXISTS_NO_SYNTHESIS:'+case_name)
        cases.append(dict(case_id=case_name, anchor=anchor, radio_path=str(case_path),
                          full_path=str(full), los_path=str(los), los_exists=flags,
                          los_exists_path=str(flags_path)))
    metadata = dict(route_id=route_id, motion_path=str(motion_path), radio_path=str(radio_path),
        motion_n=len(motion), rf_n=len(radio), motion_dt_s=lock['motion_dt_s'],
        max_lateral_serialization_residual_m=float(abs(lateral).max()),
        rounding_tolerance_m=lock['legacy_euler_lateral_tolerance_m'], input_sha256=verified,
        receipts=receipts, POWER_training='all existing R2/R4/R5; new routes not used')
    return dict(motion_t=t, motion_truth=truth, motion_pose_ids=motion.pose_id.to_numpy(int),
                rf_motion_indices=indices, rf_pose_ids=radio.pose_id.to_numpy(int),
                lateral_residual_m=np.r_[0., lateral], metadata=metadata, cases=cases)

"""Fail-closed, staged input admission. Pure stdlib; never trusts a saved PASS.

Input sealing is deliberately narrower than engine qualification or adoption.
The latter stages cannot pass from receipts alone: their executable validators
must be connected before those stages are available.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

VERSION = 'rt-admission-v1'
FAMILIES = {'L1': 12000, 'L1multi': 12000, 'L2static': 3000,
            'L2multi': 6000, 'C1pilot': 6000}
ROOMS = {'L1': 40, 'L1multi': 40, 'L2static': 20, 'L2multi': 20, 'C1pilot': 20}
FFD_HASHES = {
 'RHCP_new_6G7G_11pts.ffd':'c907dd425eaec3699afa683bed994abf34d035c7f1323a080ed890c4d72ebd6a',
 'LHCP_new_6G7G_11pts.ffd':'eb2212b3c1e25dde0d9d041f9b0c875c23a8351c3f61bf645b87fd784c790059',
 'LP_x-axis_pol_6G7G_11pts_new.ffd':'e0caaa4ccbf496f3e6609efe2aa28f96ad47e4ced71c874eaea9ec818a29243f',
 'LP_y-axis_pol_6G7G_11pts_new.ffd':'5b2ca5937b32190d2ff08252b27a2e55b2f147309721a90717ec476fbfe301b5',
 'LP_+45_new_6G7G_11pts.ffd':'0e8e7bca8140946785cf5e5e0d4386d8bc602dba2d89e9e464d5eab4156b4a40',
 'LP_-45_new_6G7G_11pts.ffd':'edb4aa30ef66a362f02714e408076687bbbbc01907e9b2489e92c99af613cbcb'}
TYPES = {'A', 'B', 'C', 'HALL', 'WAREHOUSE', 'CORRIDOR', 'ATRIUM'}
WALLS = {'floor': (2, 0), 'ceiling': (2, 1), 'wall_west': (0, 0),
         'wall_east': (0, 1), 'wall_south': (1, 0), 'wall_north': (1, 1)}
INPUT_GATES = ('C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C08', 'C10',
               'C11', 'C12', 'C13', 'C14', 'C17', 'C18')
LATER = {'C07': 'SAVED_PATH_VALIDATOR_REQUIRED', 'C09': 'OBSERVATION_VALIDATOR_REQUIRED',
         'C15': 'ENGINE_ROUNDTRIP_VALIDATOR_REQUIRED',
         'C16': 'INDEPENDENT_ENGINE_QUALIFICATION_REQUIRED'}


class AdmissionError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise AdmissionError(message)


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def vector(x, n=3):
    return isinstance(x, list) and len(x) == n and all(number(v) for v in x)


def sub(a, b): return [x-y for x, y in zip(a, b)]
def add(a, b): return [x+y for x, y in zip(a, b)]
def scale(a, k): return [x*k for x in a]
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _unique_pairs(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, 'DUPLICATE_JSON_KEY:'+k)
        out[k] = v
    return out


def read_json(path):
    def bad(value): raise AdmissionError('NONFINITE_JSON:'+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=_unique_pairs, parse_constant=bad)


def relative_file(root, name):
    require(isinstance(name, str) and '\\' not in name and ':' not in name,
            'INVALID_ASSET_PATH')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and name not in ('', '.'),
            'ASSET_TRAVERSAL')
    root = Path(root).resolve()
    current = root
    for part in p.parts:
        current /= part
        require(not current.is_symlink(), 'ASSET_SYMLINK')
    require(current.is_file() and current.resolve().is_relative_to(root), 'MISSING_ASSET:'+name)
    return current


def corners(face):
    return [add(face['point'], add(scale(face['u_axis'], u*face['half_u']),
                                  scale(face['v_axis'], v*face['half_v'])))
            for u, v in ((-1,-1),(-1,1),(1,-1),(1,1))]


def box(faces):
    points = [p for s in faces for p in corners(s)]
    return ([min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)])


def occupied_boxes(scene):
    """Derive occupied extents from geometry, not supplied bounds/flags."""
    named = {s['name']: s for s in scene['surfaces'] if s['name'] not in WALLS}
    remaining = dict(named)
    groups = []
    suffixes = ('west', 'east', 'south', 'north', 'top')
    for name in list(named):
        prefix, _, suffix = name.rpartition('_')
        members = [prefix+'_'+s for s in suffixes]
        if suffix in suffixes and all(m in remaining for m in members):
            groups.append([remaining.pop(m) for m in members])
    for members in (('cabinet_front','cabinet_side','cabinet_top'), ('desk_top','desk_front')):
        present = [m for m in members if m in remaining]
        if len(present) >= 2:
            groups.append([remaining.pop(m) for m in present])
    groups.extend([[s] for s in remaining.values()])
    return [box(g) for g in groups]


def face_distance(p, face):
    d = sub(p, face['point'])
    u = max(-face['half_u'], min(face['half_u'], dot(d, face['u_axis'])))
    v = max(-face['half_v'], min(face['half_v'], dot(d, face['v_axis'])))
    return norm(sub(d, add(scale(face['u_axis'], u), scale(face['v_axis'], v))))


def validate_face(s):
    require(type(s.get('surface_id')) is int and isinstance(s.get('name'), str), 'FACE_ID')
    for k in ('point', 'normal', 'u_axis', 'v_axis'):
        require(vector(s.get(k)), 'FACE_VECTOR:'+k)
    for k in ('normal', 'u_axis', 'v_axis'):
        require(abs(norm(s[k])-1) <= 1e-8, 'FACE_UNIT:'+k)
    for a,b in (('normal','u_axis'),('normal','v_axis'),('u_axis','v_axis')):
        require(abs(dot(s[a],s[b])) <= 1e-8, 'FACE_ORTHOGONAL')
    require(all(number(s.get(k)) and s[k]>0 for k in ('half_u','half_v')), 'FACE_EXTENT')
    require(isinstance(s.get('material'), dict), 'MATERIAL_MISSING')
    m=s['material']
    require(isinstance(m.get('kind'),str) and m['kind'].lower() in ('dielectric','pec') and isinstance(m.get('name'),str), 'MATERIAL_KIND')
    if m['kind'].lower()=='pec':require(m.get('pec_tm_sign')==-1.,'PEC_TM_SIGN')
    require(number(m.get('eps_r')) and m['eps_r']>0, 'MATERIAL_EPSILON')
    for k in ('tan_delta','conductivity_s_m'):
        require(number(m.get(k)) and m[k]>=0, 'MATERIAL_LOSS:'+k)
    canonical(m)


def validate_scene(sc):
    require(sc.get('room_type') in TYPES, 'UNKNOWN_ROOM_TYPE')
    require(vector(sc.get('size')) and min(sc['size'])>0, 'ROOM_SIZE')
    require(sc.get('units')=='m' and sc.get('coordinate_system')=='right_handed_z_up', 'COORDINATES')
    require(isinstance(sc.get('surfaces'), list) and len(sc['surfaces'])>=6, 'EMPTY_SCENE')
    ids=set();names=set();physical=set()
    for s in sc['surfaces']:
        validate_face(s)
        require(s['surface_id'] not in ids and s['name'] not in names, 'DUPLICATE_FACE_ID')
        ids.add(s['surface_id']);names.add(s['name'])
        cs=corners(s)
        require(all(-1e-6<=p[i]<=sc['size'][i]+1e-6 for p in cs for i in range(3)), 'FACE_OUTSIDE_ROOM')
        fp=tuple(sorted(tuple(round(v,8) for v in p) for p in cs))
        require(fp not in physical, 'DUPLICATE_PHYSICAL_FACE');physical.add(fp)
    require(set(WALLS)<=names, 'MISSING_ROOM_BOUNDARY')
    for name,(axis,side) in WALLS.items():
        s=next(s for s in sc['surfaces'] if s['name']==name)
        lo,hi=box([s]);expected=sc['size'][axis]*side
        require(abs(lo[axis]-expected)<=1e-6 and abs(hi[axis]-expected)<=1e-6, 'BOUNDARY_PLANE')
        for i in range(3):
            if i!=axis:
                require(abs(lo[i])<=1e-6 and abs(hi[i]-sc['size'][i])<=1e-6, 'BOUNDARY_COVERAGE')
    return occupied_boxes(sc)


def validate_position(p, sc, boxes, anchor=False):
    require(vector(p), 'POSITION_NONFINITE')
    require(all(0<=p[i]<=sc['size'][i] for i in range(3)), 'POSITION_OUTSIDE')
    require(all(.4-1e-9<=p[i]<=sc['size'][i]-.4+1e-9 for i in (0,1)), 'WALL_MARGIN')
    if anchor: require(p[2]<=sc['size'][2]-.1+1e-9, 'CEILING_GAP')
    require(all(not all(lo[i]-.05<=p[i]<=hi[i]+.05 for i in range(3)) for lo,hi in boxes), 'OCCUPIED_VOLUME')
    require(all(face_distance(p,s)>=.1-1e-9 for s in sc['surfaces']), 'FACE_CLEARANCE')


def validate_object(obj, size):
    """Strict required input; no link-dependent normal, clamping or fallback."""
    require(isinstance(obj,dict), 'OBJECT_MISSING')
    require(obj.get('condition') in ('side_reflector','blockage','metal_near'), 'OBJECT_CONDITION')
    require(obj.get('bounds_valid') is True, 'OBJECT_BOUNDS_REJECTED')
    require(isinstance(obj.get('object_id'),str) and bool(obj['object_id']), 'OBJECT_ID')
    validate_face(obj['surface'])
    require(vector(size) and min(size)>0, 'ROOM_SIZE')
    require(all(0<=p[i]<=size[i] for p in corners(obj['surface']) for i in range(3)), 'OBJECT_OUTSIDE')
    return obj['surface']


def _gate_report():
    return {f'C{i:02}': {'status':'NOT_RUN','checks':0,'failures':[]} for i in range(1,19)}


def validate_package(root, stage='input'):
    try:
        return _validate_package(root, stage)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError, OverflowError) as e:
        gates = _gate_report()
        gates['C01'].update(status='FAIL', failures=['MALFORMED_INPUT:'+str(e)[:350]])
        return {'status':'HOLD','stage':stage,'gates':gates,'adoption':'HOLD',
                'engine_ready':False,'research_ready':False}


def _validate_package(root, stage='input'):
    """Recompute gates; reports in the package never authorize a stage."""
    root=Path(root);gates=_gate_report()
    def check(gid, fn):
        try:
            fn();gates[gid]['checks']+=1
            if not gates[gid]['failures']:gates[gid]['status']='PASS'
        except (ValueError,KeyError,TypeError,AttributeError,IndexError,OSError,OverflowError) as e:
            gates[gid]['status']='FAIL';gates[gid]['failures'].append(str(e)[:350])
    try: p=read_json(relative_file(root,'INPUT.json'))
    except (ValueError,OSError) as e:
        gates['C01'].update(status='FAIL',failures=[str(e)])
        return {'status':'HOLD','stage':stage,'gates':gates,'adoption':'HOLD'}
    family=p.get('family');scenes=p.get('scenes',{});links=p.get('links',[])
    def contract():
        require(p.get('schema_version')==VERSION, 'SCHEMA_VERSION')
        require(family in FAMILIES, 'UNSUPPORTED_FAMILY_REQUIRES_NEW_CONTRACT')
        require(p.get('purpose')=='historical_geometry_repair_input', 'PURPOSE')
        require(p.get('condition_profile')=='historical_clean_only', 'NONCLEAN_CONTRACT_NOT_ADMITTED')
        require(p.get('position_contract')=='P5R_DP20_UNCHANGED', 'POSITION_CONTRACT')
        require(isinstance(links,list) and len(links)==FAMILIES[family], 'EXPECTED_CASE_COUNT')
        require(isinstance(scenes,dict) and bool(scenes), 'EMPTY_SCENES')
    check('C01',contract)
    if gates['C01']['status']!='PASS':
        return {'status':'HOLD','stage':stage,'gates':gates,'adoption':'HOLD'}
    boxes={}
    for sid,sc in scenes.items():
        def scene_check(sid=sid,sc=sc):
            require(digest(sc)==sid,'SCENE_DIGEST_MISMATCH')
            boxes[sid]=validate_scene(sc)
        check('C02',scene_check)
        check('C11',lambda sc=sc: [validate_face(s) for s in sc['surfaces']])
    def clean():
        require(all(not s['name'].startswith('condition_') for sc in scenes.values() for s in sc['surfaces']), 'UNDECLARED_CONDITION_OBJECT')
        require(all(r.get('condition')=='clean' for r in links),'CONDITION_PROFILE_MISMATCH')
    check('C05',clean);check('C06',clean)
    case_ids=set();groups=defaultdict(list);room_anchors={};room_scenes={}
    source_rows=read_json(relative_file(root,p['source_rows_asset']))
    require(isinstance(source_rows,list) and len(source_rows)==len(links),'SOURCE_ROWS_COUNT')
    sources={r['case_id']:r for r in source_rows}
    require(len(sources)==len(source_rows),'SOURCE_DUPLICATE_CASE')
    for r in links:
        def pos(r=r):
            require(r.get('scene_id') in boxes,'SCENE_NOT_VALIDATED')
            sc=scenes[r['scene_id']]
            validate_position(r['tx'],sc,boxes[r['scene_id']],True)
            validate_position(r['rx'],sc,boxes[r['scene_id']])
            length=norm(sub(r['tx'],r['rx']))
            require(length>=.5-1e-9,'MIN_LINK')
            require(number(r.get('true_range_m')) and abs(length-r['true_range_m'])<=1e-8,'TRUE_RANGE')
        check('C03',pos)
        def identity(r=r):
            require(type(r.get('case_id')) is int and r['case_id'] not in case_ids,'DUPLICATE_CASE')
            case_ids.add(r['case_id'])
            require(all(isinstance(r.get(k),str) and r[k] for k in ('room_id','epoch_id','anchor_id')),'LINK_KEYS')
            require(vector(r.get('tag_orientation_deg')),'ORIENTATION')
            require(isinstance(r.get('source_row'),dict) and bool(r['source_row']),'SOURCE_ROW_MISSING')
            canonical(r['source_row'])
            src=r['source_row']; sc=scenes[r['scene_id']]
            require(src==sources[r['case_id']],'SOURCE_ROW_CHANGED')
            require(src['case_id']==r['case_id'] and str(src['room_id'])==r['room_id'],'SOURCE_ID')
            for end in ('tx','rx'):
                require(r[end]==[src[f'{end}_{a}_m'] for a in 'xyz'],'SOURCE_POSITION')
            require(sc['size']==[src[f'room_size_{a}_m'] for a in 'lwh'],'SOURCE_SIZE')
            require(sc['room_type']==src['room_type'],'SOURCE_ROOM_TYPE')
            require(src.get('condition_id','clean')==r['condition'],'SOURCE_CONDITION')
            require(r['tag_orientation_deg']==[0.,0.,src.get('rx_azimuth_deg',0.)],'SOURCE_ORIENTATION')
            require(r['anchor_id']==str(src.get('anchor_id',src['case_id'])),'SOURCE_ANCHOR')
            require(r['epoch_id']==str(src.get('epoch_id',src.get('tag_id',src['case_id']))),'SOURCE_EPOCH')
            groups[(r['room_id'],r['epoch_id'])].append(r)
            if family in ('L1multi','L2multi','C1pilot'):
                key=(r['room_id'],r['anchor_id'])
                require(key not in room_anchors or room_anchors[key]==r['tx'],'ANCHOR_MOVED')
                room_anchors[key]=r['tx']
            require(r['room_id'] not in room_scenes or room_scenes[r['room_id']]==r['scene_id'],'ROOM_SCENE_CHANGED')
            room_scenes[r['room_id']]=r['scene_id']
        check('C04',identity)
    def shared():
        n=4 if family in ('L1multi','L2multi','C1pilot') else 1
        require(all(len(rows)==n and len({r['anchor_id'] for r in rows})==n for rows in groups.values()),'ANCHOR_COVERAGE')
        for rows in groups.values():
            for k in ('scene_id','rx','tag_orientation_deg','condition'):
                require(len({digest(r[k]) for r in rows})==1,'SHARED_ENVIRONMENT:'+k)
        require(len(room_scenes)==ROOMS[family],'ROOM_COVERAGE')
        require(set(room_scenes.values())==set(scenes),'UNREFERENCED_SCENE')
    check('C04',shared)
    check('C08',lambda: require(p.get('physics')=={'R_max':3,'T':False,'D':False,'S':False,'proxy':False}, 'PHYSICS_SCOPE'))
    check('C10',lambda: require(p.get('temporal_claim') is False and all(r.get('timestamp_s') is None for r in links),'STATIC_TEMPORAL_CLAIM'))
    rf=p.get('rf',{})
    def rf_check():
        expected=[6250400000.+1950000.*i for i in range(257)]
        require(rf.get('frequencies_hz')==expected,'FREQUENCY_GRID')
        require(rf.get('window')=='hann' and rf.get('ifft_pad_factor')==4,'CIR_CONTRACT')
        for key in ('config_asset','antenna_source_asset','noise_source_asset','detector_source_asset'):
            require(rf.get(key) in p.get('assets',{}),'RF_SOURCE_MISSING:'+key)
        require(isinstance(rf.get('ffd_assets'),list) and len(rf['ffd_assets'])==6,'FFD_MISSING')
        require(all(x in p['assets'] for x in rf['ffd_assets']),'FFD_ASSET_MISSING')
        require({PurePosixPath(x).name:p['assets'][x] for x in rf['ffd_assets']}==FFD_HASHES,'FFD_SOURCE_SUBSTITUTED')
        require(rf.get('port_contract')=='preserve_source_config_and_rows','PORT_CONTRACT')
        require(rf.get('cross_engine_rf_qualified') is False,'PREMATURE_RF_QUALIFICATION')
        config=read_json(relative_file(root,rf['config_asset']))
        cfg=config['p5r_cp_config']
        require(cfg['f_center']==6.5e9 and cfg['bw']==499.2e6 and cfg['n_freq']==257 and cfg['rt_max_bounce']==3,'SOURCE_RF_CONFIG')
        if family=='C1pilot':
            native=config['c1_native_config']
            require(native['f_center']==6.5e9 and native['bw']==499.2e6 and native['n_freq']==257 and native['rt_max_bounce']==3,'NATIVE_RF_CONFIG')
            name=rf['native_antenna_asset'];require(name in p['assets'],'NATIVE_ANTENNA_ASSET')
            meta=read_json(relative_file(root,name))
            require(set(meta)=={str(r['case_id']) for r in links},'ANTENNA_CASE_COVERAGE')
            for row in links:
                bases=meta[str(row['case_id'])]
                require(set(bases)=={'CP_NATIVE','LP_XY_NATIVE','LP_45_NATIVE'},'ANTENNA_BASIS_COVERAGE')
                for basis, ends in bases.items():
                    require(set(ends)=={'tx','rx'},'ANTENNA_ENDPOINT_COVERAGE')
                    for end, a in ends.items():
                        require(a['position']['values']==row[end],'ANTENNA_POSITION')
                        require(a['use_ffd'] is True and a['basis']==('circular' if basis=='CP_NATIVE' else 'linear'),'ANTENNA_MODEL')
                        require(a['convention']=='IEEE-RHCP' and a['circular_order']=='RL','ANTENNA_CONVENTION')
                        mat=a['ffd_local_to_world']['values']
                        require(isinstance(mat,list) and len(mat)==3 and all(vector(v) for v in mat),'ANTENNA_MATRIX')
                        require(all(abs(dot(mat[i],mat[j])-(1. if i==j else 0.))<=1e-8 for i in range(3) for j in range(3)),'ANTENNA_MATRIX_ORTHOGONAL')
                        det=sum(mat[0][i]*(mat[1][(i+1)%3]*mat[2][(i+2)%3]-mat[1][(i+2)%3]*mat[2][(i+1)%3]) for i in range(3))
                        require(abs(det-1.)<=1e-8,'ANTENNA_MATRIX_HANDEDNESS')
    check('C12',rf_check);check('C13',rf_check)
    def artifacts():
        required={'raw_paths','H_clean','H_noisy','CIR','features','candidates','labels','splits','OOF','calibration','policy'}
        require(set(p.get('downstream_status',{}))==required,'ARTIFACT_DECLARATIONS')
        require(all(v=='NOT_RUN_INPUT_ONLY' for v in p['downstream_status'].values()),'PREMATURE_OUTPUT_PASS')
    check('C14',artifacts)
    def cohort():
        require(len(case_ids)==FAMILIES[family],'CASE_COVERAGE')
        require(p.get('statistical_claim')=='NOT_ESTABLISHED','PREMATURE_STATISTICS')
        require(p.get('source_cases_asset') in p.get('assets',{}),'SOURCE_CASES_MISSING')
        require(p.get('source_rows_asset') in p.get('assets',{}),'SOURCE_ROWS_MISSING')
    check('C17',cohort)
    def assets():
        require(isinstance(p.get('assets'),dict) and len(p['assets'])>=6,'ASSETS_MISSING')
        for name,h in p['assets'].items():
            require(isinstance(h,str) and len(h)==64,'ASSET_HASH_FORMAT')
            require(sha(relative_file(root,name))==h,'ASSET_HASH_MISMATCH:'+name)
        expected={'INPUT.json',*p['assets']}
        actual={x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file()}
        require(not any(x.is_symlink() for x in root.rglob('*')),'PACKAGE_SYMLINK')
        require(actual-{'SEAL.json','INPUT_ADMISSION.json'}==expected,'UNMANIFESTED_FILES')
        require(p.get('validated_trace_asset') in p['assets'],'TRACE_SOURCE_MISSING')
        require(p['assets'][p['validated_trace_asset']]=='2b9318e06cac86c5822bff657fe8acb8cce0594cf868c511e2c1c0dda004d8a8','UNQUALIFIED_TRACE')
    check('C18',assets)
    for gid,reason in LATER.items():gates[gid].update(status='BLOCKED',failures=[reason])
    good=all(gates[k]['status']=='PASS' and gates[k]['checks']>0 for k in INPUT_GATES)
    # No CLI switch or forged PASS receipt can bypass unavailable later validators.
    if stage!='input': good=False
    return {'status':'PASS_INPUT_ONLY' if good else 'HOLD','stage':stage,
            'validator_version':VERSION,'input_sha256':sha(root/'INPUT.json'),
            'family':family,'cases':len(links),'gates':gates,'adoption':'HOLD',
            'engine_ready':False,'research_ready':False}


def seal_package(root):
    root=Path(root)
    require(not (root/'SEAL.json').is_symlink() and not (root/'INPUT_ADMISSION.json').is_symlink(),'SEAL_SYMLINK')
    require(not (root/'SEAL.json').exists(),'ALREADY_SEALED')
    report=validate_package(root)
    (root/'INPUT_ADMISSION.json').write_bytes(canonical(report))
    require(report['status']=='PASS_INPUT_ONLY','INPUT_ADMISSION_FAILED')
    seal={'kind':'INPUT_ONLY_NOT_ENGINE_ADMISSION','input_sha256':report['input_sha256'],
          'validator_sha256':sha(Path(__file__)),'report_sha256':sha(root/'INPUT_ADMISSION.json')}
    with (root/'SEAL.json').open('xb') as f:f.write(canonical(seal))
    return seal


def verify_seal(root):
    root=Path(root);seal=read_json(relative_file(root,'SEAL.json'))
    require(seal.get('kind')=='INPUT_ONLY_NOT_ENGINE_ADMISSION','SEAL_SCOPE')
    require(seal['validator_sha256']==sha(Path(__file__)),'VALIDATOR_CHANGED_REAUDIT_REQUIRED')
    require(seal['input_sha256']==sha(root/'INPUT.json'),'SEALED_INPUT_CHANGED')
    require(seal['report_sha256']==sha(root/'INPUT_ADMISSION.json'),'SEALED_REPORT_CHANGED')
    report=validate_package(root)
    require(report['status']=='PASS_INPUT_ONLY','SEALED_PACKAGE_INVALID')
    return report

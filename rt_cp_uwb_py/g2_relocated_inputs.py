"""Explicit relocated-input adapter; historical embedded geometry is not consumed."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .rf_volume_inputs import load_scene
from .rf_volume_events import VolumeScene, IdealTriangle
from .rf_volume_cached import CachedVolumeScene
from .c1_c3_geometry import panel_corners
from .l1_l2_rf_synthesis import historical_mount_frames


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class RelocatedInputs:
    def __init__(self, root, geometry_root):
        self.root = Path(root).resolve(); self.geometry_root = Path(geometry_root).resolve()
        self.inputs = {}; self.scenes = {}
        def read(p):
            self.inputs[str(p)] = sha(p)
            return json.loads(p.read_text(encoding='utf8'))
        changes = read(self.root/'CHANGED_LINKS.json')
        keys = {(v['family'], v['case_id']): v for v in changes}
        if len(keys) != 41:
            raise ValueError('EXPECTED_41_UNIQUE_LINKS')
        found = {}
        for family in ['L1', 'L1multi', 'L2static', 'L2multi']:
            doc = read(self.root/'inputs_v6'/family/'INPUT.json')
            for row in doc['links']:
                key = family, row['case_id']
                if key in keys:
                    found[key] = dict(row, family=family)
        for name in ['LINKS.jsonl', 'FRAMES.jsonl']:
            self.inputs[str(self.root/'common'/name)] = sha(self.root/'common'/name)
        with (self.root/'common/LINKS.jsonl').open(encoding='utf8') as f:
            for line in f:
                row = json.loads(line); key = row['family'], row['case_id']
                if key in keys:
                    if key in found: raise ValueError('DUPLICATE_LINK')
                    found[key] = dict(row, scene_id=row['room_id'])
        frame_keys = {(r['unit_id'], r['frame']) for r in found.values() if 'unit_id' in r}
        frames = {}
        with (self.root/'common/FRAMES.jsonl').open(encoding='utf8') as f:
            for line in f:
                row = json.loads(line); key = row['unit_id'], row['frame']
                if key in frame_keys:
                    digest = hashlib.sha256(json.dumps(row['physical'], sort_keys=True,
                              separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
                    if digest != row['canonical_scene_hash']: raise ValueError('FRAME_SHA_MISMATCH')
                    frames[key] = row
        if set(found) != set(keys): raise ValueError('MISSING_CHANGED_LINK')
        self.rows = []
        for key, change in keys.items():
            row = found[key]
            if row['rx'] != change['new'] or row['scene_id'] != change['scene_id']:
                raise ValueError('RELOCATION_MISMATCH')
            frame = frames[(row['unit_id'], row['frame'])] if 'unit_id' in row else None
            if frame and (frame['physical']['tag_pose']['position'] != row['rx']
                          or frame['canonical_scene_hash'] != row['scene_hash']):
                raise ValueError('LINK_FRAME_MISMATCH')
            mount_row = dict(row.get('source_row', row))
            if frame:
                mount_row['rx_azimuth_deg'] = np.degrees(frame['physical']['tag_pose']['yaw_rad'])
            tx_rotation, rx_rotation = historical_mount_frames(mount_row)
            self.rows.append(dict(row, link_id=f'{key[0]}_{key[1]}',
                frame_record=frame, tx_rotation=tx_rotation, rx_rotation=rx_rotation))

    def scene(self, row):
        sid = row['scene_id']
        if sid not in self.scenes:
            scene, epsilon, records = load_scene(self.geometry_root, sid)
            self.inputs.update({str(self.geometry_root/k): v for k,v in records.items()})
            self.scenes[sid] = scene, epsilon
        scene, epsilon = self.scenes[sid]
        ideals = list(scene.ideal_surfaces)
        frame = row['frame_record']
        obj = frame['physical'].get('object') if frame else None
        if obj:
            if obj['material']['kind'] != 'PEC': raise ValueError('UNSUPPORTED_DYNAMIC_OBJECT')
            corners = np.array(panel_corners(obj['panel']))
            for indices in ([0,1,2], [0,2,3]):
                ideals.append(IdealTriangle(corners[indices], 'PEC', obj['object_id'], None))
        return CachedVolumeScene(VolumeScene(scene.prisms, scene.tolerance, ideals)), epsilon

    def verify_inputs(self):
        if not all(sha(p) == h for p,h in self.inputs.items()):
            raise ValueError('INPUT_CHANGED_DURING_EXECUTION')


def load_recomputed_link(root, link_id, *, require_complete=True):
    """Producer-output consumer with explicit partial-only opt-in and SHA checks."""
    root = Path(root).resolve()
    manifest = json.loads((root/'MANIFEST.json').read_text(encoding='utf8'))
    def checked(name):
        path = root/name
        if path.resolve().parent != root or name not in manifest['outputs']:
            raise ValueError('UNMANIFESTED_PRODUCER_OUTPUT')
        if sha(path) != manifest['outputs'][name]: raise ValueError('PRODUCER_OUTPUT_SHA_MISMATCH')
        return path
    status = json.loads(checked('STATUS.json').read_text(encoding='utf8'))
    bound = json.loads(checked('PRODUCTION_INPUTS.json').read_text(encoding='utf8'))
    matches = [r for r in bound if r['link_id']==link_id]
    if len(matches) != 1: raise ValueError('LINK_NOT_UNIQUELY_BOUND')
    if require_complete and not status['production_admission']:
        raise ValueError('FULL_CHANNEL_AND_LABELS_NOT_QUALIFIED')
    row = matches[0]
    paths = json.loads(checked(link_id+'_PATHS.json').read_text(encoding='utf8'))
    if row['tx_m'] != paths['tx'] or row['rx_m'] != paths['rx'] or row['scene_id'] != paths['scene_id']:
        raise ValueError('PRODUCER_ENDPOINT_BINDING_MISMATCH')
    with np.load(checked(link_id+'_PARTIAL_RF.npz')) as a:
        if bool(a['full_channel_admitted']): raise ValueError('UNEXPECTED_PARTIAL_ADMISSION')
        data = {k:a[k].copy() for k in a.files}
    return dict(input=row, geometry=paths['geometry'], rf_labels=paths['rf_labels'],
                rf=data, production_admission=False)

"""SHA-checked G2 mesh/lineage adapter for the volume path producer."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .rf_volume_events import VolumeScene, VolumePrism, IdealTriangle
from .rf_junctions import epsilon_from_conductivity


def load_scene(root, scene_id):
    root = Path(root).resolve()
    inputs = {}
    def read(name):
        path = (root/name).resolve()
        if root not in path.parents:
            raise ValueError('INPUT_OUTSIDE_REVISION')
        raw = path.read_bytes()
        inputs[name] = hashlib.sha256(raw).hexdigest()
        return raw
    manifest = json.loads(read('SCENE_MESH_MANIFEST.json'))
    lineage = json.loads(read('SOURCE_SURFACE_LINEAGE.json'))
    contract = json.loads(read('MATERIAL_CONTRACT.json'))
    matches = [s for s in manifest['scenes'] if s['scene_id'] == scene_id]
    if len(matches) != 1:
        raise ValueError('SCENE_ID_NOT_UNIQUE')
    meshes = {}; coverage = {}
    for mesh in matches[0]['materials']:
        raw = read(mesh['mesh'])
        if inputs[mesh['mesh']] != mesh['sha256']:
            raise ValueError('MESH_SHA_MISMATCH')
        lines = raw.decode('ascii').splitlines(); end = lines.index('end_header')
        if 'format ascii 1.0' not in lines[:end]:
            raise ValueError('ONLY_ASCII_PLY_SUPPORTED')
        nv = int(next(x.split()[-1] for x in lines[:end] if x.startswith('element vertex ')))
        nf = int(next(x.split()[-1] for x in lines[:end] if x.startswith('element face ')))
        vertices = np.array([[float(x) for x in row.split()] for row in lines[end+1:end+1+nv]])
        faces = [list(map(int, row.split())) for row in lines[end+1+nv:end+1+nv+nf]]
        if any(len(row) != 4 or row[0] != 3 for row in faces) or len(faces) != nf:
            raise ValueError('NON_TRIANGLE_MESH')
        meshes[mesh['mesh']] = vertices[np.array([r[1:] for r in faces])]
        coverage[mesh['mesh']] = np.zeros(nf, int)
    ranges = {r['wall_id']: r for r in lineage['mesh_face_ranges'] if r['scene_id'] == scene_id}
    prisms = []; ideals = []
    for wall in (w for w in lineage['walls'] if w['scene_id'] == scene_id):
        row = ranges[wall['wall_id']]
        if row['face_count'] == 0:
            continue
        start = row['first_face']; stop = start+row['face_count']; name = row['mesh']
        if start < 0 or stop > len(meshes[name]):
            raise ValueError('INVALID_FACE_RANGE')
        coverage[name][start:stop] += 1
        mat = wall['material']; spec = contract['materials'][mat]
        corners = np.asarray(wall['corners'])
        n = np.cross(corners[1]-corners[0], corners[2]-corners[0]); n /= np.linalg.norm(n)
        for triangle in meshes[name][start:stop]:
            if mat in ('PEC', 'EPS4_LOSSLESS'):
                ideals.append(IdealTriangle(triangle, mat, wall['wall_id'], spec['epsilon_r']))
            else:
                if wall.get('material_side') != 'NEGATIVE_NORMAL' or not wall['thickness']:
                    raise ValueError('UNSUPPORTED_VOLUME_SIDE_OR_THICKNESS')
                prisms.append(VolumePrism(triangle, n, wall['thickness'], mat, wall['wall_id']))
    if any(np.any(counts != 1) for counts in coverage.values()):
        raise ValueError('FACE_LINEAGE_NOT_EXACTLY_ONCE')
    def epsilon(material, frequency_hz):
        if material == 'air':
            return 1+0j
        spec = contract['materials'][material]
        low, high = spec['valid_ghz']
        if not low <= frequency_hz/1e9 <= high:
            raise ValueError('MATERIAL_FREQUENCY_OUT_OF_RANGE')
        a,b,c,d = spec['coefficients_abcd']
        return epsilon_from_conductivity(a*(frequency_hz/1e9)**b, c*(frequency_hz/1e9)**d, frequency_hz)
    return VolumeScene(prisms, ideal_surfaces=ideals), epsilon, inputs

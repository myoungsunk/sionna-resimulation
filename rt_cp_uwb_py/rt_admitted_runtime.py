"""Opt-in corrected runtime; historical producer modules are never edited.

One context per process. A caller must validate/seal its input package first.
This module only implements the corrected propagation/condition binding, not
Sionna qualification or downstream scientific admission.
"""
from contextlib import contextmanager
from threading import Lock

import numpy as np

from . import sweep, trace_validated
from .core import Surface
from .rt_admission import AdmissionError, require, validate_object

_LOCK = Lock()


def append_required_object(scene, row, tx_pos, rx_pos):
    condition = str(row.get('condition_id', 'clean')).strip().lower()
    require(condition in ('clean','side_reflector','blockage','metal_near'), 'UNKNOWN_CONDITION')
    obj = row.get('scene_package_object')
    if condition == 'clean':
        require(obj is None, 'CLEAN_WITH_EXTRA_OBJECT')
        require(not any(s.name.startswith('condition_') for s in scene.surfaces), 'CLEAN_SCENE_HAS_OBJECT')
        return scene
    require(obj is not None, 'REQUIRED_SHARED_OBJECT_MISSING')
    size = [row.get(k) for k in ('room_size_l_m','room_size_w_m','room_size_h_m')]
    face = validate_object(obj,size)
    require(obj['condition']==condition,'OBJECT_CONDITION_MISMATCH')
    require(face['surface_id'] not in {s.surface_id for s in scene.surfaces},'OBJECT_ID_COLLISION')
    require(face['name'].startswith('condition_'),'OBJECT_NAME')
    from .core import Material
    material=Material(**face['material'])
    added=Surface(face['surface_id'],face['name'],np.array(face['point']),
                  np.array(face['normal']),np.array(face['u_axis']),np.array(face['v_axis']),
                  face['half_u'],face['half_v'],material)
    # Position validation remains a package/epoch gate, not an anchor-dependent
    # object constructor. Geometry is copied verbatim from the shared object.
    return scene.__class__(tuple(scene.surfaces)+(added,))


def no_proxy(scene, tx, rx):
    return None


@contextmanager
def corrected_runtime(fe_module=None):
    require(_LOCK.acquire(blocking=False),'RUNTIME_CONTEXT_ALREADY_ACTIVE')
    old=(sweep.enumerate_paths,sweep._append_condition_geometry,sweep._blockage_diffraction_proxy_path)
    fe_old=None
    try:
        if fe_module is not None:
            fe_old=fe_module._real_enumerate_paths
            fe_module._real_enumerate_paths=trace_validated.enumerate_paths
        sweep.enumerate_paths=trace_validated.enumerate_paths
        sweep._append_condition_geometry=append_required_object
        sweep._blockage_diffraction_proxy_path=no_proxy
        yield
    finally:
        sweep.enumerate_paths,sweep._append_condition_geometry,sweep._blockage_diffraction_proxy_path=old
        if fe_module is not None and fe_old is not None:
            fe_module._real_enumerate_paths=fe_old
        _LOCK.release()


def trace_admitted_scene(scene, tx, rx, max_reflections=3):
    require(type(max_reflections) is int and 0<=max_reflections<=3,'REFLECTION_ORDER')
    for position in (tx,rx):
        a=np.asarray(position,dtype=float)
        require(a.shape==(3,) and np.isfinite(a).all(),'INVALID_ENDPOINT')
    require(np.linalg.norm(np.asarray(rx)-np.asarray(tx))>=.5,'MIN_LINK')
    paths=trace_validated.enumerate_paths(scene,np.asarray(tx),np.asarray(rx),max_reflections)
    return {'paths':paths,'status':'PATHS_FOUND' if paths else 'NO_PATH_IN_SPECULAR_MODEL',
            'search':'DETERMINISTIC_IMAGE_ENUMERATION','proxy_used':False}

import json
from math import dist
import sys
from pathlib import Path
import numpy as np
from run_tb3_g1_pilot import load_runtime
from run_tb3_production import case_inputs
from tb3_g6_face_match import load_faces, fold_images
from tb3_g6_revalidate import trace_hits
from validate_tb3_production_g3 import scene_runtime

p=Path('/production')
f1=json.loads((p/'config/PRODUCTION_F1.json').read_text())
ref=Path('/ref')
core, _, versions=load_runtime(ref)
with np.load(ref/'LP_plus45_bank.npz', allow_pickle=False) as bank:
    freqs=bank['freqs_hz']
def diagnose(case, index, path_index, row):
    entry, anchor_id, _, tasks, *_=case_inputs(p/'g0',p/'g7',case)
    scene_root=p/'g0/scene'
    scene, solver, setup=scene_runtime(core,entry,anchor_id,scene_root)
    task=tasks[index]
    trace,hits,nodes=trace_hits(core,scene,solver,f1['solver'],freqs,[0],task,setup,load_faces(scene,entry,scene_root))
    tx=entry['anchors_xyz_m'][anchor_id]
    rx=[task['x'],task['y'],entry['rx_z_m']]
    recorded_tx=np.asarray(scene.transmitters['tx'].position).reshape(3).astype(float).tolist()
    recorded_rx=np.asarray(scene.receivers['rx'].position).reshape(3).astype(float).tolist()
    path=hits[path_index]
    faces=[f for _,_,f,_ in path]
    image_delay, image_points=fold_images(tx,rx,faces)
    assert row[-1] is not None and row[0]=='>'.join(f.label for f in faces)
    check={'case':case,'task_id':index,'path_index':path_index,'x_y_m':rx[:2],'tx_m':tx,'rx_m':rx,
    'node':0,'replayed_native_delay_s':float(trace['tau'][path_index]),
    'trace_measured_delay_s':row[1],'infinite_plane_image_delay_s':image_delay,
    'abs_infinite_plane_delay_residual_s':abs(row[1]-image_delay),

    'vertices':[dict(face=f.label,primitive=i,triangle_m=triangle.vertices,native_point_m=point,
    image_point_m=image, vertex_displacement_m=dist(point,image),
    recorded_hit_in_primitive=triangle.contains(point,1e-5),
    exact_hit_in_face=any(t.contains(image,1e-9) for _,t in f.primitives))
    for (i,triangle,f,point),image in zip(path,image_points,strict=True)],
    'float32_tx_recorded_as_m':recorded_tx,'float32_rx_recorded_as_m':recorded_rx,
    'gate_error':row[-1], 'solver': f1['solver'], 'runtime':versions}
    return check

results = []
for path in sorted(Path('/run/traces').glob('*.jsonl')):
    for line in path.open():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        for path_index, row in enumerate(item['paths']):
            if row[-1] and 'Image hit outside the connected finite face' in row[-1]:
                results.append(diagnose(item['case'], item['task_id'], path_index, row))
print(json.dumps({'scope': 'node 0 diagnostics on completed finite-face failures', 'cases': results}, indent=2))

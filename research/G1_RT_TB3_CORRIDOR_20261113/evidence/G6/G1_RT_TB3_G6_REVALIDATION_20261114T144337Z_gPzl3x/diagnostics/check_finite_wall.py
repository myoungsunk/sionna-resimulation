import json
from math import dist
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
case, index, path_index='G-T2_C', 1025, 46
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
recorded_segments=[recorded_tx,*(pt for _,_,_,pt in path),recorded_rx]
trace_rows=[json.loads(l) for l in (Path('/run/traces')/'G-T2_C_08.jsonl').open()]
row=next(i for i in trace_rows if i['task_id']==index)['paths'][path_index]
assert row[-1] is not None and row[0]=='>'.join(f.label for f in faces)
check={'case':case,'task_id':index,'path_index':path_index,'x_y_m':rx[:2],'tx_m':tx,'rx_m':rx,
'node':0,'archived_canonical_native_delay_s':float(trace['tau'][path_index]),
'trace_measured_delay_s':row[1],'infinite_plane_image_delay_s':image_delay,
'abs_infinite_plane_delay_residual_s':abs(row[1]-image_delay),
'recess_boundary_distance_m':6.7-image_points[1][0],
'vertices':[dict(face=f.label,primitive=i,triangle_m=triangle.vertices,native_point_m=point,
image_point_m=image, vertex_displacement_m=dist(point,image),
recorded_hit_in_primitive=triangle.contains(point,1e-5),
exact_hit_in_face=any(t.contains(image,1e-9) for _,t in f.primitives))
for (i,triangle,f,point),image in zip(path,image_points,strict=True)],
'float32_tx_recorded_as_m':recorded_tx,'float32_rx_recorded_as_m':recorded_rx,
'gate_error':row[-1], 'solver': f1['solver'], 'runtime':versions}
print(json.dumps(check,indent=2))

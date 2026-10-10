import json,hashlib,pathlib,subprocess
p=pathlib.Path('/home/KMS/DRIVE_SIM_A23_Q2_JOINT_L2_20261010_01a12422');old=pathlib.Path('/home/KMS/DRIVE_SIM_A23_EXECUTION_20261010_01a12411')
sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
names=['A0_CHECK.json','A0_ARMS.csv','A0_UNIT_STATS.csv','ARMS_controls.csv','ARM_UNIT_STATS_controls.csv','ARMS_q1.csv','ARM_UNIT_STATS_q1.csv']
r={n:{'prior':sha(old/'OUTPUT'/n),'current':sha(p/'OUTPUT'/n),'unchanged':sha(old/'OUTPUT'/n)==sha(p/'OUTPUT'/n)} for n in names}
(p/'REUSE_PRESERVATION.json').write_text(json.dumps(r,indent=2));print('prior reuse files unchanged',all(x['unchanged'] for x in r.values()))
l=pathlib.Path('/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source/results/DRIVE_SIM_20261007/S4/LUT_LOS_CHECK.json')
if l.exists():
 (p/'LEGACY_L2_CHECK.json').write_bytes(l.read_bytes());d=json.loads(l.read_text());print('legacy L2',{k:v for k,v in d.items() if k!='rows'})

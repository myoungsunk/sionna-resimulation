"""Read-only original RF archive identity comparison; no simulation or fit."""
import hashlib,json,subprocess
from pathlib import Path
repo=Path(r'D:\SLAM_bot\DS_X1_X2_RESULTS_COMMIT_20261026')
source=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2')
prefix='results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/S2/'
remote='/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2'
raw=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','PasswordAuthentication=no','-o','ConnectTimeout=8','Snowball','sha256sum '+remote+'/H_R*_m*.npy'],text=True)
hashes={Path(line.split()[1]).name:line.split()[0] for line in raw.splitlines()}
read=lambda p:json.loads(subprocess.check_output(['git','-C',str(repo),'show','HEAD:'+p]))
rows=[]
for route,poses in [('R2',1303),('R4',922),('R5',1883)]:
    for anchor in ('A','B'):
        pair=[]
        for mount in (0,45):
            name=f'H_{route}_a{anchor}_m{mount}'
            man=read(prefix+name+'.manifest.json')
            assert man['config']['report']['complete'] and man['config']['report']['n_pose']==poses
            assert hashes[name+'.npy']==man['outputs'][0]['sha256']
            pair.append(man)
        assert pair[0]['inputs']==pair[1]['inputs']
        assert pair[0]['command'][pair[0]['command'].index('--traces')+1]==pair[1]['command'][pair[1]['command'].index('--traces')+1]
        rows.append(dict(case=f'{route}_a{anchor}_m45',poses=poses,remote_path=remote+f'/H_{route}_a{anchor}_m45.npy',sha256=hashes[f'H_{route}_a{anchor}_m45.npy'],original_manifest_match=True,same_pose_input_and_jones_trace_as_mount0=True,bytes=pair[1]['outputs'][0]['bytes']))
current=[]
full=source/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/FULL_RF'
for p in sorted(full.glob('H_*.npy')):
    actual=hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual==hashes[p.name]
    current.append(dict(file=p.name,sha256=actual,remote_archive_identical=True))
out=dict(status='ORIGINAL_ARCHIVE_REUSE_IDENTITIES_PASS',scope='12 remote RF files compared to original manifests, 7 current full RF files compared bytewise by SHA256; no new RF execution',available_mount45=rows,current_frozen_inputs=current,decision='Do not rerun RF simulation for the same original conditions. Recover five already generated H files. Generate missing features/OOF/MR/HG and current EKF traces separately; old S6 scores are a different estimator/sensor experiment.')
(Path(__file__).parent/'ASSESSMENT.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

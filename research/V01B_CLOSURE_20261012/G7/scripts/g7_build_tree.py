import json,hashlib,os,subprocess
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');G=S/'g7';BC=G/'input/BLOCK_C'
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C');DA=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()
M={c['case']:c for c in json.load(open(S/'matrix.json'))};old=json.load(open(G/'pub/CASES_7.json'));oldnames={c['case'] for c in old}
def link(dst,src):
    dst=Path(dst)
    if dst.exists() or dst.is_symlink():dst.unlink()
    dst.parent.mkdir(parents=True,exist_ok=True);os.symlink(src,dst)
link(BC/'freqs_hz.npy',FR/'freqs_hz.npy')
for r in ('R2','R4','R5'):
    raw=subprocess.check_output(['git','-C','/home/user/sionna-resimulation','show',f'origin/codex/abc-gated-resume-20261011:results/DRIVE_SIM_20261007/S1/routes/rf_poses_{r}.json'])
    (BC/'INPUTS').mkdir(parents=True,exist_ok=True);(BC/'INPUTS'/f'rf_poses_{r}.json').write_bytes(raw)
cases=[];prov={}
for c in old:
    n=c['case'];link(BC/'FULL_RF'/f'H_{n}.npy',FR/'FULL_RF'/f'H_{n}.npy');link(BC/f'H_LoS_{n}.npy',FR/f'H_LoS_{n}.npy');link(BC/n/'SAMPLES.json',FR/n/'SAMPLES.json');cases.append(c);prov[n]='existing (published inputs, unchanged)'
LOS=json.load(open(S/'los_gen_summary.json'));LOS={('R'+k if not k.startswith('R') else k):v for k,v in LOS.items()}
for n in ['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']:
    r=n[:2];anc=4.0 if n[3:5]=='aA' else 10.0
    full=DA/f'H_{n}.npy';los=S/'los_gen'/f'H_LoS_{n}.npy';assert sha(full)==M[n]['full_sha256'] and sha(los)==LOS[n]['sha256']
    link(BC/'FULL_RF'/f'H_{n}.npy',full);link(BC/f'H_LoS_{n}.npy',los);(BC/n).mkdir(parents=True,exist_ok=True);(BC/n/'SAMPLES.json').write_bytes((BC/'INPUTS'/f'rf_poses_{r}.json').read_bytes())
    sp=sha(BC/n/'SAMPLES.json');assert sp==M[n]['rf_pose_sha256']
    cases.append(dict(poses=M[n]['poses'],shape=[M[n]['poses'],257,2,2],layout='pose,frequency,rx(+45,-45),tx(+45,-45)',max_depth=0,mount_deg=45,anchor_xyz=[anc,0.0,2.6500000000000004],robot_z=0.45,
        H_sha256=sha(los),samples_sha256=sp,case=n,input_H_sha256=sha(full),input_rf_poses_sha256=sp,
        provenance='LoS H generated from the legacy trace LoS path (V01B_TRACE_REQUEST2 G4); full H delivered 2026-10-12 (V01B_DATA_REQUEST DELIVERY_A)'))
    prov[n]='NEW: full H delivered; LoS H generated from trace LoS path'
json.dump(cases,open(BC/'CASES.json','w'),indent=1);json.dump(prov,open(G/'case_provenance.json','w'),indent=1)
print(len(cases),'cases;',sum(1 for c in cases if c['case'] in oldnames),'existing +',sum(1 for c in cases if c['case'] not in oldnames),'new')

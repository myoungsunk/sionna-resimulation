import subprocess,tarfile,hashlib,json,sys,io
from pathlib import Path
B='origin/codex/abc-gated-resume-20261011';R='results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3'
OUT=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad/native5')
TARGET={'0169155f926bb27d4dbb4ba9ef5d3422e3ec96296ab6e593f81ecfaf43a575d5':'R2_aB_m45','2587edcdff11747ef78c8e370571fee6a78a6934cc83c29909d9515098ebab82':'R4_aA_m45',
        '3ac3dffb40b7730bc77ec2fa45e071a835aeffa53595387129eccbe168598226':'R4_aB_m45','55c886b6b1060bbf9bde9c1681ff9f926aee33e8cc0af62ad9e993625a7a6376':'R5_aA_m45',
        'd56b8168cac1f10632beeafff6e2ea8b6547831199519f26914bc27197d2ccf7':'R5_aB_m45'}
SIZES={21431872,15165184,30971712}
class Cat(io.RawIOBase):
    def __init__(s,paths):s.paths=iter(paths);s.buf=b'';s.pos=0
    def readable(s):return True
    def readinto(s,b):
        while s.pos>=len(s.buf):
            try:p=next(s.paths)
            except StopIteration:return 0
            s.buf=subprocess.check_output(['git','cat-file','blob',f'{B}:{p}']);s.pos=0
        n=min(len(b),len(s.buf)-s.pos);b[:n]=s.buf[s.pos:s.pos+n];s.pos+=n;return n
found={};log=[]
for a in ['RF_PRIORS_ARCHIVE','C_CORRECTION_ARCHIVE','PRE_CORRECTION_ARCHIVE','ADDITIONAL_CONTROLS_ARCHIVE']:
    if len(found)==5:break
    man=json.loads(subprocess.check_output(['git','show',f'{B}:{R}/{a}/PACKAGE_MANIFEST.json']))
    parts=[f"{R}/{a}/{p['file']}" for p in man['parts']]
    n=0
    with tarfile.open(fileobj=io.BufferedReader(Cat(parts),buffer_size=1<<20),mode='r|gz') as tar:
        for m in tar:
            if not (m.isfile() and m.name.endswith('.npy') and m.size in SIZES):continue
            n+=1;b=tar.extractfile(m).read();d=hashlib.sha256(b).hexdigest()
            if d in TARGET:
                c=TARGET[d];(OUT/f'H_{c}_native.npy').write_bytes(b);found[c]=dict(archive=a,member=m.name,sha256=d);print('FOUND',c,a,m.name,flush=True)
    log.append((a,n));print('scanned',a,'candidate npy',n,'found so far',list(found),flush=True)
(OUT/'FOUND.json').write_text(json.dumps(dict(found=found,scan=log),indent=1))
print('DONE',len(found),'of 5')

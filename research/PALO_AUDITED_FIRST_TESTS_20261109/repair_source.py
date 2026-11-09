#!/usr/bin/env python3
"""Auditable exact source patch after the original bundle is hash verified.
The R5 strict whole-history parity test failed with batch candidate arithmetic.
Use the canonical original scalar kernel for baseline/replay; keep the frozen
mathematical model and numerical tolerances. Mixture still separately audited.
"""
from pathlib import Path
import hashlib,json
p=Path('src/minimal_models.py');old=p.read_text()
helper='''def scalar_candidate(e,x,P,z):
    """Canonical original scalar kernel for exact long replay/checkpoint parity.
    Batched mixture updates remain separately checked step-by-step.
    """
    def obs(v):
        hh,JJ=e.scalar_lut.model(v,e.case)
        return hh[1:],JJ[1:]
    y,C,a=e.core.gaussian_update(x,P,np.array([z]),obs,np.array([[R]]))
    hh,JJ=obs(x);cl=e.observe(x)[2]
    return y,C,dict(h=float(hh[0]),H=JJ[0],nu=float(a['innovation'][0]),
        S=float(a['S'][0,0]),K=a['K'][:,0],step=a['K'][:,0]*a['innovation'][0],
        nis=float(a['NIS']),clip=bool(cl))

'''
new=old.replace('def run_baseline(e,u,z,x0,gate=GATE):',helper+'def run_baseline(e,u,z,x0,gate=GATE):')
assert new.count('y,C,d=e.candidate(x,P,float(z[k]))')==2
new=new.replace('y,C,d=e.candidate(x,P,float(z[k]))','y,C,d=scalar_candidate(e,x,P,float(z[k]))')
assert new!=old;p.write_text(new)
p=Path('src/audit_checks.py');s=p.read_text();t=s.replace("'run_baseline','run_mixture','replay','rts','predict','mix_moments','log_likelihood'","'run_baseline','run_mixture','replay','rts','predict','mix_moments','log_likelihood','scalar_candidate'")
assert t!=s;p.write_text(t)
p=Path('src/run_pretests.py');s=p.read_text();t=s.replace("'WITHDRAW_FRESH_XP_PARITY')","f'WITHDRAW_FRESH_XP_PARITY:{meta}:{start}:{sec}:{ex,ep,ek,pk}')")
assert t!=s;p.write_text(t)
expected={'minimal_models.py':'c086d5862ab1a847d10048c516628a25a8e7b3e86e1f59d26f058c77861f31c2','audit_checks.py':'c7451cc75eb465be0a17bd0fafb4ec5e888689293a104c80ca04a13f2b490384','run_pretests.py':'8310115076e33c268e0fcca7ad2a7a5e18adb6d4e6775f8a5174dede38c2c906','pipeline_io.py':'f64271f268b5aafcdb26fe23c2d505eff15dcc63a770081e2a84dd9c71ed2443'}
for name,digest in expected.items():
    actual=hashlib.sha256(Path('src',name).read_bytes()).hexdigest()
    assert actual==digest,('REPAIR_SOURCE_HASH_MISMATCH',name,actual,digest)
Path('REPAIR_SOURCE_RECEIPT.json').write_text(json.dumps({'source_hashes':expected,'changed_model_parameters':False,'changed_numerical_tolerances':False,'repair':'canonical scalar observation for baseline and checkpoint replay'},indent=2))
print('SCALAR_OBSERVATION_REPAIR_HASH_PASS')

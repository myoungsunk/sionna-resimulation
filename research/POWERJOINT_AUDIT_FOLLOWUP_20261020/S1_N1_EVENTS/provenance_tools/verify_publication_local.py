"""Read-only verification of the final S1 publication and preserved S0."""
from pathlib import Path
import base64,hashlib,json,sys
import numpy as np
import pandas as pd
sys.path.insert(0,r'D:/tmp')
from powerjoint_github import session,api
ROOT=Path(r'D:/tmp/sionna-powerjoint-followup-20261020')
PREFIX='research/POWERJOINT_AUDIT_FOLLOWUP_20261020'
HERE=ROOT/PREFIX/'S1_N1_EVENTS'
S0='d415075da8b97745611a1fcf1ffb4d2df57a40f2'

def main():
    s=session();head=api(s,'git/ref/heads/research/powerjoint-audit-followup-20261020')['object']['sha']
    commit=api(s,'git/commits/'+head)
    def subtree(commit_sha,path):
        cur=api(s,'git/commits/'+commit_sha)['tree']['sha']
        for part in path.split('/'):
            cur=next(x['sha'] for x in api(s,'git/trees/'+cur)['tree'] if x['path']==part)
        tree=api(s,'git/trees/'+cur,params={'recursive':1});assert not tree.get('truncated')
        return {path+'/'+x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob'}
    remote=subtree(head,PREFIX);checked=0
    for path in (ROOT/PREFIX).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        if path.suffix.lower() in ('.npz','.npy','.zip','.tar','.pkl','.pickle'):continue
        b=path.read_bytes();rel=path.relative_to(ROOT).as_posix()
        assert len(b)<=20_000_000
        assert remote.get(rel)==hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),rel
        checked+=1
    before=subtree(S0,PREFIX+'/S0_CORRECTIONS');after=subtree(head,PREFIX+'/S0_CORRECTIONS')
    assert before==after,'S0_CHANGED'
    assert subtree(S0,'research/POWERJOINT_AUDIT_RERUN_20261020')==subtree(head,'research/POWERJOINT_AUDIT_RERUN_20261020'),'ORIGINAL_AUDIT_CHANGED'
    summary_rel=PREFIX+'/00_SUMMARY_KO.md'
    old=base64.b64decode(api(s,'contents/'+summary_rel,params={'ref':S0})['content'])
    assert (ROOT/summary_rel).read_bytes().startswith(old),'S0_SUMMARY_CHANGED'
    index=json.loads((HERE/'OUTPUT_INDEX.json').read_text())
    for rel,meta in index['outputs'].items():
        b=(HERE/rel).read_bytes();assert len(b)==meta['bytes'] and hashlib.sha256(b).hexdigest()==meta['sha256'],rel
    assert hashlib.sha256((ROOT/summary_rel).read_bytes()).hexdigest()==index['root_summary_sha256']
    lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());prior=json.loads((HERE/'PROTOCOL_LOCK_V1.json').read_text())
    strip=lambda d:{k:v for k,v in d.items() if k not in ['version','amendment','implementation_sources_sha256']}
    assert strip(lock)==strip(prior)
    for rel,want in lock['implementation_sources_sha256'].items():
        assert hashlib.sha256((HERE/rel).read_bytes()).hexdigest()==want,rel
    table=pd.read_csv(HERE/'INTERVENTIONS.csv');assert len(table)==790
    assert not table.duplicated(['event','bias','arm']).any()
    assert table[table.arm!='D7'].status.eq('TECHNICAL_PASS').all()
    assert (table.label=='ORACLE_DIAGNOSTIC').all()
    metrics=lock['metrics'];valid=table[table.status=='TECHNICAL_PASS']
    assert np.isfinite(valid[metrics].to_numpy()).all()
    assert valid.scorer_max_abs_difference.max()<=1e-9
    for name in ['EVENT_TABLE.csv','EVENT_TABLE_L2.csv']:
        t=pd.read_csv(HERE/name);assert len(t)==79
        assert set(t.event)==set(pd.read_csv(HERE/'EVENT_LIST.csv').event)
        neutral=t[t.role=='NEUTRAL']
        assert neutral[[c for c in t if c.startswith(('r_','h_'))]].isna().all().all()
    d=json.loads((HERE/'DECISION.json').read_text());assert d['technical']=='TECHNICAL_PASS_CORE'
    assert d['scientific']=='NOT_ESTABLISHED'
    e=json.loads((HERE/'ERRORS.json').read_text());assert not e['execution_errors'] and not e['missing_event_arms']
    assert len(e['preserved_first_run_execution_errors'])==10
    receipt=json.loads((HERE/'MANIFEST.json').read_text())
    for r in receipt['canonical_artifacts']+receipt['preserved_failed_artifacts']:
        assert r['archive_sha256']==r['release_readback_sha256'] and r['archive_bytes']==r['release_readback_bytes']
    print(json.dumps(dict(final_commit=head,remote_blobs_byte_identical=checked,indexed_files_verified=len(index['outputs']),unchanged_S0_blobs=len(before),S0_summary_prefix_byte_identical=True,scientific_protocol_unchanged=True,common11_rows=len(valid),unavailable_D7_rows=len(table)-len(valid),scientific=d['scientific'],groups=d['groups']),ensure_ascii=False),flush=True)
if __name__=='__main__':main()

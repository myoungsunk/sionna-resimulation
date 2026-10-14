"""R3 source-bound audit of immutable four-failure GitHub artifact.

This stdlib audit runs before any numerical validation of the four saved
failures, never re-labels original FAIL, and does not calculate state estimates.
"""
import argparse,hashlib,json,os,zipfile
from pathlib import Path
from datetime import datetime,timezone

SHA='d25e96077a6b487fd0d90591362e141ee3908457808edf8688a7d3a480bad26b'
RUN='38526390416'
COMMIT='99be5e38f8b68d2ed441b75222d8ff599db40a52'
CASES=[
 ('straight','MAP3',55,'f8fd1d3f0ceeebfda3322ca8a03c3eddbeb663d1078e39db342c3ec23cf2bb55'),
 ('straight','MAP4',60,'77415d27128ba08ba193bab632fed98a858aeec530f64d0963c2331e5e080dd2'),
 ('turn','MAP3',63,'ea1298400b662769466fc3219c3ec8ad32be3a9da3119e0af855e7bfafd3755a'),
 ('return','MAP3',63,'b43db01f7bbc59cd2f27a553c2841173392342416b4a609001c2abecae96f16c')
]
def sha(b):return hashlib.sha256(b).hexdigest()
def base(route,model):
 return '_temp/p2_preflight/trials/'+route+'/0.05/000/'+model+'/'

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--archive',required=True,type=Path)
 ap.add_argument('--source-audit',required=True,type=Path)
 ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('GitHub Actions required')
 folder=a.out.resolve();folder.mkdir(parents=True,exist_ok=False)
 src=json.loads(a.source_audit.read_text())
 reasons=[]
 if not(src.get('decision')=='GO' and src.get('git_sha')==os.getenv('GITHUB_SHA')):reasons.append('SOURCE_AUDIT')
 blob=a.archive.read_bytes()
 if sha(blob)!=SHA:reasons.append('ARCHIVE_SHA256')
 try:
  with zipfile.ZipFile(a.archive) as archive:
   if archive.testzip() is not None:reasons.append('ZIP_CRC')
   run=json.loads(archive.read('_temp/p2_preflight/FINAL.json'))
   if str(run.get('run_id'))!=RUN or run.get('commit')!=COMMIT:reasons.append('PROVENANCE')
   if run.get('invalid_model_cases')!=4:reasons.append('FAILURE_COUNT')
   for route,model,k,expected in CASES:
    data=archive.read(base(route,model)+'FAILED_STEP.npz')
    f=json.loads(archive.read(base(route,model)+'FAILURE.json'))
    if sha(data)!=expected:reasons.append('FAILURE_SHA_'+route+'_'+model)
    if f.get('step')!=k or f.get('model')!=model or f.get('solver_status')!='LINE_SEARCH_FAILED':reasons.append('FAILURE_CELL_'+route+'_'+model)
 except Exception as e:reasons.append('INPUT_ARCHIVE_PARSE_'+type(e).__name__+':'+str(e))
 r={'stage':'R3_ARCHIVED_INPUT_AUDIT','git_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
    'timestamp_utc':datetime.now(timezone.utc).isoformat(),'source_receipt_sha256':sha(a.source_audit.read_bytes()),
    'archive_sha256':sha(blob),'cases':len(CASES),
    'decision':'GO' if not reasons else 'HOLD','reasons':reasons,
    'scope':'four saved synthetic solver inputs only','scientific_PASS':False}
 (folder/'ARCHIVE_AUDIT.json').write_text(json.dumps(r,indent=2)+'\n')
 print('R3_INPUT_AUDIT '+json.dumps(r),flush=True)
 return 0 if not reasons else 2
if __name__=='__main__':raise SystemExit(main())

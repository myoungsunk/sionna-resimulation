import hashlib,json,subprocess,zipfile,datetime
from pathlib import Path
R=Path('/home/KMS/codex_runs/DLP-ANCHORB-8ARM-20261102/run_v1/work')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((R/'EXECUTION_LOCK.json').read_text())
bad=[k for k,v in lock['source_sha256'].items() if sha(R/'repo'/k)!=v]
assert not bad,bad
assert sha(R/'input/anchor_b_frozen.zip')==lock['archive_sha256']
job=json.loads((R/'out/replay/FINAL.json').read_text())
score=json.loads((R/'out/score/FINAL.json').read_text())
assert job['status']=='RUN_COMPLETED' and score['experiment_status']=='COMPLETED'
image=json.loads(subprocess.check_output(['docker','image','inspect','python:3.11.11']).decode())[0]
receipt={'question_id':'DLP-ANCHORB-8ARM-20261102','execution_id':'snowball-anchor-b-run-v1-20261102',
    'status':'COMPLETED','scientific_PASS':False,'post_run_source_and_input_hashes':'PASS',
    'image_id':image['Id'],'image_repo_digests':image['RepoDigests'],
    'remote_account':subprocess.check_output(['id','-un']).decode().strip(),
    'remote_host':subprocess.check_output(['hostname']).decode().strip(),
    'remote_workdir':str(R),'upstream_commit':lock['upstream_commit'],'local_patch':True,
    'execution_lock_sha256':sha(R/'EXECUTION_LOCK.json'),'run_script_sha256':sha(R/'run_snowball.sh'),
    'replay_finished_utc':job['finished_utc'],'score_finished_utc':score['created_utc'],
    'receipt_created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(R/'out/EXECUTION_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
out=R.parent/'AnchorB_8arm_Results_v1.zip'
with zipfile.ZipFile(str(out),'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((R/'out').rglob('*')):
        if p.is_file():z.write(str(p),str(p.relative_to(R/'out')))
    for name in ['CONTRACT.json','EXECUTION_LOCK.json','FROZEN_BASE.json','ACQUISITION_CHECK.json','PREFLIGHT_LOCAL.json','run_snowball.sh','RUN_PACKAGE_HASHES.json']:
        z.write(str(R/name),'run_metadata/'+name)
print(json.dumps({'zip':str(out),'sha256':sha(out),'bytes':out.stat().st_size}))

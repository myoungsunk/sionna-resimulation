"""Finalize provenance without rerunning or promoting the failed experiment."""
import json,subprocess,py_compile,sys
from datetime import datetime,timezone
import h3_offline as h
from run_full import load_caches
root=h.ROOT
for source in root.glob('*.py'):py_compile.compile(str(source),doraise=True)
p0=json.loads((root/'GATES_02/VERIFIED_INPUTS.json').read_text())['p0']
_,cache=load_caches(p0)
manager='C:/Users/Myoungsun Kim/.codex/skills/managed-processes/scripts/manager.py'
resources=['51b8915c-e2ff-45e6-8a18-23dc5e6db0be','73012978-e9a6-4f48-833a-958d3fae5518','57f6318f-81d9-4a18-bde8-f57c3d4838da','8d1ea5c7-f3fa-410f-80b5-cca075a51369','a95969d8-6737-4636-a287-c3ae072cf771']
processes=[]
for identity in resources:
    r=json.loads(subprocess.check_output([sys.executable,'-X','utf8',manager,'status','--id',identity],text=True))['processes'][0]
    if r['ref_count'] or r['actual_process']['state']!='absent' or r['actual_supervisor']['state']!='absent' or r['job']['state']!='absent':raise RuntimeError('Unsettled helper '+identity)
    processes.append(dict(id=identity,run_id=r['creator'],exit_code=r['exit_code'],termination=r['termination'],ref_count=r['ref_count'],log_dir=r['log_dir'],actual_process=r['actual_process']['state'],actual_supervisor=r['actual_supervisor']['state'],job=r['job']['state']))
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=h.REPO,text=True).strip()
dirty=subprocess.check_output(['git','status','--porcelain'],cwd=h.REPO,text=True).strip()
if revision!=h.C['base_commit'] or dirty:raise RuntimeError('Original checkout state changed')
receipt=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),overall='FAIL_CLOSED_SPATIAL_HOLDOUT',full_experiment='INCOMPLETE',scientific_PASS=False,recursive_fusion='NOT_RUN',frozen_contract_sha256=h.c.file_sha(root/'CONTRACT.json'),final_source_sha256={p.name:h.c.file_sha(p) for p in root.glob('*.py')},summary_sha256=h.c.file_sha(root/'SUMMARY_KO.md'),source_syntax='PASS',repository_revision=revision,repository_clean=True,frozen_blobs=h.c.check_frozen_baseline_files(),cache_sha256=cache['sha256'],processes=processes,gates=json.loads((root/'GATES_02/VALIDATION_RECEIPT.json').read_text()),D0_parity=json.loads((root/'AUDIT_02/VALIDATION_RECEIPT.json').read_text()),whole_experiment_attempt=json.loads((root/'FULL_01/VALIDATION_RECEIPT.json').read_text()))
h.c.atomic_json(root/'FINAL_VALIDATION_RECEIPT.json',receipt)
print(json.dumps({k:receipt[k] for k in ('overall','full_experiment','scientific_PASS','recursive_fusion','repository_clean','source_syntax')},indent=2))

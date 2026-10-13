"""Capture I2 execution provenance and failure logs without changing frozen data."""
from pathlib import Path
import sys, subprocess, datetime, json, hashlib, platform
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def run():
    receipt=HERE/'out/I2_EXECUTION_RECEIPT.json'
    if receipt.exists(): raise RuntimeError('Existing receipt; use a new run wrapper/output')
    output=HERE/'out/i2_run_01'
    command=[sys.executable,str(HERE/'i2_ideal_range_calibration.py'),'--out',str(output)]
    record=dict(start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,platform=platform.platform(),python=sys.version,thread_id=__import__('os').environ.get('CODEX_THREAD_ID'),local_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),remote_base='07dadb0ba165cc9d03c7ccb4c5fd3334bbe51b1f',note='Local HEAD older than published working files; content hashes authoritative')
    # Verify pre-existing I0/I1 dependencies against the published handoff commit.
    comparisons={}
    for name in ['i0_build_paired_inputs.py','replay.py','I0_RUN_SPEC.json','i1_model.py','I1_SPEC.json','out/i1_run_01/I1_GATE.json']:
        p=HERE/name
        blob=subprocess.check_output(['git','show',record['remote_base']+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
        comparisons[name]=hashlib.sha256(blob).hexdigest()==hashlib.sha256(p.read_bytes()).hexdigest()
    record['handoff_matches']=comparisons
    if not all(comparisons.values()): raise RuntimeError('handoff mismatch')
    record['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'i2_ideal_range_calibration.py',HERE/'i2_batch.py',HERE/'out/I2_DESIGN.json',Path(__file__)]}
    receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
    with (HERE/'out/I2_EXECUTION.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    record.update(end=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=result.returncode)
    receipt.write_text(json.dumps(record,indent=2),encoding='utf-8')
    raise SystemExit(result.returncode)

if __name__=='__main__': run()

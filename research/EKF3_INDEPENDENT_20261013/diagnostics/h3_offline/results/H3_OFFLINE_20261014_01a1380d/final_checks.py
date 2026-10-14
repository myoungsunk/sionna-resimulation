"""Verify DR reproduction without bypassing the failed spatial training gate."""
import json,sys,time,traceback
from datetime import datetime,timezone
import h3_offline as h
import run_full as r
out=h.ROOT/(sys.argv[1] if len(sys.argv)>1 else 'AUDIT_01');out.mkdir(exist_ok=False);start=time.time()
try:
    p0=json.loads((h.ROOT/'GATES_01/VERIFIED_INPUTS.json').read_text())['p0']
    caches,im=r.load_caches(p0)
    _,rows=r.prepare_priors(p0,caches,out)
    h.c.atomic_json(out/'VALIDATION_RECEIPT.json',dict(status='PASS',check='D0_ALL_REQUESTED_PRIORS',prior_cells=len(rows),reference_cells=len(rows)*len(h.C['RF_pairs']),max_absolute_difference=max(x['parity_max_abs'] for x in rows),tolerance=h.C['parity_absolute_tolerance'],elapsed_s=time.time()-start,scientific_PASS=False,full_experiment='BLOCKED_SPATIAL_HOLDOUT',recursive_fusion='NOT_RUN'))
except Exception as exc:
    h.c.atomic_json(out/'VALIDATION_RECEIPT.json',dict(status='FAIL_CLOSED',error=str(exc),elapsed_s=time.time()-start,scientific_PASS=False));traceback.print_exc();sys.exit(1)

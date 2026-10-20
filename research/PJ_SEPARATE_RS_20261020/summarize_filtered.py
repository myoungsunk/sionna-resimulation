#!/usr/bin/env python3
"""Postprocessing-only filename filtering correction; no scientific replay changes.
Replay artifact wildcard also retains identical MEASUREMENT_SCORES.csv copies.
Only case-level R2/R4/R5 scores belong in the 28-trace aggregate.
"""
from pathlib import Path
import os,hashlib,json
root=Path(os.environ['PJ_OUT']);copies=list(root.rglob('MEASUREMENT_SCORES.csv'))
hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in copies};assert len(hashes)==1,('MEASUREMENT_COPIES_DIVERGE',hashes)
p=Path(__file__).with_name('summarize.py');text=p.read_text();old="files=sorted(root.rglob('*_SCORES.csv'))";new="files=sorted(p for p in root.rglob('*_SCORES.csv') if p.name.startswith(('R2_', 'R4_', 'R5_')))"
assert text.count(old)==1;text=text.replace(old,new)
(root/'POSTPROCESS_ONLY_FIX.json').write_text(json.dumps({'reason':'duplicate copied measurement summaries excluded from recursive file count','original_summary_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_summary_sha256':hashlib.sha256(text.encode()).hexdigest(),'measurement_duplicate_copies':len(copies),'duplicate_hashes_identical':True,'measurement_training_and_EKF_changed':False},indent=2))
(root/'ACTUAL_SUMMARY_EXECUTED.py').write_text(text)
exec(compile(text,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})

#!/usr/bin/env python3
"""Static offline implementation verification. No fetch, fit, replay, or RF evaluation."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REQUIRED=['freeze_input_contract.py','tests/test_freeze_input_contract.py','corridor_control.py','tests/test_corridor_control.py','evidence_contract.py','tests/test_evidence_contract.py','tests/test_t2_integration.py',
          'tests/evidence_helpers.py','tests/fixtures/p2_math.py','tests/fixtures/t2_prepare_inputs.py',
          'tests/fixtures/t2_receipt_index.py','runtime_contract.py','tests/test_runtime_contract.py','office_transfer_core.py','office_transfer_cli.py','lock.json','README_KO.md',
          'requirements.txt','tests/test_core.py']
for name in REQUIRED:
    p=ROOT/name
    if not p.is_file():raise FileNotFoundError('MISSING:'+name)
for name in (n for n in REQUIRED if n.endswith('.py')):
    ast.parse((ROOT/name).read_text(encoding='utf-8'),filename=str(ROOT/name))
lock=json.loads((ROOT/'lock.json').read_text(encoding='utf-8'))
assert set(lock['paths'])=={'O01','O02','O03'}
assert sum(lock['paths'][r]['rf_n'] for r in lock['paths'])==811
assert lock['source_los_model_max_abs_tol']==0.05
assert len(lock['source_audit_commit'])==40 and len(lock['corridor_p2_commit'])==40
for route,c in lock['paths'].items():
    assert len(c['archive_sha256'])==64
    assert all(len(x)==64 for x in c['files'].values())
print('STATIC_PACKAGE_QA_PASS',json.dumps({
  'files':len(REQUIRED), 'source_routes':list(lock['paths']),
  'rf_rows':811,'scope':'AST_HASH_SHAPE_NO_RF_NO_TRAIN_NO_REPLAY',
  'sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in REQUIRED}
},ensure_ascii=False))

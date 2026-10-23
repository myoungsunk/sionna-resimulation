"""Implementation audit only. It cannot produce an RF experiment PASS receipt."""
from __future__ import annotations
from pathlib import Path
import ast
import io
import contextlib
import importlib.metadata
import unittest
from .common import code_hash,write_json,read_json,require,REFERENCE_SHA,file_hash


def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item.id()


def audit(ws):
    root=Path(__file__).parent
    checks=[]
    for file in sorted(root.rglob('*.py')):
        tree=ast.parse(file.read_text(encoding='utf-8'),filename=str(file));compile(tree,str(file),'exec')
        checks.append(dict(file=str(file.relative_to(root)),check='syntax',status='PASS'))
        if file.name in ('runtime_features.py','replay.py','numerics.py','common.py'):
            imports=[getattr(n,'module','') or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            require(not any('oracle_scoring' in m or 'training' in m for m in imports),'Runtime truth/training import boundary violated')
            checks.append(dict(file=file.name,check='runtime_import_boundary',status='PASS'))
    required=['run_s0','run_s1','run_s2','run_s3','run_s4','run_s5','run_s6','run_s7']
    tree=ast.parse((root/'stages.py').read_text());defined={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    require(set(required)<=defined,'Missing executable stage')
    suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py');names=list(flatten(suite))
    require(len(names)>=60,'Contract suite incomplete')
    manifest=read_json(root/'manifest.json')
    require(manifest['frozen_reference_sha']==REFERENCE_SHA,'Protocol reference mismatch')
    coverage=[]
    require({r['id'] for r in manifest['requirement_coverage']}=={f'R{i:02d}' for i in range(1,21)},'Required R01--R20 coverage incomplete')
    for row in manifest['requirement_coverage']:
        missing=[test for test in row['tests'] if not any(name.endswith('.'+test) for name in names)]
        require(not missing,f"Missing required tests for {row['id']}: {missing}")
        coverage.append({**row,'test_discovery_status':'PASS'})
    launcher=root.parents[1]/'scripts/base_rf_identifiability_v2.py'
    require(launcher.is_file(),'CLI launcher missing')
    compile(ast.parse(launcher.read_text(encoding='utf-8')),str(launcher),'exec')
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    out=ws.root/'AUDIT';out.mkdir(parents=True,exist_ok=True);(out/'UNIT_TEST_LOG.txt').write_text(stream.getvalue(),encoding='utf-8')
    versions={x:importlib.metadata.version(x) for x in ('numpy','scipy','pandas','scikit-learn','joblib')}
    passed=result.wasSuccessful() and not result.skipped
    report=dict(status='PASS' if passed else 'QA_FAIL',scope='implementation and synthetic contracts only',reference_sha=REFERENCE_SHA,
                code_sha256=code_hash(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                tests=names,static_checks=checks,requirement_coverage=coverage,launcher_sha256=file_hash(launcher),environment=versions,rf_experiments_executed=False,real_data_model_training_executed=False,
                native_SourceFFD_integration='NOT_RUN; S0 remains mandatory with original assets',stages_implemented=required)
    write_json(out/'IMPLEMENTATION_AUDIT.json',report)
    if passed:ws.finish('AUDIT',rf_experiments_executed=False,tests_run=result.testsRun,native_integration='NOT_RUN')
    else:ws.receipt('AUDIT','QA_FAIL',tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors))
    print(f"IMPLEMENTATION_AUDIT {report['status']}: {result.testsRun} tests, RF executions=0, real-data training=0")
    return 0 if passed else 1

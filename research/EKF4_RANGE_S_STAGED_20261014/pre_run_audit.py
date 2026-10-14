"""PRE-RUN audit of exact source, input contract and diagnostic API assumptions.

Read-only audit *before* any validation, diagnosis or experiment code.
Not an external/independent peer review, and not a scientific result.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = {
    'P2_SPEC.json': '548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7',
    'synthetic.py': 'c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643',
}
CODES = (
    'core.py', 'stable_descent.py', 'synthetic.py', 'validate.py',
    'test_core.py', 'test_solver_regression.py', 'test_solver_r2.py',
    'solver_regression.py', 'record_r2.py', 'p2_v2.py',
    'pre_run_audit.py', 'conftest.py', 'diagnose.py', 'diagnose_resume.py', 'r3_four_regression.py'
)
DOCS = ('P2_SPEC.json', 'FAILURE_SNAPSHOT.json', 'RESUME_FAILURE_SNAPSHOT.json',
        'P2_V2_PREEXECUTION_CONTRACT_KO.md', 'P2_V2_CHANGE_RECONCILIATION.json')
VARIABLE_BRANCH_LOG = {'curvature_ratio', 'gradient_integral_difference',
                       'step_acceptance', 'gradient_new_inf',
                       'direct_cost_difference'}
AUDIT_DECISION = ('verify raw input identity, estimator truth isolation and '
                  'test API contract before P2 validation/execution')


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def source_truth_check(root):
    """Review the one frozen estimator entrypoint's AST for truth leakage."""
    funcs = [a for a in root.body if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))]
    target = next(a for a in funcs if a.name == 'run_model')
    parents = {}
    for node in ast.walk(target):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    labels = []
    for node in ast.walk(target):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'data' and isinstance(node.slice, ast.Constant)
                and node.slice.value == 'truth'):
            par = parents.get(node)
            valid = isinstance(par, ast.Call) and isinstance(par.func, ast.Name) and par.func.id == 'score'
            labels.append({'line': node.lineno, 'used_for_scoring_only': valid})
    return labels, bool(labels) and all(v['used_for_scoring_only'] for v in labels)


def branch_telemetry_assumptions(root):
    """Flag unguarded direct indexing of optional fields in regression code.

    This is narrow source checking for the exact R1/R2 incident, not proof
    that every possible branch is safe.
    """
    issues = []
    for node in ast.walk(root):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value not in VARIABLE_BRANCH_LOG:
                continue
            # Test/API-level access through ['optional'] is fragile unless
            # branch instrumentation specifically forces the target branch.
            if isinstance(node.value, ast.Name) and node.value.id in ('first', 'history', 'step'):
                issues.append({'line': node.lineno, 'field': node.slice.value})
    return issues


def require_audit_receipt(audit_path):
    """One scoped, source-bound audit receipt is required before ANY tests.

    It is not an independent scientific audit. Later stages only trust
    a receipt from this exact commit with current source digests.
    """
    if os.getenv('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Tests/diagnosis require GitHub Actions and pre-run audit')
    if not audit_path:
        raise RuntimeError('Missing required pre-run audit receipt')
    a = json.loads(Path(audit_path).read_text(encoding='utf-8'))
    if a['decision'] != 'GO' or a['git_sha'] != os.getenv('GITHUB_SHA'):
        raise RuntimeError('Pre-run audit status/source commit mismatch')
    for name,expected in a['source_sha256'].items():
        if digest(HERE/name) != expected:
            raise RuntimeError('Source changed since pre-run audit: '+name)
    workflow=REPO/'.github/workflows/ekf4-range-s-staged.yml'
    if a['workflow_sha256'] != digest(workflow):
        raise RuntimeError('Workflow changed since pre-run audit')
    return a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['preflight','full'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.getenv('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('This audit must run before tests on GitHub Actions.')
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        'schema': 'EKF4_PRE_RUN_AUDIT_V2',
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'git_sha': os.environ.get('GITHUB_SHA'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'stage': args.phase,
        'decision_sentence': AUDIT_DECISION,
        'audit_type': 'read-only static source/contract audit prior to execution',
        'independent_peer_audit': False,
        'scientific_PASS': False,
        'decision': 'HOLD',
        'fatal_findings': [], 'warnings': [], 'source_sha256': {},
        'reused_evidence': [
            'P0/P1 proof: run 38519821321 and historical R1 tests',
            'D1: run 38514766913, D2: run 38519216213',
        ],
        'next_stages_if_pass': ['P0/P1', 'R1/R2 fixed-input regression', args.phase + ' P2'],
        'execution_budget': {
            'preflight': '6 route/bias cells x first paired trial x 4 estimator models',
            'full': 'frozen 3 routes x 2 biases x 100 trial x 4 models',
        },
    }
    errors = report['fatal_findings']
    try:
        for name in (*CODES, *DOCS):
            path = HERE/name
            if not path.is_file():
                errors.append({'id': 'MISSING_INPUT', 'path': name, 'affects': 'this run'})
            else:
                report['source_sha256'][name] = digest(path)
        if not errors:
            for name, expected in FROZEN.items():
                if report['source_sha256'][name] != expected:
                    errors.append({'id': 'FROZEN_SOURCE_MISMATCH', 'path': name,
                                   'expected_sha256': expected, 'actual_sha256': report['source_sha256'][name]})
            reconcile = json.loads((HERE/'P2_V2_CHANGE_RECONCILIATION.json').read_text())
            ids = {x['id'] for x in reconcile['items']}
            if len(reconcile['items']) != 51 or len(ids) != 51:
                errors.append({'id':'AUDIT_51_COVERAGE_INCOMPLETE'})
            config = json.loads((HERE/'P2_SPEC.json').read_text())
            if not (config['models'] == ['EKF3','EKF4','MAP3','MAP4']
                    and config['paths'] == ['straight','turn','return']
                    and config['true_bias_dps'] == [0.0,0.05]
                    and config['trials_per_path_bias'] == 100
                    and config['MAP_gradient_tol'] == 1e-8):
                errors.append({'id':'FROZEN_P2_CONTRACT_MUTATED'})
            snap1 = json.loads((HERE/'FAILURE_SNAPSHOT.json').read_text())
            snap2 = json.loads((HERE/'RESUME_FAILURE_SNAPSHOT.json').read_text())
            if not (snap1['source_run_id'] == 38514443823 and
                    snap2['source_run_id'] == 38518908286 and
                    snap1['recorded_status'] == snap2['recorded_status'] == 'LINE_SEARCH_FAILED'):
                errors.append({'id':'FAILURE_FIXTURE_INTEGRITY'})
            parsed = {}
            for name in CODES:
                parsed[name] = ast.parse((HERE/name).read_text(), filename=name)
            labels, safe = source_truth_check(parsed['synthetic.py'])
            report['estimator_truth_access'] = labels
            if not safe:
                errors.append({'id':'TRUTH_LEAKAGE_IN_FROZEN_ESTIMATOR_ENTRY'})
            for name in ('test_solver_regression.py','test_solver_r2.py'):
                fragile = branch_telemetry_assumptions(parsed[name])
                if fragile:
                    errors.append({'id':'UNCONDITIONAL_BRANCH_TELEMETRY','path':name,'cases':fragile})
            # All source-like test scripts are audited even when unchanged.
            required = {'generate','run_model'}
            defined = {node.name for node in parsed['synthetic.py'].body
                       if isinstance(node, ast.FunctionDef)}
            if not required.issubset(defined):
                errors.append({'id':'ORIGINAL_SYNTHETIC_RUNNER_ENTRY_MISSING'})
            v2_defined = {node.name for node in parsed['p2_v2.py'].body
                          if isinstance(node, ast.FunctionDef)}
            if not {'run_phase','main'}.issubset(v2_defined):
                errors.append({'id':'P2_RUNNER_ENTRY_MISSING'})
            workflow = (REPO/'.github/workflows/ekf4-range-s-staged.yml').read_text()
            first = workflow.find('python research/EKF4_RANGE_S_STAGED_20261014/pre_run_audit.py')
            test = workflow.find('python research/EKF4_RANGE_S_STAGED_20261014/validate.py')
            exp = workflow.find('python research/EKF4_RANGE_S_STAGED_20261014/p2_v2.py')
            if not (first >= 0 and first < test < exp):
                errors.append({'id':'AUDIT_NOT_FIRST_IN_WORKFLOW'})
            report['workflow_sha256'] = digest(REPO/'.github/workflows/ekf4-range-s-staged.yml')
            report['warnings'].append({
                'id':'PRE_RUN_AUDIT_IS_STATIC_NOT_INDEPENDENT_PROOF',
                'scope':'LUT, measured multipath, numerical optimality and scientific claims remain unverified'
            })
            report['warnings'].append({
                'id':'ROUTE_EFFECTS_NOT_GLOBAL_EXECUTION_GATES',
                'scope':'all-three-CI requirement applies only to the all-paths-support claim'
            })
        report['decision'] = 'GO' if not errors else 'HOLD'
    except Exception as exc:
        errors.append({'id':'AUDIT_IMPLEMENTATION_ERROR','type':type(exc).__name__,'message':str(exc)})
        report['decision'] = 'HOLD'
    report['next_scientific_claim'] = 'NOT_EVALUATED'
    report['exit_code'] = 0 if report['decision'] == 'GO' else 2
    (output/'PRE_RUN_AUDIT.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print('PRE_RUN_AUDIT '+json.dumps({k:report[k] for k in
           ('git_sha','stage','decision','fatal_findings','warnings','exit_code')},ensure_ascii=False),flush=True)
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())

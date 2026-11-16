"""Reproduce the frozen R2/R5 memory and range switches on the +45 B/B0 inputs."""

import argparse
from pathlib import Path
import sys
import types

from run_followup_mount45 import LOCK as FOLLOWUP_LOCK, OUT as FOLLOWUP, load_module
from run_ks_mount45 import DIAG, LOCK as KS_LOCK, OUT as KS, ROOT, check, receipt, role_receipt, source


TEMPLATE = DIAG / 'continuation_checks_c1_c8/r2_r5_failure/run_failure.py'
OUT = ROOT / 'r2_r5'
LOCK = OUT / 'RUN_CONTRACT.json'


def bind():
    previous = load_module()
    sys.modules['run_followup'] = previous
    module = types.ModuleType('r2_r5_failure_bound')
    path = OUT / 'run_r2_r5_bound.py'
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), vars(module))
    module.LOCK, module.OUT = LOCK, OUT / 'execution'
    module.C4 = module.C5 = FOLLOWUP / 'execution'
    module.QUESTION = 'G1-INT-001/KS-R2-R5-FAILURE/M45-B-B0'
    return module


def freeze():
    paths = role_receipt(FOLLOWUP / 'execution', FOLLOWUP_LOCK)
    ks_inputs = role_receipt(KS / 'execution', KS_LOCK)
    applied_c4 = FOLLOWUP / 'execution/C4.json' in paths
    if applied_c4:
        assert FOLLOWUP / 'execution/C4_R2_directional.npz' in paths
    OUT.mkdir()
    clone = OUT / 'run_r2_r5_bound.py'
    text = TEMPLATE.read_text(encoding='utf-8').replace('mount 0', 'mount +45')
    if not applied_c4:
        text = text.replace('        c4 = read(C4 / "C4.json")', '        c4 = None')
        text = text.replace('            if route == "R2":', '            if route == "R2" and c4 is not None:')
    with clone.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    module = bind()
    source.write(LOCK, {'question': module.QUESTION, 'role': 'IMPLEMENTER', 'frozen_utc': source.utc(),
        'source': receipt(clone), 'rules': module.RULES, 'c4_applies': applied_c4,
        'governance': source.load(FOLLOWUP_LOCK)['governance'],
        'inputs': list(map(receipt, (Path(__file__), TEMPLATE, FOLLOWUP_LOCK, KS_LOCK, *paths, *ks_inputs)))})


def run():
    lock = source.load(LOCK)
    for pin in [lock['source'], *lock['governance'], *lock['inputs']]:
        check(pin)
    bind().run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()

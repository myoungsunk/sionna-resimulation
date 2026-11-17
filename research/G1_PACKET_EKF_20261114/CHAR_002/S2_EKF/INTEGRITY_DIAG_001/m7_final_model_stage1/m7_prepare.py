"""M7 actual evidence preparation; every phase writes new immutable evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

import numpy as np

from m7_h5prime import execute_h5_prime
from m7_inputs import KEYS, arrays, checked, generate_inputs
from m7_spec import PLAN_COMMIT, PLAN_SHA256, ROUTES, expected_cells, execution_policy

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
ART = Path('D:/SLAM_bot/artifacts')
M6 = ART / 'G1_GM_THETA_M6_20261116'
CHAR = M6 / 'characterization/RUN_CONTRACT.json'
GOV_HASHES = {'COMMON_CONTRACT.md': 'a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb',
              'ROLE_IMPLEMENTER.md': '2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def item(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def check_records(node):
    if isinstance(node, dict):
        if {'path', 'sha256'} <= node.keys():
            checked(node)
        else:
            for value in node.values():
                check_records(value)
    elif isinstance(node, list):
        for value in node:
            check_records(value)


def provenance():
    repo = next(p for p in ROOT.parents if (p / '.git').exists())
    plan = item(BASE / 'PLAN_M7_FINAL_MODEL_STAGE1_KO.md')
    if plan['sha256'] != PLAN_SHA256:
        raise ValueError('Plan differs from the published revised M7 plan')
    plan['commit'] = PLAN_COMMIT
    gov = [item(BASE / 'gm_theta_m6/inputs' / name) for name in GOV_HASHES]
    if any(row['sha256'] != GOV_HASHES[Path(row['path']).name] for row in gov):
        raise ValueError('Frozen governance version differs')
    return dict(study='G1-INT-001/M7-STAGE1', role='IMPLEMENTER', frozen_utc=utc(), plan=plan,
                scope=dict(anchor='B', mount_deg=0., rf='Full', bias='B0', routes=list(ROUTES)),
                branch='research/g1-sweep-heading-floor-spec-20261113',
                git=dict(repository=str(repo), head=subprocess.check_output(
                    ['git','-C',str(repo),'rev-parse','HEAD'], text=True).strip(),
                    dirty=bool(subprocess.check_output(['git','-C',str(repo),'status','--porcelain'], text=True)),
                    working_sources_hashed=True), governance=gov,
                sources=[item(p) for p in sorted(ROOT.glob('*.py'))],
                continuations={'G-T2/G-V':'SEALED', 'S2′':'STOP', 'Step 3':'HOLD'},
                authorization_basis='User: 검증 ㄱㄱ; M7 offline validation only')


def prepare(out):
    if out.exists():
        raise FileExistsError('Use a fresh M7 attempt; preserve old evidence')
    lock = read(CHAR)
    check_records(lock['model_assets'])
    check_records(lock['cells'])
    check_records(lock['d3'])
    check_records(lock['online_packets'])
    d5 = ART / 'G1_INT_DIAG_001_20261115/attempt_02/d5'
    folds = read(d5 / 'FOLDS.json')
    receipt = read(d5 / 'EXECUTION.json')
    if receipt['outputs']['FOLDS.json'] != item(d5/'FOLDS.json')['sha256']:
        raise ValueError('D5 sigma_b output differs from its receipt')
    for cell in lock['cells']:
        values = [k['sigma_b'] for k in folds[cell['route']]['knots']]
        if cell['sigma_b'] != values:
            raise ValueError('Inherited sigma_b differs from D5')
    parameters = BASE/'gm_theta_m6/characterization/K1_PRIME_K2.json'
    if item(parameters)['sha256'] != '507db95ab5368aa46ff1f1d1cef819904ec163819b0dde99a2b150f4a6bbf672':
        raise ValueError('M6 frozen parameter hash differs')
    out.mkdir(parents=True)
    stage = out/'input_generation'
    stage.mkdir()
    contract = provenance()
    contract.update(execution_policy())
    contract.update(status='FROZEN_INPUT_GENERATION', authorization=dict(input_generation='GO', donor_fit='HOLD', replay='HOLD'),
                    parent_characterization=item(CHAR), parent_contract=lock['base'],
                    model_assets=lock['model_assets'], cells=lock['cells'],
                    m5_online_packets=lock['online_packets'],
                    evaluator_inputs={r:item(BASE/f'gm_theta_m6/inputs/{r}_evaluator.npz') for r in ROUTES},
                    frozen_M6_parameters=item(parameters), d5_folds=item(d5/'FOLDS.json'),
                    d5_execution=item(d5/'EXECUTION.json'))
    check_records(contract)
    write(stage/'RUN_CONTRACT.json', contract)
    donor_dir = out/'donor_inputs'
    donor_dir.mkdir()
    donor_contract = provenance()
    donor_contract.update(stage='H5P_DONOR_CASE_PREPARATION', parent=item(stage/'RUN_CONTRACT.json'),
                          characterization=item(CHAR), d3=lock['d3'], cells=lock['cells'],
                          transform_source=item(M6/'run_characterization.py'),
                          meaning='Frozen D3 residuals and E0-LORO prior; no M7 outputs used')
    write(donor_dir/'RUN_CONTRACT.json', donor_contract)
    outputs = {}
    agreement = {}
    for cell in lock['cells']:
        r=cell['route']
        p, baseline, d3 = (arrays(checked(rec)) for rec in (cell['online'],cell['loro_trace'],lock['d3'][r]))
        for reference in (baseline,d3):
            for key in ('t','pose_id'):
                np.testing.assert_array_equal(p[key],reference[key])
        np.testing.assert_array_equal(baseline['mask'],d3['mask'])
        data=dict(t=p['t'],mask=d3['mask'], prior_distance=np.linalg.norm(baseline['prior'][:,:2]-[10.,0.],axis=1),
                  raw_s=d3['eps'][:,1],a_ref=baseline['H'][:,1,2],arc=d3['arc_m'],yaw_arc=d3['yaw_arc_rad'],
                  route_mean_s=np.asarray(d3['route_mean'][1]))
        path=donor_dir/f'{r}_donor.npz'
        with path.open('xb') as stream:
            np.savez_compressed(stream,**data)
        outputs[r]=item(path)
        agreement[r]=dict(packets=len(p['t']),accepted=int(d3['mask'].sum()),mean_s=float(data['route_mean_s']))
    write(donor_dir/'EXECUTION.json',dict(status='PASS_EXECUTION', started_utc=donor_contract['frozen_utc'],
          finished_utc=utc(),exit_code=0,command=[sys.executable,*sys.argv],
          contract_sha256=item(donor_dir/'RUN_CONTRACT.json')['sha256'],outputs=outputs,checks=agreement))
    h5=out/'h5prime'
    h5.mkdir()
    fit_contract=provenance()
    fit_contract.update(stage='H5P_SIGMA_ZERO_LORO',authorization=dict(donor_fit='GO',input_generation='HOLD',replay='HOLD'),
                        parent=item(donor_dir/'RUN_CONTRACT.json'), donor_preparation=item(donor_dir/'EXECUTION.json'),
                        h5prime=dict(method='M6_SIGMA_ZERO_LORO',donor_cases=outputs,
                                     characterizer_source=item(BASE/'gm_theta_m6/characterize.py')))
    write(h5/'RUN_CONTRACT.json',fit_contract)
    print('FROZEN input generation and H5P contracts',flush=True)


def independent_h5_check(out):
    contract=read(out/'h5prime/RUN_CONTRACT.json')
    fitted=read(out/'h5prime/H5P_DONOR_FIT.json')['fit']['folds']
    data={r:arrays(checked(rec)) for r,rec in contract['h5prime']['donor_cases'].items()}
    summaries={}
    for route,d in data.items():
        blocks=np.floor((d['t']-d['t'][0])/10.).astype(int)
        summaries[route]=[]
        for lo,hi in zip([0.,1.5,3.,6.],[1.5,3.,6.,10.]):
            numerators,denominators=[],[]
            use=d['mask']&(d['prior_distance']>=lo)&(d['prior_distance']<hi)
            for block in np.unique(blocks[use]):
                ids=np.flatnonzero(use&(blocks==block))
                i,j=np.meshgrid(ids,ids,indexing='ij')
                lag=d['t'][j]-d['t'][i]
                keep=(j>i)&(lag>=.4)&(lag<=5.)
                i,j=i[keep],j[keep]
                if len(i)<10:
                    continue
                kernel=np.exp(-(d['arc'][j]-d['arc'][i])-(d['yaw_arc'][j]-d['yaw_arc'][i])/math.radians(10.))
                eps=d['raw_s']-d['route_mean_s']
                numerators.append(float(np.mean(kernel*eps[i]*eps[j])))
                denominators.append(float(np.mean(kernel**2)))
            summaries[route].append(dict(supported=len(numerators)>=2,blocks=len(numerators),
                 numerator=float(np.mean(numerators)) if len(numerators)>=2 else None,
                 denominator=float(np.mean(denominators)) if len(numerators)>=2 else None))
    reports={}
    for held in ROUTES:
        rows=[]
        for b in range(4):
            donors=[summaries[r][b] for r in ROUTES if r!=held]
            supported=all(d['supported'] for d in donors)
            q=max(0.,sum(d['numerator'] for d in donors)/sum(d['denominator'] for d in donors)) if supported else 0.
            np.testing.assert_allclose(q,fitted[held]['q_s'][b],atol=1e-12,rtol=0.)
            assert supported == fitted[held]['supported_bins'][b]
            rows.append(dict(q_s=q,supported=supported,delta=float(q-fitted[held]['q_s'][b])))
        reports[held]=rows
    write(out/'h5prime/INDEPENDENT_CHECKS.json',dict(status='PASS_H5P_INDEPENDENT_RECALCULATION',
          checked_utc=utc(),absolute_tolerance=1e-12,folds=reports,donor_summaries=summaries,
          claim='Implementation self-check; no independent audit or M7 performance result'))
    print('PASS H5P donor fit and independent ratio checks',flush=True)


def fit(out):
    execute_h5_prime(out/'h5prime/RUN_CONTRACT.json',out/'h5prime/results')
    # Fit entry point requires an empty output directory; retain its receipt.
    fit_output=out/'h5prime/results/H5P_DONOR_FIT.json'
    write(out/'h5prime/H5P_DONOR_FIT.json',read(fit_output))
    independent_h5_check(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','fit','inputs'))
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.phase=='prepare':
        prepare(args.output)
    elif args.phase=='fit':
        fit(args.output)
    else:
        generate_inputs(args.output/'input_generation/RUN_CONTRACT.json',args.output/'input_generation')
        print('PASS 120 paired online packets and readback checks',flush=True)


if __name__=='__main__':
    main()

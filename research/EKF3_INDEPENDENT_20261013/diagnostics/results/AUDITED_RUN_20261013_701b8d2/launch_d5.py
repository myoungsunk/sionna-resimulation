from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import csv, datetime, hashlib, json, os, subprocess, sys

BASE=Path(__file__).resolve().parent
CASES=['R2_aA_m0','R2_aB_m0','R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']

def run_case(case,phase):
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUNBUFFERED='1')
    with (BASE/f'D5_{phase}_{case}.stdout.log').open('wb') as stdout,(BASE/f'D5_{phase}_{case}.stderr.log').open('wb') as stderr:
        cmd=[sys.executable,'-u',str(BASE/'run_d5_evidenced.py'),case,phase]
        p=subprocess.run(cmd,stdout=stdout,stderr=stderr,env=env)
    print(f'{phase} {case}: exit={p.returncode}',flush=True)
    return {'case':case,'phase':phase,'exit_code':p.returncode,'command':cmd}

def main():
    manifest=json.loads((BASE/'OUTPUT_D0_D4_SEED0/D0_D4_RUN_MANIFEST.json').read_text())
    print('D0-D4 completed status:',manifest['status'],flush=True)
    records=[]
    for phase in ['smoke','isolated']:
        print('Starting D5 phase',phase,flush=True)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(run_case,c,phase) for c in CASES]
            for f in as_completed(futures):
                rec=f.result();records.append(rec)
                if rec['exit_code']:
                    for future in futures:future.cancel()
                    (BASE/'D5_LAUNCH_FAILED.json').write_text(json.dumps(records,indent=2))
                    return 1
    rows=[]
    for rec in records:
        path=BASE/'D5_PARTS'/rec['phase']/rec['case']/'OUTPUT/D5_MULTI_SEED_FULL_ROUTE_METRICS.csv'
        with path.open(newline='',encoding='utf-8') as f:rows.extend(csv.DictReader(f))
    assert len(rows)==4536
    output=BASE/'D5_MULTI_SEED_FULL_ROUTE_METRICS.csv'
    with output.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (BASE/'D5_EXECUTION_RECEIPT.json').write_text(json.dumps({'status':'EXECUTED_EXPLORATORY','n_rows':len(rows),'trajectory_runs':1134,'seeds':[0,1,2],'levels':[0,1,2],'conditions':['noise_pair','gyro_bias','gyro_sf','wheel_asymmetry','slip','all'],'parts':records,'csv_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'scientific_PASS':False},indent=2))
    print('D5 completed: 1134 trajectory runs; 4536 arm metric rows',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())

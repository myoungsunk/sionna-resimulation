"""Sequential first-results then revision replay; no test-driven retuning."""
from pathlib import Path
import shutil,json
import numpy as np,pandas as pd
import numeric_patch,driver

def main():
    numeric_patch.install();out=Path('results_final');out.mkdir(exist_ok=True)
    cfg=json.loads(Path('prep/FROZEN_CALIBRATION.json').read_text());old=json.loads(Path('stage_a/prep/FROZEN_CALIBRATION.json').read_text())
    for key in ['Rc','T','pi0','normal_Rs']:assert cfg[key]==old[key],('Forbidden revision changed',key)
    cases=['R2_aB_m0','R4_aA_m0','R5_aA_m0','R5_aB_m0']
    for case in cases:
        if case=='R2_aB_m0':
            oldroot=Path('stage_a/results_a')
            for p in oldroot.glob(case+'*.npz'):shutil.copy2(p,out/p.name)
            a=pd.read_csv(oldroot/(case+'_METRICS.csv'))
            shutil.copy2(oldroot/(case+'_RESULT_AUDIT.json'),out/(case+'_A_RESULT_AUDIT.json'))
        else:
            driver.experiment(Path('inputs'),out,'A',case)
            a=pd.read_csv(out/(case+'_METRICS.csv'))
            (out/(case+'_RESULT_AUDIT.json')).rename(out/(case+'_A_RESULT_AUDIT.json'))
        driver.experiment(Path('inputs'),out,'B',case)
        b=pd.read_csv(out/(case+'_METRICS.csv'))
        (out/(case+'_RESULT_AUDIT.json')).rename(out/(case+'_B_RESULT_AUDIT.json'))
        keys=['case','channel','level','method','window'];basenames=['DR','S4','NIS_0p5','NIS_2']
        aa=a[a.method.isin(basenames)].set_index(keys).sort_index();bb=b[b.method.isin(basenames)].set_index(keys).sort_index()
        assert aa.index.equals(bb.index)
        for col in ['heading_rmse_deg','xy_rmse_m','bias_rmse_deg_s']:
            assert np.max(np.abs(aa[col]-bb[col]))<1e-8,('Baseline drift',case,col)
        pd.concat([a,b],ignore_index=True).drop_duplicates(keys,keep='last').to_csv(out/(case+'_METRICS.csv'),index=False)
        print('CASE_A_B_COMPLETE',case,flush=True)
    Path(out/'CAMPAIGN_CONTRACT.json').write_text(json.dumps(dict(cases=cases,model_revision='one latent RF offset, frozen T/Rc/pi0/normalRs',original_A_run=42560919706,source_A_commit='2e1254e06a8cbcc9fdf2923310fa6f46733f486a',rho=cfg['rho_C'],primary_R2_score='t>=140; t>=40 mixed development/descriptive',transfer_scope='already-known same-corridor R4/R5, not blind/new environment'),indent=2))
if __name__=='__main__':main()

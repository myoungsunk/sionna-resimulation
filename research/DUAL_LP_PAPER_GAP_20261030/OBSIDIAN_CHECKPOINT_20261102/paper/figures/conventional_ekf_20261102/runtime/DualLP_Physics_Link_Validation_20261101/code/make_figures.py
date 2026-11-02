"""Recreate four evidence figures from inspected CSVs; no filter execution."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def main(show: bool = False) -> None:
    root=Path(__file__).resolve().parents[1]; fd=root/'results/figures';fd.mkdir(exist_ok=True)
    scores=pd.read_csv(root/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv')
    order=[(f'{c}_aB_m0',b) for c in ('R2','R4','R5') for b in ('B0','L0','L1','L2')]
    labels=[f'{c[:2]}-B\n{b}' for c,b in order]; records=[]
    for metric,ylabel,file in [('head_rmse','Heading RMSE (degrees)','F3_HEADING_VARIANCE_POLICIES.png'),('xy_rmse_cm','Position RMSE (cm)','F4_POSITION_VARIANCE_POLICIES.png')]:
        fig,ax=plt.subplots(figsize=(13,5));x=np.arange(12)
        for offset,arm,label in [(-.25,'MB_ORIG','Mean replacement only'),(0.,'MB_CONST','Mean + held-route constant variance'),(.25,'MB_VAR','Mean + original distance lookup')]:
            part=scores[(scores.gate=='self')&(scores.arm==arm)].set_index(['case','bias']).loc[order]
            ax.bar(x+offset,part[metric],width=.24,label=label)
        ax.set_xticks(x,labels);ax.set_ylabel(ylabel);ax.set_ylim(bottom=0)
        ax.set_title('Reconstructed 12-condition results: original self gate, t ≥ 30 s')
        ax.legend(loc='upper center',bbox_to_anchor=(.5,1.02),ncol=3,fontsize=9)
        ax.margins(y=.18);ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True);fig.tight_layout()
        fig.savefig(fd/file,dpi=180,bbox_inches='tight')
        records.append(dict(file=file,source='tables/RECURSIVE_144_LOGICAL_SCORES.csv',filter='gate=self; MB_ORIG/MB_CONST/MB_VAR',metric=metric))
        if show and metric=='head_rmse':plt.show()
        plt.close(fig)
    shadow=pd.read_csv(root/'results/tables/SAME_PRIOR_VARIANCE_CONTRASTS_12.csv').set_index(['case','bias']).loc[order]
    fig,ax=plt.subplots(figsize=(13,4.8));ax.bar(np.arange(12),shadow.combined_minus_mean_head_mse_deg2);ax.axhline(0,linewidth=1)
    ax.set_xticks(np.arange(12),labels);ax.set_ylabel('Combined − mean-only heading MSE (degree²)')
    ax.set_title('Same BASE prior: one-step candidate loss, fixed accepted packets at t ≥ 30 s')
    ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True);fig.tight_layout();file='F2_SAME_PRIOR_HEADING_CONTRAST.png';fig.savefig(fd/file,dpi=180,bbox_inches='tight');plt.close(fig)
    records.append(dict(file=file,source='tables/SAME_PRIOR_VARIANCE_CONTRASTS_12.csv',metric='combined_minus_mean_head_mse_deg2'))
    physical=pd.read_csv(root/'results/PHYSICS_PACKET_LEDGER.csv.gz');fig,ax=plt.subplots(figsize=(9,5.8))
    for case,part in physical.groupby('case',sort=True):
        ax.scatter(part.J_spsi_per_rad,part.eps_s_MB,s=10,alpha=.4,label=f'{case[:2]}-B (n={len(part)})')
    ax.set_xlabel('SourceFFD heading sensitivity ∂s/∂ψ (rad⁻¹)');ax.set_ylabel('Signed residual εs after stored mean (dimensionless)')
    ax.set_title('Physical operating points and residuals: 3,136 unique RF packets');ax.legend();ax.grid(alpha=.2);fig.tight_layout();file='F1_PHYSICAL_SENSITIVITY_RESIDUAL.png';fig.savefig(fd/file,dpi=180,bbox_inches='tight');plt.close(fig)
    records.append(dict(file=file,source='PHYSICS_PACKET_LEDGER.csv.gz',filter='all unique RF packets; offline truth diagnostics',x='J_spsi_per_rad',y='eps_s_MB'))
    (fd/'FIGURE_MANIFEST.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print('결과 그림 4개와 그림별 데이터 출처를 저장했습니다.')
if __name__=='__main__':main()

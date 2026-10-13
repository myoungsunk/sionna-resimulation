"""Read-only decomposition of preserved V1 numerical agreement failures."""
from pathlib import Path
import datetime, hashlib, json
import numpy as np
from scipy.stats import t

H=Path(__file__).resolve().parent
OLD=H/'out/i2_short_range_kernel_01'

def main():
    package=json.loads((OLD/'PACKAGE_SHA256.json').read_text(encoding='utf-8-sig'))
    for name,digest in package['files'].items():
        assert hashlib.sha256((H/name).read_bytes()).hexdigest()==digest,name
    labels=['rho','sin(delta)','cos(delta)','bg/prior_sd','SF/prior_sd','eps/prior_sd','latent1','latent2']
    cases=[]
    for name in ('SYNTHETIC','R2','R4'):
        r=json.loads((OLD/f'{name}_RESULT.json').read_text())
        ref=r['qmc_statistics']['19'];other=r['batch_statistics']
        a=np.array([x['quantiles'] for x in ref]);b=np.array([x['quantiles'] for x in other])
        sd=np.sqrt((np.mean([np.square(x['sd']) for x in ref],0)+np.mean([np.square(x['sd']) for x in other],0))/2)
        between=b.var(0,ddof=1)/4
        within=np.square([x['mcse']['quantiles'] for x in other]).sum(0)/16
        raw=abs(a.mean(0)-b.mean(0))/sd[:,None]
        uncertainty=1.96*np.sqrt(a.var(0,ddof=1)/4+np.maximum(between,within))/sd[:,None]
        upper=raw+uncertainty
        assert np.allclose(upper,r['BATCH']['quantile_upper_sd'],rtol=1e-12,atol=1e-12)
        j,k=np.unravel_index(np.argmax(upper),upper.shape)
        cases.append(dict(case=name,quantile_worst=dict(parameter=labels[j],probability=[.025,.5,.975][k],
            raw_difference_in_sd=float(raw[j,k]),mc_margin_in_sd=float(uncertainty[j,k]),upper_in_sd=float(upper[j,k]),
            threshold=.1),batch_mean_mcse_per_chain_max=r['normalized_batch_mean_mcse'],
            batch_quantile_mcse_per_chain_max=r['normalized_batch_quantile_mcse'],
            raw_vs_simultaneous='See preserved RAW_DISTRIBUTION_COMPARISON.json',
            retention=8000,extension_trigger='Rhat/ESS only; MCSE and agreement not included',
            mode_evidence='disconnected basin evidence absent; not demonstrated sampler trapping'))
    result=dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        old_package_hashes_verified=len(package['files']),cases=cases,
        simultaneous=dict(coordinates=8,cdf_points_per_coordinate=99,joint_regions=3,total_tests=795,
            old_heldout_reference_replicates=3,old_method_replicates=4,old_df=2,
            old_bonferroni_multiplier=float(t.ppf(1-.05/(2*795),2)),
            proposed_actual_replicates=16,proposed_reference_heldout=15,proposed_min_df=14,
            proposed_bonferroni_multiplier=float(t.ppf(1-.05/(2*795),14)),
            threshold_unchanged=.05,method='same Bonferroni Student-t rule with actual independent replicate count'),
        conclusions=['V1 nonpassing bounds do not establish a true distribution disagreement',
                     'Quantile raw deviation and MC margin both preserved; no sole-cause attribution',
                     'No evidence yet of missed disconnected modes; previous evidence was unimplemented',
                     'V2 is post-result development; no retrospective change to V1 or confirmation claim'],
        I3='NOT_RUN',I7='NOT_RUN')
    (H/'out/I2_SHORT_RANGE_V1_MC_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()

"""Post-hoc Markov order intervention holding each path's J multiset fixed."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

from diagnose_markov import END, describe
from run_step1 import dump, sha
import run_step2 as s2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    out, run = args.out, args.run
    if out.exists():
        raise FileExistsError(out)
    curves, stations = s2.load_curves(run)
    case_names = list(stations)
    verdict = json.loads((run/"S2_VERDICT.json").read_bytes())
    rho_case = json.loads((run/"S1_RHO.json").read_bytes())
    scale_case = s2.training_scales(curves, stations)
    m = verdict["monte_carlo_paths"]
    case_idx = np.arange(m) % len(case_names)
    rng = np.random.default_rng(2026111303)
    _, dr, _ = s2.drivers(rng, m)
    uniforms = rng.uniform(size=(3,m,s2.N))
    r = np.array([scale_case[c]["r_deg2"] for c in case_names])[case_idx]
    rho = np.array([rho_case[c] for c in case_names])[case_idx]
    jrows = s2.pick_rows(stations,s2.station_pool(stations),case_idx,rho_case,uniforms,"markov")
    base = s2.simulate(curves,jrows,dr,r,rho,return_covariance=True)
    np.testing.assert_allclose(describe(base,dr)["coverage_1_to_17"],
                               verdict["stats"]["markov"]["coverage_1_to_17"],rtol=0,atol=1e-12)
    runs = 50
    seed = 2026111308
    prng = np.random.default_rng(seed)
    cov = np.zeros((runs,len(case_names)))
    bias = np.zeros_like(cov)
    total = np.zeros(runs)
    for k in range(runs):
        mixed = jrows.copy()
        perm = np.argsort(prng.random((m,END)),axis=1)
        mixed[:,:END] = np.take_along_axis(jrows[:,:END],perm,axis=1)
        np.testing.assert_array_equal(np.sort(mixed[:,:END]),np.sort(jrows[:,:END]))
        alt = s2.simulate(curves,mixed[:,:END],dr[:,:END],r,rho,return_covariance=True)
        total[k] = alt["covered"].mean()
        for i in range(len(case_names)):
            selected = case_idx==i
            cov[k,i] = alt["covered"][selected].mean()
            bias[k,i] = alt["err"][selected].mean()

    def dist(values):
        return dict(mean=float(values.mean()), p05=float(np.quantile(values,.05)),p95=float(np.quantile(values,.95)))

    by_case = {name:dict(frozen_coverage=float(base["covered"][case_idx==i,:END].mean()),
                         reordered_coverage=dist(cov[:,i]),
                         frozen_error_bias_deg=float(base["err"][case_idx==i,:END].mean()),
                         reordered_error_bias_deg=dist(bias[:,i]))
               for i,name in enumerate(case_names)}
    dump(out,dict(question_id="G1-FLOOR-001", diagnostic="within-path J order permutation",
                  interpretation="Post hoc intervention. Holds each path's selected J multiset, DR sequence, case, and filter fixed, changing only order over stations 1 to 17. Quantiles are variation across permutations, not inferential CI.",
                  seed=seed, permutations=runs, frozen_coverage=float(base["covered"][:,:END].mean()),
                  reordered_coverage=dist(total), per_case=by_case,
                  started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),
                  command=[sys.executable,*sys.argv], code_sha256=sha(Path(__file__)),
                  frozen_verdict_sha256=sha(run/"S2_VERDICT.json"),
                  base_input_manifest_sha256=sha(out.parent/"MANIFEST.json"),exit_code=0))


if __name__=="__main__":
    main()

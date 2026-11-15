"""D7 +K verification with an independent block reference and linear Monte Carlo."""
from pathlib import Path
import hashlib
import json
import math
import platform
import sys

import numpy as np
from scipy.stats import binomtest, chi2

ROOT = Path(sys.argv[1])
EVIDENCE = ROOT / "evidence"
sys.path[:0] = [str(EVIDENCE), str(ROOT.parent/"diag003_work/code")]
import diag_jc

N = 20000
STEPS = 30
SEED = 811007
SIGMA_K = .10
SIGMA_AR = .07
R = np.array([[.055**2, .25*.055*.035], [.25*.055*.035, .035**2]])
NOMINAL = .95
COVERAGE_TOLERANCE = .006  # roughly 3.9 binomial SD at N=20,000


def block_check():
    """Dense six-state filter with two consider dimensions and mixed R."""
    rng = np.random.default_rng(1907)
    matrix = rng.normal(size=(6, 6)) * .04
    p = matrix @ matrix.T + np.eye(6)*.002
    x = np.r_[.1, -.03, .02, 0., .05, -.015]
    h_matrix = rng.normal(size=(2, 6))
    r = np.array([[.018, .003], [.003, .011]])
    gates, err = [], []
    diag = np.array([1., 1., 1., .74, 1., 1.])
    q = np.diag([.0001, .0002, 0., .0001, 0., 0.])
    initial_fixed = p[4:, 4:].copy()
    for k in range(16):
        if k:
            x = diag*x
            p = diag[:, None]*p*diag[None, :] + q
        h = h_matrix@x
        z = h + [2.0, -8.0] if k % 4 == 0 else h + [.01, -.02]
        nu = z - h
        innovation_cov = h_matrix@p@h_matrix.T + r
        nis = float(nu@np.linalg.solve(innovation_cov,nu))
        gain_active = np.linalg.solve(innovation_cov,(p[:4]@h_matrix.T).T).T
        accept = nis <= diag_jc.JOINT_GATE
        yy, pp, applied, result_nis, _, gain = diag_jc.update(
            x[None], p[None], z, h[None], h_matrix[None], np.zeros(2), r, [4,5])
        expected_x, expected = x.copy(), p.copy()
        if accept:
            expected_x[:4] += gain_active@nu
            expected[:4,:4] -= gain_active@innovation_cov@gain_active.T
            expected[:4,4:] -= gain_active@(h_matrix@p[:,4:])
            expected[4:,:4] = expected[:4,4:].T
        assert bool(applied[0]) == accept
        assert np.all(gain[0,4:] == 0.)
        assert np.array_equal(pp[0,4:,4:],initial_fixed)
        assert np.allclose(yy[0,4:], x[4:], rtol=0, atol=0)
        assert np.linalg.eigvalsh(pp[0]).min() > 0
        cross_delta = float(np.max(np.abs(pp[0, :4, 4:]-p[:4,4:])))
        if accept:
            assert cross_delta > 0.
        err.append({"state": np.max(abs(yy[0]-expected_x)),
                    "P": np.max(abs(pp[0]-expected)),
                    "P_cross": np.max(abs(pp[0, :4,4:]-expected[:4,4:])),
                    "NIS": abs(result_nis[0]-nis)})
        x, p = yy[0], pp[0]
        gates.append(accept)
    diagnostics = {k: float(max(e[k] for e in err)) for k in err[0]}
    assert max(diagnostics.values()) < 1.e-12
    assert sum(gates) == 12 and len(gates)-sum(gates) == 4
    return {"status": "PASS", "max_abs_difference": diagnostics, "accepted": sum(gates),
            "rejected": len(gates)-sum(gates)}


def model(x, case):
    h = x[:, (0, 2)]
    jacobian = np.zeros((len(x), 2, 4))
    jacobian[:, 0, 0] = 1.
    jacobian[:, 1, 2] = 1.
    return h, jacobian


def mc_fixture():
    rng = np.random.default_rng(SEED)
    initial = rng.standard_normal((N,4))*diag_jc.INITIAL_STD
    yaw_pred_noise = math.radians(.015)*rng.standard_normal((STEPS-1,N))
    yaw = np.vstack([initial[:,2], initial[:,2]+np.cumsum(yaw_pred_noise-initial[:,3], axis=0)])
    z = rng.multivariate_normal(np.zeros(2), R, size=(STEPS,N))
    z[...,0] += initial[:,0]
    z[...,1] += yaw
    term_k = SIGMA_K*rng.standard_normal(N)
    term_ar = SIGMA_AR*rng.standard_normal(N)
    data = {"t":np.arange(STEPS, dtype=float), "case":{"anchor":(0.,0.)}, "model":model,
            "mu":np.zeros((STEPS,2)), "R":np.repeat(R[None],STEPS,axis=0)}
    controls = {k: np.zeros((N,STEPS)) for k in ("ds_odom","dtheta_gyro")}
    truth_final = initial.copy()
    truth_final[:,2] = yaw[-1]
    return data, controls, z, term_k, term_ar, truth_final


def metric(result, truth):
    e = result["state"][:,-1] - truth
    e[:,2] = diag_jc.wrap(e[:,2])
    c = result["covariance"][:,-1]
    dim = [("heading",(2,)), ("xy",(0,1)), ("bias",(3,))]
    out = {}
    for key, ix in dim:
        ee = e[:,ix]
        cc = c[:,ix,:][:,:,ix]
        nees = np.einsum("ni,ni->n",ee,np.linalg.solve(cc,ee[...,None])[...,0])
        count = int(np.count_nonzero(nees<=chi2.ppf(NOMINAL,len(ix))))
        ci = binomtest(count,N).proportion_ci(.95, method="wilson")
        out[key] = {"coverage": count/N, "count": count, "wilson95":[ci.low,ci.high],
                    "mean_nees": float(np.mean(nees)), "dof": len(ix)}
    out["heading"].update({
        "rmse_deg": float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),
        "mean_posterior_sd_deg": float(np.degrees(np.mean(np.sqrt(c[:,2,2]))))
    })
    out["gate_reject_rate"] = float(1-result["accepted"].mean())
    return out


def monte_carlo():
    data, controls, z, term_k, term_ar, truth = mc_fixture()
    k = diag_jc.Term(1,"consider",SIGMA_K**2)
    ar = diag_jc.Term(1,"ar",SIGMA_AR**2)
    z_matched, z_fixed, z_ar = z.copy(), z.copy(), z.copy()
    z_matched[...,1] += term_k
    z_fixed[...,1] += 3*SIGMA_K
    z_ar[...,1] += term_k+term_ar
    original_gate = diag_jc.JOINT_GATE
    configurations = (
        ("matched_K_gate_off",z_matched,(k,),False),
        ("matched_K_gate_on",z_matched,(k,),True),
        ("matched_AR_plus_K_infinite_limit_gate_off",z_ar,(ar,k),False),
        ("matched_AR_plus_K_infinite_limit_gate_on",z_ar,(ar,k),True),
        ("fixed_3sigma_K_gate_on",z_fixed,(k,),True),
        ("fixed_3sigma_J4_gate_on",z_fixed,(),True),
    )
    out = {}
    for name, obs, terms, gate in configurations:
        data["z"] = obs
        try:
            diag_jc.JOINT_GATE = original_gate if gate else np.inf
            result = diag_jc.replay(data, controls, np.zeros((N,3)), terms)
        finally:
            diag_jc.JOINT_GATE = original_gate
        out[name] = metric(result,truth)
        del result
    for name in ("matched_K_gate_off","matched_AR_plus_K_infinite_limit_gate_off"):
        for field in ("heading","xy","bias"):
            assert abs(out[name][field]["coverage"]-NOMINAL) <= COVERAGE_TOLERANCE, (name,field)
    out["DR_heading_rmse_deg"] = float(np.degrees(np.sqrt(np.mean(truth[:,2]**2))))
    return out


def d7_checkpoints():
    cases = ("R2_aA_m0","R2_aB_m0","R4_aB_m0","R5_aB_m0")
    output = {}
    for case in cases:
        folder=EVIDENCE/"main"/case
        summary = json.loads((folder/"B0_+0.json").read_text(encoding="utf-8"))
        with np.load(folder/"B0_+0.npz",allow_pickle=False) as data:
            row = {}
            for arm in ("JC_upper", "JC_K_upper", "JC_infinite", "JC_K_infinite"):
                s = summary["arms"][arm]
                key = s.get("identical_to",arm)
                e = data[f"{key}_checkpoint_error"]
                p = data[f"{key}_checkpoint_covariance"]
                sd = np.sqrt(p[...,2,2])
                out = {"n":e[...,2].size,"heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(e[...,2]**2)))),
                       "xy_rmse_m":float(np.sqrt(np.mean(np.sum(e[...,:2]**2,axis=-1)))),
                       "heading_coverage":float(np.mean(e[...,2]**2/p[...,2,2]<=chi2.ppf(.95,1))),
                       "heading_mean_nees":float(np.mean(e[...,2]**2/p[...,2,2])),
                       "heading_mean_sd_deg":float(np.degrees(np.mean(sd))),
                       "xy_mean_sd_trace_root_m":float(np.mean(np.sqrt(p[...,0,0]+p[...,1,1]))),
                       "all_eligible_frames_joint_reject_rate": s["frame"]["joint_gate_reject_rate"],
                       "conditional_mean_heading_error_deg":float(np.degrees(np.mean(e[...,2])))}
                for k in ("heading_rmse_deg","xy_rmse_m","heading95_coverage","heading_nees_mean"):
                    tag = {"heading95_coverage":"heading_coverage",
                           "heading_nees_mean":"heading_mean_nees"}.get(k,k)
                    assert abs(out[tag]-s["paired_checkpoint"]["J4"]["A"][k]["point"]) < 1e-12
                row[arm] = out
            output[case] = row
    return output


def main():
    path = Path(sys.argv[2])
    source = Path(diag_jc.__file__)
    suite = {"classification":"DIAGNOSTIC_ONLY","source_commit":"6cc0a6dd4515f313690aa74be9777508ad918e05",
             "diag_jc_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
             "run":{"profile":platform.platform(),"python":platform.python_version(),"numpy":np.__version__,
                    "seed":SEED,"independent_trials":N,"packets":STEPS,"nominal":NOMINAL,
                    "absolute_tolerance_gate_off":COVERAGE_TOLERANCE},
             "block":block_check(),"synthetic":monte_carlo(),"archived_D7_B0":d7_checkpoints()}
    path.write_text(json.dumps(suite,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"block":suite["block"],"synthetic":suite["synthetic"],
                      "archived_D7_B0":suite["archived_D7_B0"]},indent=2))


if __name__ == "__main__":
    main()

"""Run MODEL-003 v3's production EKF functions on generated observations only."""

import ast
import hashlib
import json
import math
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.stats import binomtest

REPO = Path(sys.argv[1])
SCRIPTS = REPO / "scripts" / "drive_sim"
sys.path.insert(0, str(SCRIPTS))
import tb3_model003_v3_joint as joint
from tb3_model003_filter import initial_covariance
from tb3_model003_v3_range import RangeModel
# The Linux runner imports resource on Windows. Load only its unmodified scoring code.
def load_checkpoint_scoring():
    path = SCRIPTS / "run_tb3_model003_s3.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    expected = {"wrap_rad", "score_state", "HEADING_BOUND", "XY_BOUND"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in expected:
            nodes.append(node)
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in expected
                                                for target in node.targets):
            nodes.append(node)
    scope = {"np": np}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope["score_state"], scope["HEADING_BOUND"], scope["XY_BOUND"]


score_state, HEADING_BOUND, XY_BOUND = load_checkpoint_scoring()

N = 20_000
STEPS = 30
SEED = 923418
NOMINAL = .95
TOLERANCE = .006
SIGMA_KS = .10
SIGMA_KR = .08
SIGMA_R = .055
SIGMA_S = .035
SIGMA_COLOR_S = .07
SIGMA_COLOR_R = .03
NUGGET = .20
SITE_RHO = .30
LENGTH_YAW = .25
K_R_STD = .005
ANCHOR = np.array([-8., 0.])
ANCHOR_DZ = 1.


def fit_constant(sigma):
    return dict(support_m=(0., 50.), knots_m=(0., 50.),
                log_variance=(np.log(sigma**2),)*2, white_variance=sigma**2)


def measurements(model, fixed_bias_sigma=None):
    rng = np.random.default_rng(SEED)
    truth = rng.multivariate_normal(np.zeros(model.motion_dim), covariance(model), size=N)
    noise_r = rng.normal(size=(STEPS, N))
    noise_s = rng.normal(size=(STEPS, N))
    gyro = rng.normal(size=(STEPS, N)) * math.radians(.015)
    stationary_r = rng.normal(size=(STEPS, N))
    stationary_s = rng.normal(size=(STEPS, N))
    kr = rng.normal(size=N)*SIGMA_KR
    ks = rng.normal(size=N)*SIGMA_KS if fixed_bias_sigma is None else fixed_bias_sigma*SIGMA_KS
    site_bias = rng.normal(size=(max(model.site_count, 1), N))
    angular = ([0.] + ([.1, -.1, 0., .05, -.05] * STEPS))[:STEPS]
    range_truth = np.sqrt(np.sum((truth[:, :2]-ANCHOR)**2, axis=1) + ANCHOR_DZ**2)
    color_r, color_s = stationary_r[0].copy(), stationary_s[0].copy()
    for step, angle in enumerate(angular):
        if step:
            truth[:, 2] += angle - truth[:, 3] + gyro[step]
            if model.motion_dim == 5:
                truth[:, 2] -= truth[:, 4]*abs(angle)
            decay = math.exp(-abs(angle)/LENGTH_YAW)
            std = math.sqrt(1-decay**2)
            color_r = decay*color_r + std*stationary_r[step]
            color_s = decay*color_s + std*stationary_s[step]
        r_obs = range_truth + SIGMA_R*noise_r[step]
        if model.has_range_consider:
            r_obs = (range_truth + kr + SIGMA_COLOR_R*math.sqrt(1-NUGGET)*color_r
                     + math.sqrt(SIGMA_R**2 + NUGGET*SIGMA_COLOR_R**2)*noise_r[step])
        site = step % max(model.site_count, 1)
        if model.colored_s:
            scale = SIGMA_COLOR_S*math.sqrt(1-model.site_corr)
            s_obs = (truth[:, 2] + ks + scale*math.sqrt(1-NUGGET)*color_s
                     + SIGMA_COLOR_S*math.sqrt(model.site_corr)*site_bias[site]
                     + math.sqrt(SIGMA_S**2 + NUGGET*scale**2)*noise_s[step])
        else:
            s_obs = truth[:, 2] + ks + math.hypot(SIGMA_S, SIGMA_COLOR_S)*noise_s[step]
        yield angle, site if model.site_count else None, r_obs, s_obs, truth


def covariance(model):
    return initial_covariance(K_R_STD if model.motion_dim == 5 else None)


def configure(arm):
    colored = arm != "J-V+K"
    sites = arm == "J-CS+K"
    md = 5 if sites else 4
    common = dict(length_m=1., length_rad=LENGTH_YAW, nugget=NUGGET)
    conditional_range = dict(mean_knots_m=np.array([0., 50.]), mean_bias_m=np.zeros(2),
                             c2_range=fit_constant(SIGMA_COLOR_R),
                             consider_variance_m2=SIGMA_KR**2, **common)
    r_model = RangeModel("R-MC" if colored else "R4", md, ANCHOR, ANCHOR_DZ,
                         0., SIGMA_R**2, 0., **(conditional_range if colored else {}))
    return joint.JointModel(arm, md, ANCHOR, ANCHOR_DZ, SIGMA_S**2, fit_constant(SIGMA_COLOR_S),
                            range_options=r_model, consider_s_variance=SIGMA_KS**2,
                            site_corr=SITE_RHO if sites else 0., site_count=4 if sites else 0,
                            **common)


def metric(nees, limit):
    count = int(np.count_nonzero(nees<=limit))
    ci = binomtest(count, N).proportion_ci(.95, method="wilson")
    return dict(coverage=count/N, count=count, wilson95=[ci.low, ci.high],
                mean_nees=float(np.mean(nees)))


def run(model, gates, fixed_bias_sigma=None):
    defaults = joint.GATE_RANGE, joint.GATE_JOINT
    if not gates:
        joint.GATE_RANGE = joint.GATE_JOINT = np.inf
    mean, cov = joint.initialize_joint(np.zeros((N, model.motion_dim)), covariance(model), model)
    consider = slice(model.active_dim, None)
    pcc = cov[:, consider, consider].copy()
    xc = mean[:, consider].copy()
    cross_max = 0.
    s_reject = r_reject = 0
    jac = np.broadcast_to([0., 0., 1.], (N, 3))
    try:
        for step, (angle, site, r_obs, s_obs, truth) in enumerate(measurements(model, fixed_bias_sigma)):
            if step:
                angular = abs(angle) if model.motion_dim == 5 else None
                mean, cov = joint.predict_joint(mean, cov, 0., angle, 1., model,
                                                angular_travel_rad=angular)
            mean, cov, events = joint.update_joint(mean, cov, r_obs, s_obs, mean[:, 2], jac, 0.,
                                                   model, site_index=site)
            assert np.array_equal(mean[:, consider], xc)
            assert np.array_equal(cov[:, consider, consider], pcc)
            assert events["s_available"].all() and events["r_available"].all()
            cross_max = max(cross_max, float(np.max(np.abs(cov[:, :model.active_dim, consider]))))
            s_reject += int(np.sum(events["s_gate_rejected"]))
            r_reject += int(np.sum(events["r_rejected"]))
    finally:
        joint.GATE_RANGE, joint.GATE_JOINT = defaults
    assert cross_max > 0.
    assert np.linalg.eigvalsh(cov).min() >= -1.e-12
    errors, xy, heading, bias = score_state(mean, cov, truth[:, 3], truth[:, :3])
    result = dict(heading=metric(heading, HEADING_BOUND), xy=metric(xy, XY_BOUND),
                  bias=metric(bias, HEADING_BOUND), s_gate_reject_rate=s_reject/(N*STEPS),
                  r_gate_reject_rate=r_reject/(N*STEPS), cross_covariance_max=cross_max,
                  Pcc_and_consider_mean_unchanged=True,
                  heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(errors[:, 2]**2)))))
    if not gates:
        assert all(abs(result[key]["coverage"]-NOMINAL)<=TOLERANCE for key in ("heading","xy","bias")), result
    return result


def repo_hashes():
    files = ("tb3_model003_v3_joint.py", "tb3_model003_v3_filter.py", "tb3_model003_v3_range.py",
             "tb3_model003_filter.py", "run_tb3_model003_s3.py", "tb3_model003_v3_characterization.py")
    return {name: hashlib.sha256((SCRIPTS/name).read_bytes()).hexdigest() for name in files}


def main():
    arms = ("J-V+K", "J-C+K", "J-CS+K")
    results = {}
    for arm in arms:
        for gate in (False,True):
            name = arm, "gate_on" if gate else "gate_off"
            results["/".join(name)] = run(configure(arm), gate)
    results["J-V+K/gate_on/fixed_3sigma"] = run(configure("J-V+K"), True, fixed_bias_sigma=3.)
    out = dict(classification="DIAGNOSTIC_ONLY", status="MATCHED_GATE_OFF_PASS",
               model_commit=subprocess.check_output(["git","-C",str(REPO),"rev-parse","HEAD"],text=True).strip(),
               source_sha256=repo_hashes(), seed=SEED, independent_trials=N, packets=STEPS,
               nominal=NOMINAL, absolute_tolerance_gate_off=TOLERANCE,
               python=platform.python_version(), numpy=np.__version__, results=results)
    text = json.dumps(out, indent=2)+"\n"
    Path(sys.argv[2]).write_text(text, encoding="utf-8")
    for name, row in results.items():
        print(name, "heading", row["heading"]["coverage"], "xy", row["xy"]["coverage"],
              "bias", row["bias"]["coverage"], "s_gate_reject", row["s_gate_reject_rate"])


if __name__ == "__main__":
    main()


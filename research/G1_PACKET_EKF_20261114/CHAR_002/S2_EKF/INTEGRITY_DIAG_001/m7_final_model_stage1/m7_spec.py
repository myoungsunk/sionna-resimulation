"""M7 ff7955d3 implementation scope. Importing this file starts no experiment."""
from collections import Counter

PLAN_COMMIT = "ff7955d3212065649057a335720e11fb92fff234"
PLAN_SHA256 = "9bafa3640fe34d1185481a97b1898a38d8490f59f261904d0cd93f94e69e4053"
ROUTES = ("R2", "R4", "R5")
ARMS = ("H0", "H1", "H2", "H3", "H4", "H5", "H5P")
SEEDS = tuple(range(10, 30))
FIXED_SEEDS = tuple(range(10, 15))
MAIN_CONDITIONS = ("B0", "L2_GYRO_ARW")
STRESS = "L2_GYRO_ARW_Q_B0_STRESS"
CONDITIONS = {
    "B0": {"injected_N_deg_sqrt_s": .015, "filter_N_deg_sqrt_s": .015,
           "input_condition": "B0", "decision_role": "MAIN"},
    "L2_GYRO_ARW": {"injected_N_deg_sqrt_s": .060, "filter_N_deg_sqrt_s": .060,
                    "input_condition": "L2_GYRO_ARW", "decision_role": "MAIN"},
    STRESS: {"injected_N_deg_sqrt_s": .060, "filter_N_deg_sqrt_s": .015,
             "input_condition": "L2_GYRO_ARW", "decision_role": "REPORT_ONLY"},
}


def cell_id(condition, mode, seed, route, arm):
    return f"{condition}/{mode}/seed{seed}/{route}/{arm}"


def expected_cells():
    """Enumerate all 1,470 planned cells; thirty DR controls are trace aliases."""
    cells = []
    for condition, policy in CONDITIONS.items():
        modes = ("own", "fixed") if condition in MAIN_CONDITIONS else ("own",)
        for mode in modes:
            for seed in SEEDS if mode == "own" else FIXED_SEEDS:
                for route in ROUTES:
                    for arm in ARMS:
                        alias = (cell_id(condition, "own", seed, route, arm)
                                 if mode == "fixed" and arm == "H0" else None)
                        cells.append(dict(id=cell_id(condition, mode, seed, route, arm),
                                          condition=condition, mode=mode, seed=seed,
                                          route=route, arm=arm, **policy,
                                          trace_alias_of=alias, execute=alias is None))
    return cells


def validate_cell_index(records):
    """Reject missing, extra, duplicate or relabelled cells instead of dropping them."""
    records = list(records)
    expected = {row["id"]: row for row in expected_cells()}
    counts = Counter(row["id"] for row in records)
    duplicates = sorted(key for key, count in counts.items() if count != 1)
    if set(counts) != set(expected) or duplicates:
        raise ValueError(dict(missing=sorted(set(expected) - set(counts)),
                              extra=sorted(set(counts) - set(expected)), duplicates=duplicates))
    for row in records:
        for key, value in expected[row["id"]].items():
            if key not in row or type(row[key]) is not type(value) or row[key] != value:
                raise ValueError(f"Cell identity differs: {row['id']}/{key}")
    return dict(cells=len(records), physical_replays=sum(row["execute"] for row in records),
                input_packets=2 * len(SEEDS) * len(ROUTES))


def execution_policy():
    """A draft default, never a frozen RUN_CONTRACT or authorization to execute."""
    return dict(plan_commit=PLAN_COMMIT, status="IMPLEMENTATION_ONLY",
                authorization={"input_generation": "HOLD", "donor_fit": "HOLD", "replay": "HOLD"},
                conditions=list(MAIN_CONDITIONS), seeds=list(SEEDS),
                input_aliases={STRESS: "L2_GYRO_ARW"},
                paired_gyro_noise={"b0_N_deg_sqrt_s": .015, "l2_N_deg_sqrt_s": .060})

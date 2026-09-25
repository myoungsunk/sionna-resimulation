"""Population and admission helpers for Paper 2 backend v3.

These helpers are deliberately input/materialization logic only.  They build
the planned five-space x R4-R7 primary population contract, seed identities,
and implementation/preflight summaries without running a backend endpoint or
promoting a scientific claim.
"""
from __future__ import annotations

import hashlib
from itertools import product
import json
from pathlib import Path
from typing import Any

import pandas as pd

from rt_cp_uwb_py.predictability_contracts_20260729 import (
    realization_sha256,
    seed_identity,
    sha256_json,
)


def load_backend_v3_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if "execution_caps" not in config:
        raise ValueError("backend v3 config missing execution_caps")
    if "primary" not in config["execution_caps"]:
        raise ValueError("backend v3 config missing execution_caps.primary")
    return config


def execution_cap(config: dict[str, Any], scope: str) -> dict[str, Any]:
    caps = config.get("execution_caps", {})
    if scope not in caps:
        raise KeyError(f"execution cap not configured: {scope}")
    cap = caps[scope]
    required = {"spaces", "regime_schedules", "max_steps_per_trajectory"}
    missing = required - set(cap)
    if missing:
        raise ValueError(f"execution cap {scope} missing fields: {sorted(missing)}")
    return cap


def _schedule_rule(config: dict[str, Any], schedule_id: str) -> dict[str, Any]:
    rule = config.get("regime_schedules", {}).get(schedule_id)
    if not isinstance(rule, dict):
        raise ValueError(f"unknown regime schedule: {schedule_id}")
    return rule


def _is_randomized_schedule(config: dict[str, Any], schedule_id: str) -> bool:
    return str(_schedule_rule(config, schedule_id).get("mode")) in {
        "per_step_mixed_anchor",
        "contiguous_contamination_burst",
    }


def _stable_seed(*parts: object) -> int:
    text = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "little", signed=False)


def _condition_pool(config: dict[str, Any]) -> list[str]:
    raw = config.get("regime_schedules", {}).get("condition_pool", [])
    if not isinstance(raw, list) or not raw:
        return ["side_reflector", "blockage", "metal_near"]
    return [str(item) for item in raw]


def schedule_realization_seeds(
    config: dict[str, Any],
    scope: str,
    schedule_id: str,
) -> list[int]:
    cap = execution_cap(config, scope)
    deterministic = cap.get("deterministic_schedule_realizations", {})
    if isinstance(deterministic, dict) and schedule_id in deterministic:
        count = int(deterministic[schedule_id])
        if count != 1:
            raise ValueError(f"deterministic schedule {schedule_id} must have exactly one realization")
        return [0]
    if _is_randomized_schedule(config, schedule_id):
        randomized = cap.get("randomized_schedule_seeds")
        if randomized is not None:
            if not isinstance(randomized, list) or not randomized:
                raise ValueError(f"execution cap {scope} randomized_schedule_seeds must be non-empty")
            seeds = [int(seed) for seed in randomized]
            if len(set(seeds)) != len(seeds):
                raise ValueError(f"execution cap {scope} randomized_schedule_seeds contains duplicates")
            return seeds
    raw = cap.get("seeds")
    if raw is None:
        raw = cap.get("replay_seeds")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"execution cap {scope} seeds/replay_seeds must be non-empty for schedule {schedule_id}")
    seeds = [int(seed) for seed in raw]
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"execution cap {scope} seeds/replay_seeds contains duplicates for schedule {schedule_id}")
    return seeds


def _max_steps_for_population(cap: dict[str, Any]) -> int:
    raw = cap.get("max_steps_per_trajectory", 50)
    if raw is None:
        available = cap.get("available_steps_per_trajectory")
        if available is None:
            raise ValueError(
                "execution cap max_steps_per_trajectory null requires available_steps_per_trajectory for standalone population materialization"
            )
        return int(available)
    return int(raw)


def _planned_assignment_hash(
    config: dict[str, Any],
    *,
    scope: str,
    space: str,
    schedule: str,
    replay_seed: int,
    max_steps: int,
) -> str:
    """Hash the planned schedule outcome, not the replay-seed label itself."""

    rule = _schedule_rule(config, schedule)
    mode = str(rule.get("mode"))
    pool = _condition_pool(config)
    schedule_seed = int(config.get("seed_authority", {}).get("schedule_seed", 0))
    anchors = ["A0", "A1", "A2"]
    if mode == "per_step_mixed_anchor":
        rng = _stable_seed(schedule_seed, space, schedule, replay_seed, "mixed")
        assignments = []
        state = rng
        for step_idx in range(max_steps):
            state = _stable_seed(state, "anchor", step_idx)
            anchor = anchors[state % len(anchors)]
            state = _stable_seed(state, "condition", step_idx)
            condition = pool[state % len(pool)]
            assignments.append({"step_idx": step_idx, "anchor_id": anchor, "condition_id": condition})
        return sha256_json(
            {
                "space_id": space,
                "schedule_id": schedule,
                "mode": mode,
                "assignments": assignments,
            }
        )
    if mode == "contiguous_contamination_burst":
        burst_len = int(rule.get("burst_length_steps", 0))
        if burst_len <= 0:
            raise ValueError(f"schedule {schedule} burst_length_steps must be > 0")
        max_start = max(1, max_steps - burst_len + 1)
        configured_seeds = schedule_realization_seeds(config, scope, schedule)
        if int(replay_seed) in configured_seeds:
            seed_rank = configured_seeds.index(int(replay_seed))
            if len(configured_seeds) > max_start * len(pool):
                raise ValueError(
                    f"schedule {schedule} has insufficient burst outcome capacity for {len(configured_seeds)} seeds"
                )
            start = seed_rank % max_start
            condition = pool[(seed_rank // max_start) % len(pool)]
        else:
            start = _stable_seed(schedule_seed, space, schedule, replay_seed, "start") % max_start
            condition = pool[_stable_seed(schedule_seed, space, schedule, replay_seed, "condition") % len(pool)]
        return sha256_json(
            {
                "space_id": space,
                "schedule_id": schedule,
                "mode": mode,
                "burst_start": int(start),
                "burst_length_steps": burst_len,
                "condition_id": condition,
            }
        )
    return sha256_json(
        {
            "space_id": space,
            "schedule_id": schedule,
            "mode": mode,
            "steps": list(range(max_steps)),
            "condition_id": str(rule.get("condition", schedule)),
            "sequence": list(rule.get("sequence", [])),
        }
    )


def materialize_population(config: dict[str, Any], scope: str) -> pd.DataFrame:
    """Create an outcome-blind planned runtime population table."""

    cap = execution_cap(config, scope)
    max_steps = _max_steps_for_population(cap)
    rows: list[dict[str, Any]] = []
    for space, schedule in product(
        cap["spaces"],
        cap["regime_schedules"],
    ):
        for replay_seed, step_idx in product(
            schedule_realization_seeds(config, scope, str(schedule)),
            range(max_steps),
        ):
            material = {
                "space_id": str(space),
                "schedule_id": str(schedule),
                "replay_seed": int(replay_seed),
                "step_idx": int(step_idx),
            }
            stochastic_hash = _planned_assignment_hash(
                config,
                scope=scope,
                space=str(space),
                schedule=str(schedule),
                replay_seed=int(replay_seed),
                max_steps=max_steps,
            )
            realization = sha256_json(
                {
                    "space_id": str(space),
                    "trajectory_id": f"{space}_T0",
                    "schedule_id": str(schedule),
                    "replay_seed": int(replay_seed),
                    "stochastic_realization_hash": stochastic_hash,
                }
            )
            is_randomized = _is_randomized_schedule(config, str(schedule))
            rows.append(
                {
                    **material,
                    "trajectory_id": f"{space}_T0",
                    "condition_id": str(schedule),
                    "pose_group_id": f"{space}_{schedule}",
                    "realization_sha256": realization,
                    "stochastic_realization_hash": stochastic_hash,
                    "realization_kind": "randomized" if is_randomized else "deterministic",
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        raise ValueError("materialized backend population is empty")
    return table


def attach_seed_identity(
    population: pd.DataFrame,
    *,
    namespace: str,
    arm: str = "population",
) -> pd.DataFrame:
    rows = population.copy()
    identities: list[str] = []
    seeds: list[int] = []
    payload_hashes: list[str] = []
    for row in rows.itertuples(index=False):
        digest, seed = seed_identity(
            namespace=namespace,
            lane="p2_backend_v3",
            arm=arm,
            case_id=f"{row.trajectory_id}:{row.schedule_id}:{row.step_idx}",
            repeat_index=int(row.replay_seed),
        )
        identities.append(digest)
        seeds.append(seed)
        payload_hashes.append(
            realization_sha256(
                [
                    str(row.space_id),
                    str(row.schedule_id),
                    int(row.replay_seed),
                    int(row.step_idx),
                    digest,
                ]
            )
        )
    rows["seed_identity_sha256"] = identities
    rows["runtime_seed_uint32"] = seeds
    rows["seeded_realization_sha256"] = payload_hashes
    return rows


def population_admission(population: pd.DataFrame) -> dict[str, Any]:
    required = {
        "space_id",
        "schedule_id",
        "replay_seed",
        "step_idx",
        "trajectory_id",
        "realization_sha256",
        "seed_identity_sha256",
        "seeded_realization_sha256",
        "stochastic_realization_hash",
    }
    missing = sorted(required - set(population.columns))
    duplicate_identity = int(population["seed_identity_sha256"].duplicated().sum())
    duplicate_seeded = int(population["seeded_realization_sha256"].duplicated().sum())
    realizations = population.drop_duplicates(
        ["space_id", "trajectory_id", "schedule_id", "replay_seed"]
    )
    randomized_realizations = realizations
    if "realization_kind" in randomized_realizations.columns:
        randomized_realizations = randomized_realizations[
            randomized_realizations["realization_kind"].astype(str).eq("randomized")
        ]
    duplicate_realization = int(
        randomized_realizations.duplicated(
            ["space_id", "trajectory_id", "schedule_id", "stochastic_realization_hash"]
        ).sum()
    )
    return {
        "pass": not missing and duplicate_identity == 0 and duplicate_seeded == 0 and duplicate_realization == 0,
        "n_rows": int(len(population)),
        "n_spaces": int(population["space_id"].nunique()),
        "n_schedules": int(population["schedule_id"].nunique()),
        "n_replay_seeds": int(population["replay_seed"].nunique()),
        "nominal_seed_count": int(population["replay_seed"].nunique()),
        "unique_realization_count": int(realizations["stochastic_realization_hash"].nunique()),
        "duplicate_realization_count": duplicate_realization,
        "effective_cluster_count": int(realizations.drop_duplicates(["space_id", "trajectory_id", "schedule_id", "stochastic_realization_hash"]).shape[0]),
        "trajectory_count": int(population["trajectory_id"].nunique()),
        "schedule_count": int(population["schedule_id"].nunique()),
        "missing_columns": missing,
        "duplicate_seed_identity": duplicate_identity,
        "duplicate_seeded_realization": duplicate_seeded,
        "seed_status": "DUPLICATE_REALIZATION" if duplicate_realization else "IDENTIFIABLE",
        "population_hash": sha256_json(
            population[
                ["space_id", "trajectory_id", "schedule_id", "replay_seed", "step_idx", "seed_identity_sha256", "stochastic_realization_hash"]
            ].to_dict(orient="records")
        ),
    }


def state_support(population: pd.DataFrame) -> pd.DataFrame:
    return (
        population.groupby(["space_id", "schedule_id"], as_index=False)
        .agg(
            n_rows=("step_idx", "size"),
            n_replay_seeds=("replay_seed", "nunique"),
            n_trajectories=("trajectory_id", "nunique"),
        )
        .sort_values(["space_id", "schedule_id"])
        .reset_index(drop=True)
    )

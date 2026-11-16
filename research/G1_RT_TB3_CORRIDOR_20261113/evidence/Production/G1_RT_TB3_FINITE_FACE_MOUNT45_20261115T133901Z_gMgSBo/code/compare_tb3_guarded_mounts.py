"""Compare geometry and path-rejection receipts between guarded mount angles."""
import argparse
from pathlib import Path

from verify_tb3_finite_face_production import CASES, checked_case_receipts, generation
from run_tb3_production import write


TASK_FIELDS = ("task_id", "pose_ids", "tag", "node_bins", "solver_calls",
               "n_full_paths", "n_near_paths", "pre_field_rejections",
               "pre_field_rejections_by_node")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("current", "mount0", "out"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    args = parser.parse_args()
    current, mount0 = args.current / "results", args.mount0 / "results"
    new_result, new_cases = generation(current)
    base_result, base_cases = generation(mount0)
    if (not new_result["finite_face_guard"] or not base_result["finite_face_guard"]
            or new_result["g6_result_sha256"] != base_result["g6_result_sha256"]):
        raise ValueError("Parent and +45 must use the same passing G6 filter")
    summaries = {}
    for case in sorted(CASES):
        new, new_tasks = checked_case_receipts(current, case, new_cases[case])
        base, base_tasks = checked_case_receipts(mount0, case, base_cases[case])
        if (base["mount_deg"], new["mount_deg"]) != (0, 45):
            raise ValueError(f"Wrong mounts for {case}")
        if new["samples_sha256"] != base["samples_sha256"]:
            raise ValueError(f"Samples differ for {case}")
        for left, right in zip(new_tasks, base_tasks, strict=True):
            if any(left[key] != right[key] for key in TASK_FIELDS):
                raise ValueError(f"Guarded trace differs for {case}/{left['task_id']}")
        if new["full_H_sha256"] == base["full_H_sha256"] or new["los_H_sha256"] == base["los_H_sha256"]:
            raise ValueError(f"Mount transform did not change the expected channel arrays for {case}")
        summaries[case] = dict(tasks=len(new_tasks), poses=new["poses"],
                               pre_field_rejections=sum(t["pre_field_rejections"] for t in new_tasks))
    write(args.out, dict(status="PASS", base_mount_deg=0, mount_deg=45, cases=summaries,
                         matching_trace_receipts=sum(v["tasks"] for v in summaries.values())))


if __name__ == "__main__":
    main()

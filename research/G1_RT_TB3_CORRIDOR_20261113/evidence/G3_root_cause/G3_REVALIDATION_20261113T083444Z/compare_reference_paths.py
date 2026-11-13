"""Compare unpaired high-sample reference paths with the two original arms."""
import argparse
from pathlib import Path

from run_tb3_g1_pilot import load_runtime, read, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--revalidation", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    trace, np, versions = load_runtime(args.source)
    result_path = args.revalidation / "analysis/G3.json"
    result = read(result_path)
    unusable = []
    for entry in result["pooled"]["unusable"]:
        if entry["arm"] != "bin_by_bin":
            raise ValueError("Unexpected non-reference unusable trace")
        rel = Path(entry["case"]) / "bin_by_bin" / f"{entry['tag']}_trace.npz"
        p = args.revalidation / "output" / rel
        receipt_path = p.with_name(f"{p.stem}_receipt.json")
        receipt = read(receipt_path)
        with np.load(p, allow_pickle=False) as data:
            d_tau = data["tau"]
            d_dirs = trace.P.path_directions(*data["ang"])
        arms = {}
        for arm in ("bin_by_bin", "node_interpolation"):
            old_trace = args.original / "output" / entry["case"] / arm / p.name
            with np.load(old_trace, allow_pickle=False) as data:
                tau = data["tau"]
                dirs = trace.P.path_directions(*data["ang"])
                match, _ = trace.P.match_partial(d_tau, d_dirs, tau, dirs, tol=trace.ANGLE_TOL_RAD)
                lookup = {}
                for idx in receipt["complex_paths"]:
                    j = int(match[idx])
                    lookup[str(idx)] = (dict(path_index=j, presence=int(data["present"][:, j].sum()))
                                        if j >= 0 else None)
                arms[arm] = dict(sha256=sha(old_trace), path_matches=lookup)
        paths = [r for r in receipt["dropped_audit"] if r["path"] in receipt["complex_paths"]]
        unusable.append(entry | dict(trace_sha256=sha(p), receipt_sha256=sha(receipt_path),
                                       paths=paths, original_arms=arms))
    write(args.out, dict(kind="POST_HOC_REFERENCE_PATH_COMPARISON", versions=versions,
                         revalidation_result_sha256=sha(result_path), records=unusable))


if __name__ == "__main__":
    main()

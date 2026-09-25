from __future__ import annotations

import argparse

from rt_cp_uwb_py.remote import run_remote_parity


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh-target", default="root@141.223.86.156")
    ap.add_argument("--remote-root", default="/root/rt_cp_uwb_python_port")
    ap.add_argument("--cases-csv", default=None)
    ap.add_argument("--baseline-csv", default=None)
    ap.add_argument("--max-cases", type=int, default=30)
    ap.add_argument("--replay-fp-hints", action="store_true")
    args = ap.parse_args()
    result = run_remote_parity(
        args.ssh_target,
        args.remote_root,
        cases_csv=args.cases_csv,
        baseline_csv=args.baseline_csv,
        max_cases=args.max_cases,
        replay_fp_hints=args.replay_fp_hints,
    )
    print(result["local_out"])


if __name__ == "__main__":
    main()

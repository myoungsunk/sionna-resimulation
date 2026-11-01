"""A010 canonical-input module technical smoke. DEV3/HOLDOUT2 stay sealed."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import a10_canonical as A  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    gen = ROOT / "results/P2_A010P0_GEN_run_41269011836"
    result = A.smoke_report(gen / "A010_LHALF_WORLDPOSE_V2.npy",
                            gen / "A010_CANONICAL_INPUTS.zip",
                            gen / "A010_INPUT_CANONICAL_SHA.csv")
    result["scope"] = "A010_CANONICAL_TECHNICAL_SMOKE_ONLY"
    result["source_inputs"] = "A010-P0 GEN run 41269011836 (forensic 4 existing DEV2 keys)"
    result["scientific_verdict"] = "NOT_EVALUATED"
    result["A010_full_freeze"] = "DRAFT"
    result["DEV3"] = "NOT_RUN"
    result["HOLDOUT2"] = "NOT_RUN"
    result["RT"] = "NOT_RUN"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"pass": result["pass"], "tested_arrays": result["array_ledger"]["checked"],
                      "DEV3": result["DEV3"]}, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

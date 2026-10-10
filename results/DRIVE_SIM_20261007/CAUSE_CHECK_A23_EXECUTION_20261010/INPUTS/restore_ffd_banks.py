"""Restore the complete production FFD banks; refuse overwrites and verify all hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    manifest = json.loads((base / "FFD_RESTORE_MANIFEST.json").read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    for bank in manifest["banks"]:
        name = bank["filename"]
        if Path(name).name != name:
            raise ValueError("Invalid bank filename")
        output = args.out / name
        partial = args.out / (name + ".partial")
        if output.exists() or partial.exists():
            raise FileExistsError("Preserve existing file: " + str(output))
        full_hash = hashlib.sha256()
        total = 0
        with partial.open("xb") as target:
            for part in bank["parts"]:
                source = (base / part["path"]).resolve()
                if not source.is_relative_to(base):
                    raise ValueError("Part outside package")
                part_hash = hashlib.sha256()
                part_size = 0
                with source.open("rb") as reader:
                    for block in iter(lambda: reader.read(4 * 1024 * 1024), b""):
                        target.write(block)
                        part_hash.update(block)
                        full_hash.update(block)
                        part_size += len(block)
                if part_size != part["bytes"] or part_hash.hexdigest() != part["sha256"]:
                    raise ValueError("Part mismatch; partial evidence retained: " + str(source))
                total += part_size
        if total != bank["bytes"] or full_hash.hexdigest() != bank["sha256"]:
            raise ValueError("Bank mismatch; partial evidence retained: " + name)
        partial.rename(output)
        print(json.dumps({"file": str(output), "bytes": total, "sha256": full_hash.hexdigest(), "verified": True}))


if __name__ == "__main__":
    main()

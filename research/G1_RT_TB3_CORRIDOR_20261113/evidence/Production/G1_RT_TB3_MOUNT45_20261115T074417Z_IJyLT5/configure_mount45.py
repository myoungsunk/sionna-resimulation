"""Generate the isolated mount-45 derivative of the byte-pinned F1 runner."""
import ast
import hashlib
import json
from pathlib import Path

def replace(data, old, new):
    if data.count(old) != 1:
        raise ValueError(f"Expected one match for {old!r}")
    return data.replace(old, new)

def write_source(name, source):
    ast.parse(source, filename=name)
    Path("code", name).write_bytes(source.encode())

base_config = Path("PRODUCTION_F1_MOUNT0.json").read_bytes()
old_hash = hashlib.sha256(base_config).hexdigest()
assert old_hash == "fcd3ee9448640bcd29e0f031d06243a7cd5d8c6d7f80b1db49485ed7904017d8"
config = replace(base_config, b'"mount_deg": 0,', b'"mount_deg": 45,')
assert json.loads(config) == dict(json.loads(base_config), mount_deg=45)
Path("config/PRODUCTION_F1.json").write_bytes(config)
runner = Path("RUNNER_MOUNT0.py").read_text()
runner = replace(runner, old_hash, hashlib.sha256(config).hexdigest())
runner = replace(runner, "(17, 257, 0)", "(17, 257, 45)")
runner = replace(
    runner,
    '    parser.add_argument("--g8-canary", type=Path, metavar="G1_OUTPUT")\n',
    '    parser.add_argument("--g8-canary", type=Path, metavar="G1_OUTPUT")\n'
    '    parser.add_argument("--canary-los-reference", type=Path)\n',
)
runner = replace(
    runner,
    "    if args.g8_canary:\n        if args.case",
    '    if bool(args.g8_canary) != bool(args.canary_los_reference):\n'
    '        parser.error("The pilot needs both frozen pose input and mount-45 LoS reference")\n'
    "    if args.g8_canary:\n        if args.case",
)
runner = replace(
    runner,
    '        check_canary(args.g8_canary, args.out / "PATHS_LoS.npz")',
    '        check_canary(args.canary_los_reference, args.out / "PATHS_LoS.npz")',
)
runner = replace(
    runner,
    '        write(args.out / "CANARY.json", gate | {"native_g1_coefficient_delay_exact": True})',
    '        write(args.out / "CANARY.json", gate | {\n'
    '            "mount_deg": 45, "native_g1_coefficient_delay_exact": True,\n'
    '            "independent_los_reference_sha256": sha(args.canary_los_reference / "PATHS_LoS.npz"),\n'
    '        })',
)
write_source("run_tb3_production.py", runner)
merge = Path("MERGER_MOUNT0.py").read_text()
merge = replace(merge, 'mount_deg=0,', 'mount_deg=manifests[0]["engine"]["mount_deg"],')
write_source("merge_tb3_production.py", merge)
g4 = Path("G4_MOUNT0.py").read_text()
g4 = replace(g4, "MOUNT_DEG = 0.0", "MOUNT_DEG = 45.0")
g4 = replace(
    g4, "    poses_dir = results_root",
    '    manifest = read_json(results_root / "H" / case / "MANIFEST.json")\n'
    '    if manifest["case"] != case or manifest["mount_deg"] != MOUNT_DEG:\n'
    '        raise ValueError(f"{case}: unexpected mount in merged data")\n'
    "    poses_dir = results_root",
)
write_source("validate_tb3_g4.py", g4)
batch = Path("BATCH_MOUNT0.py").read_text()
batch = replace(
    batch,
    '    if not read(canary).get("native_g1_coefficient_delay_exact"):\n',
    '    receipt = read(canary)\n'
    '    if (receipt.get("status") != "PASS" or receipt.get("mount_deg") != 45\n'
    '            or not receipt.get("native_g1_coefficient_delay_exact")\n'
    '            or receipt.get("independent_los_reference_sha256")\n'
    '               != sha(root / "los_reference/PATHS_LoS.npz")):\n',
)
write_source("run_tb3_production_batch.py", batch)

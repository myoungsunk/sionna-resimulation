#!/usr/bin/env bash
# Snowball lane controller for the full native campaign (runs on the host as KMS).
#
#   --pilot         PILOT_IDS=B000123,B004567 (required, non-empty, each id in BATCHES, no duplicates, <= 64)
#   --launch        all batches of 02_batches/BATCHES.jsonl in background lanes; refuses if a controller is alive
#   --status        JSON counts (works before any output exists)
#   --server-verify container verify_sionna_full.py --raw-policy full -> 06_validation/SERVER_VERIFY.json
#   --preflight     host identity/load/RAM/disk + pinned image + container versions/imports -> controller/PREFLIGHT_*.json
#   --los-fixture   container runtime --los-fixture-only (exactly 9 PathSolver calls; reused if passed)
#   --pilot-report  PILOT_IDS + EXPECTED_ROWS: bounded S2 report -> 06_validation/S2_PILOT_REPORT.json,
#                   03_pilot/CAPACITY_PLAN.json (the full verify stays INCOMPLETE after a pilot by design)
#
# Each batch: pinned Docker image -> sionna_full_runtime.py (reuses verified targets, recovers COMPLETE)
# -> finish_sionna_full.py (skips only when production matches the current key; refuses stale output).
# No existence-based skipping here: completion is decided inside the container against the current key.
# Transient runtime failures (exit not 0/2) are retried at most twice (3 attempts); exit 2 = recorded
# deterministic target failures, not retried; finish exit 4 = refused (stale/incomplete), not retried.
# NOT executed from the development environment; see tests/test_g2_full_lanes.py for the fake-docker checks.
set -euo pipefail
: "${CAMPAIGN:?}" "${CODE_REV:?}" "${INPUTS_DIR:?}" "${IMAGE:?}" "${PY:?}"
CODE="$CAMPAIGN/code/$CODE_REV"   # revision-specific staged code (never overwritten)
LANES="${LANES:-2}"; THREADS="${THREADS:-4}"; PILOT_MAX="${PILOT_MAX:-64}"
CTRL="$CAMPAIGN/controller"
BATCHES="$CAMPAIGN/02_batches/BATCHES.jsonl"
HOST_PY="${HOST_PY:-python3}"

log() { mkdir -p "$CTRL"; echo "$(date -u +%FT%TZ) $*" >>"$CTRL/events.log"; }

all_ids() {
  "$HOST_PY" -c 'import json,sys
for l in open(sys.argv[1]):
    print(json.loads(l)["batch_id"])' "$BATCHES"
}

pilot_ids() {  # validated explicit list; never falls back to all batches
  [ -n "${PILOT_IDS:-}" ] || { echo "PILOT_IDS_REQUIRED: explicit non-empty representative batch list" >&2; return 64; }
  "$HOST_PY" -c 'import json,sys
known = {json.loads(l)["batch_id"] for l in open(sys.argv[1])}
ids = [x for x in sys.argv[2].split(",")]
if not ids or any(not x for x in ids): sys.exit("PILOT_IDS_EMPTY_ELEMENT")
if len(ids) != len(set(ids)): sys.exit("PILOT_IDS_DUPLICATE")
unknown = [x for x in ids if x not in known]
if unknown: sys.exit("PILOT_IDS_UNKNOWN:" + ",".join(unknown))
if len(ids) > int(sys.argv[3]): sys.exit("PILOT_IDS_TOO_MANY")
print("\n".join(ids))' "$BATCHES" "$PILOT_IDS" "$PILOT_MAX"
}

container() {  # extra docker args..., then the command
  docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp:rw,size=2g -e HOME=/tmp \
    -v "$CODE:$CODE:ro" -v "$CAMPAIGN/input:$CAMPAIGN/input:ro" \
    -v "$CAMPAIGN/$INPUTS_DIR:$CAMPAIGN/$INPUTS_DIR:ro" -v "$CAMPAIGN/02_batches:$CAMPAIGN/02_batches:ro" \
    -v "$CAMPAIGN/batches:$CAMPAIGN/batches:rw" -v "$CAMPAIGN/06_validation:$CAMPAIGN/06_validation:rw" \
    -w "$CODE" "$@"
}

run_batch() {  # $1 batch id
  local id="$1" try rc frc
  mkdir -p "$CTRL/logs" "$CAMPAIGN/batches" "$CAMPAIGN/06_validation"
  for try in 1 2 3; do
    rc=0
    container --cpus "$THREADS" "$IMAGE" "$PY" scripts/g2_completion/sionna_full_runtime.py --environment snowball \
      --campaign-root "$CAMPAIGN" --inputs-dir "$INPUTS_DIR" --batch-id "$id" --threads "$THREADS" \
      >>"$CTRL/logs/$id.log" 2>&1 || rc=$?
    log "$id try=$try runtime_rc=$rc"
    if [ "$rc" = 0 ]; then
      frc=0
      container "$IMAGE" "$PY" scripts/g2_completion/finish_sionna_full.py --campaign-root "$CAMPAIGN" \
        --inputs-dir "$INPUTS_DIR" --batch-id "$id" >>"$CTRL/logs/$id.log" 2>&1 || frc=$?
      log "$id finish_rc=$frc"
      return 0
    fi
    if [ "$rc" = 2 ]; then log "$id TARGET_FAILURES_RECORDED"; return 0; fi
  done
  log "$id GAVE_UP_AFTER_3"
}

lane() {  # $1 lane index, $2 file with ids: runs ids where index % LANES == lane
  local lane="$1" i=0 id
  while read -r id; do
    if [ $((i % LANES)) = "$lane" ]; then run_batch "$id"; fi
    i=$((i+1))
  done <"$2"
}

alive() { [ -f "$CTRL/RUNNING" ] && kill -0 "$(cat "$CTRL/RUNNING")" 2>/dev/null; }

count() { { find "$CAMPAIGN/batches" -path "$1" -type f 2>/dev/null || true; } | wc -l | tr -d ' '; }

case "${1:-}" in
  --pilot)
    mkdir -p "$CTRL"; list="$CTRL/pilot_ids.$$"
    pilot_ids >"$list" || { rc=$?; rm -f "$list"; exit "$rc"; }
    log "PILOT start ids=$(paste -sd, "$list")"
    for l in $(seq 0 $((LANES-1))); do lane "$l" "$list" & done; wait
    log "PILOT end"; rm -f "$list";;
  --launch)
    if alive; then echo "CONTROLLER_ALREADY_RUNNING pid=$(cat "$CTRL/RUNNING")"; exit 0; fi
    mkdir -p "$CTRL/logs"; all_ids >"$CTRL/all_ids.txt"
    nohup bash -c "echo \$\$ >'$CTRL/RUNNING'; for l in \$(seq 0 $((LANES-1))); do bash '$0' --lane \$l '$CTRL/all_ids.txt' & done; wait; rm -f '$CTRL/RUNNING'" \
      >>"$CTRL/controller.log" 2>&1 &
    sleep 1; echo "LAUNCHED pid=$(cat "$CTRL/RUNNING" 2>/dev/null || echo '?') lanes=$LANES threads=$THREADS";;
  --lane) lane "$2" "$3";;
  --status)
    total=$(wc -l <"$BATCHES" | tr -d ' ')
    comp=$(count '*/attempt_*/COMPLETE.json'); fin=$(count '*/production/FINISHED.json')
    if alive; then a=true; else a=false; fi
    echo "{\"batches\": $total, \"complete_files\": $comp, \"finished_files\": $fin, \"controller_alive\": $a, \"note\": \"file counts only; completion under the current key is decided by verify_sionna_full.py\"}";;
  --server-verify)
    mkdir -p "$CAMPAIGN/06_validation"
    container "$IMAGE" "$PY" scripts/g2_completion/verify_sionna_full.py --campaign-root "$CAMPAIGN" \
      --inputs-dir "$INPUTS_DIR" --raw-policy full --out 06_validation/SERVER_VERIFY.json;;
  --preflight)
    mkdir -p "$CTRL"; out="$CTRL/PREFLIGHT_$(date -u +%Y%m%dT%H%M%SZ).json"
    {
      echo "{\"user\": \"$(whoami)\", \"host\": \"$(hostname)\", \"nproc\": $(nproc),"
      echo " \"loadavg\": \"$(cut -d' ' -f1-3 /proc/loadavg)\","
      echo " \"mem_available_gib\": $(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo),"
      echo " \"disk_free_gib\": $(df -Pk "$CAMPAIGN" | awk 'NR==2 {printf "%.1f", $4/1048576}'),"
      echo " \"image_present\": $(docker image inspect "$IMAGE" >/dev/null 2>&1 && echo true || echo false),"
      echo " \"code_rev\": \"$CODE_REV\","
      cont=$(container "$IMAGE" "$PY" -c 'import json,importlib.metadata as m,sys
import mitsuba as mi; mi.set_variant("llvm_ad_mono_polarized")
v={n:m.version(n) for n in ("sionna-rt","mitsuba","drjit")}
mods={}
for name in ("sklearn","shapely","scipy","numpy","rt_cp_uwb_py","rt_cp_uwb_py.g2_full_runner","rt_cp_uwb_py.g2_scoped_channel"):
    try:
        __import__(name); mods[name]="ok"
    except Exception as e:
        mods[name]=type(e).__name__+": "+str(e)[:120]
print(json.dumps(dict(python=sys.executable, versions=v, variant=mi.variant(), imports=mods)))' 2>&1 | tail -1 || true)
      case "$cont" in "{"*) ;; *) cont="{\"error\": \"container check failed: $(printf %s "$cont" | tr -d '"\\' | head -c 200)\"}";; esac
      echo " \"container\": $cont"
      echo "}"
    } >"$out"
    cat "$out";;
  --los-fixture)
    mkdir -p "$CAMPAIGN/02_fixtures"
    docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp:rw,size=2g -e HOME=/tmp \
      -v "$CODE:$CODE:ro" -v "$CAMPAIGN/input:$CAMPAIGN/input:ro" -v "$CAMPAIGN/$INPUTS_DIR:$CAMPAIGN/$INPUTS_DIR:ro" \
      -v "$CAMPAIGN/02_fixtures:$CAMPAIGN/02_fixtures:rw" -w "$CODE" "$IMAGE" \
      "$PY" scripts/g2_completion/sionna_full_runtime.py --environment snowball --campaign-root "$CAMPAIGN" \
        --inputs-dir "$INPUTS_DIR" --los-fixture-only --threads "$THREADS";;
  --pilot-report)
    : "${EXPECTED_ROWS:?}"; ids=$(pilot_ids | paste -sd,)
    mkdir -p "$CAMPAIGN/03_pilot"
    container -v "$CAMPAIGN/03_pilot:$CAMPAIGN/03_pilot:rw" -v "$CAMPAIGN/02_fixtures:$CAMPAIGN/02_fixtures:ro" \
      "$IMAGE" "$PY" scripts/g2_completion/report_sionna_pilot.py --campaign-root "$CAMPAIGN" \
      --inputs-dir "$INPUTS_DIR" --batches "$ids" --expected-rows "$EXPECTED_ROWS" --lanes "$LANES" --threads "$THREADS";;
  *) echo "usage: $0 --preflight|--los-fixture|--pilot|--pilot-report|--launch|--status|--server-verify" >&2; exit 64;;
esac

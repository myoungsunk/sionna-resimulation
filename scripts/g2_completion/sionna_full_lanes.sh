#!/usr/bin/env bash
# Snowball lane controller for the full native campaign (runs on the host as KMS).
# Each batch: pinned Docker image -> sionna_full_runtime.py -> finish_sionna_full.py.
# Resume-safe: a batch with production/FINISHED.json is skipped; runtime reuses verified targets.
# Transient failures (exit not 0/2) are retried at most twice (3 attempts); exit 2 = deterministic
# target failures, recorded and not retried. NOT executed from the development environment.
set -euo pipefail
: "${CAMPAIGN:?}" "${INPUTS_DIR:?}" "${IMAGE:?}" "${PY:?}" "${LANES:=2}" "${THREADS:=4}"
CTRL="$CAMPAIGN/controller"; mkdir -p "$CTRL"
BATCHES="$CAMPAIGN/02_batches/BATCHES.jsonl"

run_batch() {  # $1 batch id
  local id="$1" try rc
  [ -f "$CAMPAIGN/batches/$id/production/FINISHED.json" ] && return 0
  for try in 1 2 3; do
    rc=0
    docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp:rw,size=2g \
      --cpus "$THREADS" -e HOME=/tmp \
      -v "$CAMPAIGN/code:$CAMPAIGN/code:ro" -v "$CAMPAIGN/input:$CAMPAIGN/input:ro" \
      -v "$CAMPAIGN/$INPUTS_DIR:$CAMPAIGN/$INPUTS_DIR:ro" -v "$CAMPAIGN/02_batches:$CAMPAIGN/02_batches:ro" \
      -v "$CAMPAIGN/batches:$CAMPAIGN/batches:rw" -w "$CAMPAIGN/code" "$IMAGE" \
      "$PY" scripts/g2_completion/sionna_full_runtime.py --environment snowball --campaign-root "$CAMPAIGN" \
        --inputs-dir "$INPUTS_DIR" --batch-id "$id" --threads "$THREADS" \
      >>"$CTRL/logs/$id.log" 2>&1 || rc=$?
    echo "$(date -u +%FT%TZ) $id try=$try runtime_rc=$rc" >>"$CTRL/events.log"
    if [ "$rc" = 0 ]; then
      docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp \
        -v "$CAMPAIGN/code:$CAMPAIGN/code:ro" -v "$CAMPAIGN/$INPUTS_DIR:$CAMPAIGN/$INPUTS_DIR:ro" \
        -v "$CAMPAIGN/batches:$CAMPAIGN/batches:rw" -w "$CAMPAIGN/code" "$IMAGE" \
        "$PY" scripts/g2_completion/finish_sionna_full.py --campaign-root "$CAMPAIGN" \
          --inputs-dir "$INPUTS_DIR" --batch-id "$id" >>"$CTRL/logs/$id.log" 2>&1 \
        && echo "$(date -u +%FT%TZ) $id FINISHED" >>"$CTRL/events.log" \
        || echo "$(date -u +%FT%TZ) $id FINISH_FAILED" >>"$CTRL/events.log"
      return 0
    fi
    [ "$rc" = 2 ] && { echo "$(date -u +%FT%TZ) $id TARGET_FAILURES_RECORDED" >>"$CTRL/events.log"; return 0; }
  done
  echo "$(date -u +%FT%TZ) $id GAVE_UP_AFTER_3" >>"$CTRL/events.log"
}

lane() {  # $1 lane index: batches i where i % LANES == lane
  local lane="$1" i=0 id
  while read -r id; do
    [ $((i % LANES)) = "$lane" ] && run_batch "$id"
    i=$((i+1))
  done < <(ids)
}

ids() {
  if [ -n "${BATCH_IDS:-}" ]; then tr ',' '\n' <<<"$BATCH_IDS"
  else "$PY" -c 'import json,sys;[print(json.loads(l)["batch_id"]) for l in open(sys.argv[1])]' "$BATCHES" 2>/dev/null \
       || python3 -c 'import json,sys;[print(json.loads(l)["batch_id"]) for l in open(sys.argv[1])]' "$BATCHES"; fi
}

alive() { [ -f "$CTRL/RUNNING" ] && kill -0 "$(cat "$CTRL/RUNNING")" 2>/dev/null; }

case "${1:-}" in
  --launch)
    if alive; then echo "CONTROLLER_ALREADY_RUNNING pid=$(cat "$CTRL/RUNNING")"; exit 0; fi
    mkdir -p "$CTRL/logs"
    nohup bash -c "echo \$\$ >'$CTRL/RUNNING'; for l in \$(seq 0 $((LANES-1))); do bash '$0' --lane \$l & done; wait; rm -f '$CTRL/RUNNING'" \
      >>"$CTRL/controller.log" 2>&1 &
    sleep 1; echo "LAUNCHED pid=$(cat "$CTRL/RUNNING" 2>/dev/null || echo '?') lanes=$LANES threads=$THREADS";;
  --lane) lane "$2";;
  --foreground) mkdir -p "$CTRL/logs"; for l in $(seq 0 $((LANES-1))); do lane "$l" & done; wait;;
  --status)
    total=$(wc -l <"$BATCHES"); fin=$(ls "$CAMPAIGN"/batches/*/production/FINISHED.json 2>/dev/null | wc -l)
    comp=$(ls "$CAMPAIGN"/batches/*/attempt_*/COMPLETE.json 2>/dev/null | wc -l)
    echo "{\"batches\": $total, \"raw_complete_attempts\": $comp, \"finished\": $fin, \"controller_alive\": $(alive && echo true || echo false)}";;
  *) echo "usage: $0 --launch|--foreground|--status"; exit 64;;
esac

"""E5 scheduled-arrival measurements and immutable failure/reacquisition ledger.

Synthetic clocks are supported for tests, but can NEVER produce hardware PASS.
An output is delivered once through the sink. Late information never revises it.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
try:
    import resource
except ImportError:  # Windows: explicitly unavailable, not fabricated.
    resource = None
import time
from typing import Callable
import numpy as np
from .contracts import ContractError


@dataclass(frozen=True)
class Arrival:
    index: int
    arrival_s: float
    source_t: float
    pose_id: int
    available: bool = True
    fault: str = "NONE"


def arrivals(case, fault="NONE") -> list[Arrival]:
    n = len(case.t)
    if fault not in {"NONE", "DROP_2", "DROP_5", "DROP_10", "DUPLICATE", "REORDER", "DELAY", "NULL_CIR", "STALE_HISTORY"}:
        raise ContractError("UNKNOWN_ARRIVAL_FAULT")
    rows = []
    pivot = min(max(n//3, 1), n-1)
    gap = int(fault.split("_")[1]) if fault.startswith("DROP_") else 0
    for k in range(n):
        due = float(case.t[k]-case.t[0])
        present = not (pivot <= k < pivot+gap)
        if fault == "STALE_HISTORY" and pivot <= k < pivot+min(12, n-pivot):
            present = False
        if fault == "DELAY" and k == pivot:
            due += .6
        if fault == "REORDER" and k == pivot:
            due += .4
        row = Arrival(k, due, float(case.t[k]), int(case.pose_id[k]), present, fault)
        rows.append(row)
        if fault == "DUPLICATE" and k == pivot:
            rows.append(Arrival(k, due+.001, row.source_t, row.pose_id, True, fault))
    return sorted(rows, key=lambda r: (r.arrival_s, r.index))


class DeadlineRunner:
    def __init__(self, processor, *, clock_ns: Callable = time.perf_counter_ns,
                 sleep: Callable = time.sleep, sink: Callable = lambda value: None,
                 synthetic_clock: bool = False, hardware_id: str | None = None):
        if not synthetic_clock and (clock_ns is not time.perf_counter_ns or sleep is not time.sleep):
            raise ContractError("CUSTOM_CLOCK_REQUIRES_SYNTHETIC_LABEL")
        self.processor, self.clock, self.sleep, self.sink = processor, clock_ns, sleep, sink
        self.synthetic_clock = synthetic_clock
        self.hardware_id = hardware_id

    def run(self, events: list[Arrival]) -> dict:
        if not events:
            raise ContractError("EMPTY_RUNTIME_SCHEDULE")
        if any(type(e.index) is not int or type(e.pose_id) is not int or
               not np.isfinite([e.arrival_s, e.source_t]).all() or e.arrival_s < 0 for e in events):
            raise ContractError("INVALID_ARRIVAL_TIME")
        if any(events[k].arrival_s > events[k+1].arrival_s for k in range(len(events)-1)):
            raise ContractError("ARRIVALS_MUST_BE_SORTED_BY_ACTUAL_ARRIVAL")
        if not self.synthetic_clock and not self.hardware_id:
            raise ContractError("HARDWARE_ID_REQUIRED_FOR_REAL_TIMING")
        case = self.processor.case
        start = self.clock()
        records, emitted = [], set()
        for event_position, event in enumerate(events):
            due = start+round(event.arrival_s*1e9)
            if self.clock() < due:
                self.sleep((due-self.clock())/1e9)
            began = self.clock()
            backlog = sum(start+round(e.arrival_s*1e9) <= began for e in events[event_position+1:])
            if not 0 <= event.index < len(case.t):
                status, output = "REJECT_INVALID_INDEX", None
            elif event.source_t != float(case.t[event.index]) or event.pose_id != int(case.pose_id[event.index]):
                status, output = "REJECT_SOURCE_IDENTITY", None
            elif event.index <= self.processor.last_k:
                status, output = "REJECT_DUPLICATE_OR_LATE", None
            else:
                # Retain all elapsed controls, even when RF observations were lost.
                while self.processor.last_k+1 < event.index:
                    j = self.processor.last_k+1
                    missing = self.processor.step(j, available=False)
                    self.sink(missing)
                    done = self.clock()
                    emitted.add(j)
                    original_due = start+round((float(case.t[j])-float(case.t[0]))*1e9)
                    records.append(dict(index=j, status="PREDICT_ONLY_MISSING", latency_ms=(done-original_due)/1e6,
                                        output_ns=done, scheduled_ns=original_due, backlog=backlog, updated=False))
                output = self.processor.step(event.index, available=event.available)
                if event.index in emitted:
                    raise ContractError("SECOND_OUTPUT_FOR_PACKET")
                self.sink(output)  # include computation, serialization and sink flush.
                emitted.add(event.index)
                status = output["status"]
            done = self.clock()
            records.append(dict(index=event.index, status=status, latency_ms=(done-due)/1e6,
                                service_ms=(done-began)/1e6, output_ns=done, scheduled_ns=due,
                                backlog=backlog, updated=bool(output and output["updated"]), fault=event.fault))
        latency = np.array([r["latency_ms"] for r in records])
        if np.any(latency < 0):
            raise ContractError("MONOTONIC_CLOCK_VIOLATION")
        percentiles = dict(zip(("p50", "p95", "p99", "max"), map(float,
                           [np.quantile(latency, .5), np.quantile(latency, .95), np.quantile(latency, .99), latency.max()])))
        observed_pass = percentiles["p99"] <= 200.
        return dict(records=records, latency_ms=percentiles, unique_outputs=len(emitted),
                    source_packets=len(case.t), max_backlog=max(r["backlog"] for r in records),
                    peak_rss_native_units=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) if resource else None,
                    rss_units="platform resource.ru_maxrss native units", hardware_id=self.hardware_id,
                    clock="SYNTHETIC" if self.synthetic_clock else "PERF_COUNTER_NS",
                    status="SYNTHETIC_TIMING_NOT_HARDWARE" if self.synthetic_clock else
                    "OBSERVED_P99_PASS" if observed_pass else "REALTIME_HOLD",
                    scheduled_to_output_includes_sink=True, retrospective_output_replacement=False)

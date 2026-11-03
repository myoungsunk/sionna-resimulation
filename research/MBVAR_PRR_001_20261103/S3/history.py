"""Causal checkpoint selection and candidate validation for S3."""
from dataclasses import dataclass
from collections import deque
from copy import deepcopy
import math
import numpy as np

@dataclass
class Checkpoint:
    last_index: int
    timestamp: float
    config_hash: str
    filter_state: object

class History:
    def __init__(self, seconds, config_hash):
        if seconds not in (10, 30, 60):
            raise ValueError("unregistered history duration")
        self.seconds = seconds
        self.config_hash = config_hash
        self.checkpoints = deque()
        self.packets = deque()
        self.last_index = -1
        self.last_time = -math.inf
        self.next_checkpoint = -math.inf
        self.corrupt = False

    def save(self, index, timestamp, state):
        if index != self.last_index or timestamp < self.next_checkpoint:
            return
        if self.checkpoints and timestamp <= self.checkpoints[-1].timestamp:
            raise ValueError("nonmonotonic checkpoint")
        self.checkpoints.append(Checkpoint(index, timestamp, self.config_hash, deepcopy(state)))
        self.next_checkpoint = timestamp + 1.0 - 1e-10

    def append(self, index, timestamp, packet):
        if index != self.last_index + 1 or not math.isfinite(timestamp) or timestamp <= self.last_time:
            self.corrupt = True
            return False
        self.packets.append((index, timestamp, deepcopy(packet)))
        self.last_index = index
        self.last_time = timestamp
        cutoff = timestamp - self.seconds
        while self.packets and self.packets[0][1] < cutoff:
            self.packets.popleft()
        while self.checkpoints and self.checkpoints[0].timestamp < cutoff:
            self.checkpoints.popleft()
        return True

    def replay_input(self, episode_start, current_index):
        if self.corrupt or current_index != self.last_index:
            return None
        cp = next((c for c in reversed(self.checkpoints) if c.last_index < episode_start), None)
        if cp is None or cp.config_hash != self.config_hash:
            return None
        suffix = [p for p in self.packets if cp.last_index < p[0] <= current_index]
        if not suffix or [p[0] for p in suffix] != list(range(cp.last_index + 1, current_index + 1)):
            return None
        return deepcopy(cp), deepcopy(suffix)

def validate_candidate(current_x, candidate_x, candidate_P, end_index, current_index):
    if end_index != current_index:
        return "CANDIDATE_BEHIND"
    if not np.isfinite(candidate_x).all() or not np.isfinite(candidate_P).all():
        return "NONFINITE"
    d = np.array([.1, .1, math.radians(1), math.radians(.05)])
    C = candidate_P / d[:, None] / d[None, :]
    tol = 1e-12 * max(1., np.linalg.norm(C, ord=2))
    if np.linalg.norm(C - C.T, ord=2) > tol or np.linalg.eigvalsh((C + C.T) / 2)[0] < -tol:
        return "INVALID_COVARIANCE"
    dx = candidate_x - current_x
    angle = math.atan2(math.sin(dx[2]), math.cos(dx[2]))
    if np.linalg.norm(dx[:2]) > .5 or abs(angle) > math.radians(10) or abs(dx[3]) > math.radians(.1):
        return "CANDIDATE_OUT_OF_BOUNDS"
    return "ACCEPT"

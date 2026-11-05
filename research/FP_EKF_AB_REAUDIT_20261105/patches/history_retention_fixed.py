"""Causal checkpoint selection and candidate validation for S3."""
from dataclasses import dataclass
from collections import deque
from copy import deepcopy
import math
import numpy as np

def source_registry(pose_ids):
    values=np.asarray(pose_ids)
    if values.ndim!=1 or len(values)==0:
        raise ValueError("empty source pose registry")
    result=tuple(v.item() if isinstance(v,np.generic) else v for v in values)
    if any(v is None or isinstance(v,(float,np.floating)) and not math.isfinite(v) for v in result) or len(set(result))!=len(result):
        raise ValueError("invalid or duplicate source pose IDs")
    return result

@dataclass
class Checkpoint:
    last_index: int
    timestamp: float
    config_hash: str
    filter_state: object
    last_pose_id: object = None

class History:
    def __init__(self, seconds, config_hash, pose_ids):
        if seconds not in (10, 30, 60):
            raise ValueError("unregistered history duration")
        self.pose_ids=source_registry(pose_ids)
        self.seconds = seconds
        self.config_hash = config_hash
        self.checkpoints = deque()
        self.packets = deque()
        self.last_pose_id = None
        self.last_index = -1
        self.last_time = -math.inf
        self.next_checkpoint = -math.inf
        self.corrupt = False

    def save(self, index, timestamp, state):
        if index != self.last_index or timestamp < self.next_checkpoint:
            return
        if self.checkpoints and timestamp <= self.checkpoints[-1].timestamp:
            raise ValueError("nonmonotonic checkpoint")
        expected=None if index==-1 else self.pose_ids[index]
        if expected!=self.last_pose_id:
            raise ValueError("checkpoint source ID mismatch")
        if hasattr(state,"last_pose_id") and state.last_pose_id!=expected:
            raise ValueError("checkpoint filter source ID mismatch")
        self.checkpoints.append(Checkpoint(index, timestamp, self.config_hash, deepcopy(state),expected))
        self.next_checkpoint = timestamp + 1.0 - 1e-10

    def append(self, index, timestamp, packet):
        source=packet.get("pose_id")
        if index<0 or index>=len(self.pose_ids) or source!=self.pose_ids[index] or index != self.last_index + 1 or not math.isfinite(timestamp) or timestamp <= self.last_time:
            self.corrupt = True
            return False
        self.packets.append((index, timestamp, deepcopy(packet)))
        self.last_pose_id = self.pose_ids[index]
        self.last_index = index
        self.last_time = timestamp
        cutoff = timestamp - self.seconds
        while self.packets and self.packets[0][1] < cutoff:
            self.packets.popleft()
        while len(self.checkpoints) > 1 and self.checkpoints[1].timestamp < cutoff:
            self.checkpoints.popleft()
        return True

    def replay_input(self, episode_start, current_index):
        if self.corrupt or current_index != self.last_index:
            return None
        cp = next((c for c in reversed(self.checkpoints) if c.last_index < episode_start), None)
        if cp is None or cp.config_hash != self.config_hash or cp.last_pose_id!=(None if cp.last_index==-1 else self.pose_ids[cp.last_index]):
            return None
        if hasattr(cp.filter_state,"last_pose_id") and (cp.filter_state.last_pose_id!=cp.last_pose_id or cp.filter_state.last_index!=cp.last_index or cp.filter_state.source_pose_ids!=self.pose_ids):
            return None
        suffix = [p for p in self.packets if cp.last_index < p[0] <= current_index]
        if not suffix or [p[0] for p in suffix] != list(range(cp.last_index + 1, current_index + 1)):
            return None
        if any(packet.get("pose_id")!=self.pose_ids[index] for index,_,packet in suffix):
            return None
        if self.last_pose_id!=self.pose_ids[current_index]:
            return None
        return deepcopy(cp), deepcopy(suffix)

def validate_candidate(current_x, candidate_x, candidate_P, end_index, current_index, *, end_pose_id, current_pose_id):
    if end_index != current_index:
        return "CANDIDATE_BEHIND"
    if end_pose_id is None or end_pose_id!=current_pose_id:
        return "SOURCE_ID_MISMATCH"
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

"""Independent ungrouped F64 sum and identifiable surface-chain grouping.

No simulator imports: synthetic verification does not trace RF paths.
"""
import hashlib
import json
import math

import numpy as np


def independent_sum(raw_a, raw_tau, frequency):
    """Scalar trig + compensated real/imag sums, never reads grouped fields."""
    answer = np.empty(2, np.complex128)
    for rx in range(2):
        real, imag = [], []
        for value, delay in zip(raw_a[rx, 0], raw_tau):
            phase = -2 * math.pi * float(frequency) * float(delay)
            c, s = math.cos(phase), math.sin(phase)
            ar, ai = float(value.real), float(value.imag)
            real.append(ar * c - ai * s)
            imag.append(ar * s + ai * c)
        answer[rx] = complex(math.fsum(real), math.fsum(imag))
    return answer


def vector_fields(raw_a, raw_tau, frequency):
    return (raw_a[:, 0, :].astype(np.complex128)
            * np.exp(-2j * np.pi * float(frequency)
                     * raw_tau.astype(np.float64))[None, :]).T


def label_chain(objects, interactions, lookup, valid):
    if not valid:
        return 'INVALID'
    chain = []
    for source_id, interaction in zip(objects, interactions):
        source_id, interaction = int(source_id), int(interaction)
        if source_id in (-1, 4294967295):
            if interaction != 0:
                raise ValueError('interaction without scene object')
            continue
        if source_id not in lookup:
            raise ValueError('unknown source scene object ' + str(source_id))
        if interaction == 0:
            raise ValueError('scene object without interaction')
        chain.append([lookup[source_id], interaction])
    return (json.dumps(chain, separators=(',', ':')) if chain else 'DIRECT')


def grouped_spectra(bins):
    """Group by exact ordered semantic object/type chain; no ray-index pairing."""
    labels = sorted({label for row in bins for label in row['labels']})
    if labels.count('DIRECT') != 1:
        raise ValueError('missing DIRECT group')
    groups = {label: i for i, label in enumerate(labels)}
    fields = np.zeros((len(labels), len(bins), 2), np.complex128)
    counts = np.zeros((len(labels), len(bins)), np.int32)
    raw_group = []
    for fi, row in enumerate(bins):
        for j, label in enumerate(row['labels']):
            gi = groups[label]
            fields[gi, fi] += row['fields'][j]
            counts[gi, fi] += 1
            raw_group.append(gi)
    return dict(group_fields=fields, group_labels=np.asarray(labels),
                group_ids=np.asarray([hashlib.sha256(s.encode()).hexdigest()
                                      for s in labels]),
                group_count=counts, group_missing=counts == 0,
                source_group=np.asarray(raw_group, np.int32),
                direct_group=np.asarray(groups['DIRECT'], np.int32))


def errors(actual, reference):
    difference = np.asarray(actual) - reference
    return dict(relative_l2=float(np.linalg.norm(difference)
                                 / max(np.linalg.norm(reference), 1e-300)),
                max_absolute=float(np.max(np.abs(difference))),
                max_normalized=float(np.max(np.abs(difference))
                                     / max(np.max(np.abs(reference)), 1e-300)))

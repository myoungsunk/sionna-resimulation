"""Opt-in pre-field finite-face guard for the frozen, axis-aligned TB3 F1 scenes."""
from __future__ import annotations

import drjit as dr
import numpy as np

from tb3_g6_face_match import EXACT_HIT_TOL_M, ImageGeometryError, fold_images


class FiniteFaceGuard:
    """Mask invalid specular paths on a pinned Sionna RT 2.0.1 PathSolver."""

    def __init__(self, solver, mi, scene, mesh_faces, tx, rx, interaction_type):
        self._calculate = solver._field_calculator
        self._mi = mi
        self._tx = tuple(tx)
        self.set_receiver(rx)
        self._none, self._specular = interaction_type.NONE, interaction_type.SPECULAR
        shapes = scene.mi_scene.shapes()
        pointers = np.asarray(dr.reinterpret_array(mi.UInt, mi.ShapePtr(shapes)))
        self._objects = {int(pointer): int(scene.objects[shape.id()].object_id)
                         for pointer, shape in zip(pointers, shapes, strict=True)}
        if set(self._objects.values()) != set(mesh_faces):
            raise ValueError("Pre-field shapes do not cover the frozen reflection meshes")
        self._mesh_faces = mesh_faces
        self.rejected = []
        solver._field_calculator = self

    def set_receiver(self, rx):
        """Start validation for a new frozen receiver position."""
        self._rx = tuple(rx)
        self._decisions = {}

    def _check_chain(self, chain):
        faces = [self._mesh_faces[obj][1][primitive] for obj, primitive in chain]
        try:
            _, points = fold_images(self._tx, self._rx, faces)
            for face, point in zip(faces, points, strict=True):
                if not any(triangle.contains(point, EXACT_HIT_TOL_M) for _, triangle in face.primitives):
                    raise ImageGeometryError(f"Image hit outside the connected finite face {face.label}")
        except ImageGeometryError as error:
            return str(error), ">".join(face.label for face in faces)
        return None

    def __call__(self, **kwargs):
        paths = kwargs["paths"]
        self.rejected = []
        valid = np.asarray(paths.valid, dtype=bool).copy()
        rows = np.flatnonzero(valid)
        if len(rows):
            events = np.asarray(paths.interaction_types)[rows]
            shapes = np.asarray(paths.shapes)[rows]
            primitives = np.asarray(paths.primitives)[rows]
            for row, row_events, row_shapes, row_primitives in zip(
                    rows, events, shapes, primitives, strict=True):
                active = row_events != self._none
                count = int(active.sum())
                if not count:
                    continue
                if not active[:count].all() or np.any(row_events[:count] != self._specular):
                    raise ValueError("Finite-face guard requires ordered F1 specular interactions")
                chain = tuple((self._objects[int(shape)], int(primitive))
                              for shape, primitive in zip(row_shapes[:count], row_primitives[:count], strict=True))
                if chain not in self._decisions:
                    self._decisions[chain] = self._check_chain(chain)
                failure = self._decisions[chain]
                if failure is not None:
                    reason, face_sequence = failure
                    valid[row] = False
                    self.rejected.append(dict(lane=int(row), chain=list(chain), reason=reason,
                                              face_sequence=face_sequence))

        if self.rejected:
            vertices = np.stack([np.asarray(getattr(paths, "vertices_" + axis)) for axis in "xyz"], axis=-1)
            for record in self.rejected:
                record["vertices_m"] = vertices[record["lane"], :len(record["chain"])].tolist()
            paths.valid = self._mi.Bool(valid)
        return self._calculate(**kwargs)

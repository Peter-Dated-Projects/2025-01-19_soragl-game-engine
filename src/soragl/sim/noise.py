"""Seeded 2D value noise in numpy, for procedural generation.

Deterministic for a given `numpy.random.Generator` state, so the same seed gives the same
terrain on every machine. Arrays are shaped `(width, height)` and indexed `[x, y]`.
"""

import numpy as np


def _smooth(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def value_noise(
    rng: np.random.Generator, width: int, height: int, cell: float
) -> np.ndarray:
    """Smoothly interpolated lattice noise in [0, 1] with features about `cell` wide."""
    cell = max(float(cell), 1.0)
    gw = int(np.ceil(width / cell)) + 2
    gh = int(np.ceil(height / cell)) + 2
    lattice = rng.random((gw, gh))
    # random sub-cell offset so octaves do not line up on the lattice
    ox, oy = rng.random(2) * cell
    xs = (np.arange(width) + ox) / cell
    ys = (np.arange(height) + oy) / cell
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    tx = _smooth(xs - x0)[:, None]
    ty = _smooth(ys - y0)[None, :]
    a = lattice[x0[:, None], y0[None, :]]
    b = lattice[x0[:, None] + 1, y0[None, :]]
    c = lattice[x0[:, None], y0[None, :] + 1]
    d = lattice[x0[:, None] + 1, y0[None, :] + 1]
    top = a + (b - a) * tx
    bottom = c + (d - c) * tx
    return top + (bottom - top) * ty


def fbm(
    rng: np.random.Generator,
    width: int,
    height: int,
    cell: float,
    octaves: int = 4,
    persistence: float = 0.5,
) -> np.ndarray:
    """Fractal sum of `octaves` value-noise layers, rescaled to exactly [0, 1]."""
    total = np.zeros((width, height))
    amplitude = 1.0
    for _ in range(octaves):
        total += value_noise(rng, width, height, cell) * amplitude
        amplitude *= persistence
        cell /= 2.0
    lo, hi = total.min(), total.max()
    return (total - lo) / max(hi - lo, 1e-9)

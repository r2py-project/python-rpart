"""Smoke test for rpartexp2 (the simplest entry point with no external deps)."""

import numpy as np
import pytest


def test_rpartexp2_basic():
    import r2py_rpart

    dtimes = np.array([1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 5.0], dtype=np.float64)
    keep = r2py_rpart.rpartexp2(dtimes)

    assert keep.dtype == np.int32
    assert len(keep) == len(dtimes)
    assert set(np.unique(keep)).issubset({0, 1})


def test_rpartexp2_all_unique():
    import r2py_rpart

    dtimes = np.array([1.0, 2.0, 4.0, 8.0], dtype=np.float64)
    keep = r2py_rpart.rpartexp2(dtimes)
    assert len(keep) == 4

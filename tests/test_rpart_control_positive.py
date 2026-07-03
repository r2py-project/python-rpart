"""Positive-path parity tests for r2py_rpart.rpart_control vs. R's
rpart::rpart.control.

Each test calls both R's rpart.control(...) (via rpy2) and Python's
rpart_control(...) with an identical set of keyword arguments, then asserts
that every element of the returned "list of options" matches -- covering
every documented parameter (minsplit, minbucket, cp, maxcompete,
maxsurrogate, usesurrogate, xval, surrogatestyle, maxdepth, ...) both
individually and in combination.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing, in particular
r_rpart_control() (calls R's rpart.control() and returns a plain dict).
"""
from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.rpart_control import rpart_control

from _r_rpart_helpers import r_rpart_control


def _assert_matches_r(py_result: dict, r_result: dict, *, keys: list[str] | None = None) -> None:
    """Assert every (or a chosen subset of) key in py_result numerically
    matches the corresponding key in r_result."""
    for key in keys or r_result.keys():
        assert key in py_result, f"Python result missing key {key!r}"
        assert_allclose(np.asarray(py_result[key], dtype=float), np.asarray(r_result[key], dtype=float))


# ---------------------------------------------------------------------------
# 1. All defaults.
# ---------------------------------------------------------------------------

def test_rpart_control_defaults_match_r():
    r_out = r_rpart_control()
    py_out = rpart_control()

    _assert_matches_r(py_out, r_out)
    assert py_out["minsplit"] == 20
    assert py_out["minbucket"] == 7
    assert py_out["cp"] == 0.01
    assert py_out["maxcompete"] == 4
    assert py_out["maxsurrogate"] == 5
    assert py_out["usesurrogate"] == 2
    assert py_out["surrogatestyle"] == 0
    assert py_out["maxdepth"] == 30
    assert py_out["xval"] == 10


# ---------------------------------------------------------------------------
# 2. minsplit supplied alone: minbucket = round(minsplit / 3).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("minsplit", [15, 21, 100, 3])
def test_rpart_control_minsplit_only_derives_minbucket_matches_r(minsplit):
    r_out = r_rpart_control(minsplit=minsplit)
    py_out = rpart_control(minsplit=minsplit)

    _assert_matches_r(py_out, r_out)
    assert py_out["minsplit"] == minsplit
    assert py_out["minbucket"] == round(minsplit / 3)


# ---------------------------------------------------------------------------
# 3. minbucket supplied alone: minsplit = minbucket * 3.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("minbucket", [9, 1, 50])
def test_rpart_control_minbucket_only_derives_minsplit_matches_r(minbucket):
    r_out = r_rpart_control(minbucket=minbucket)
    py_out = rpart_control(minbucket=minbucket)

    _assert_matches_r(py_out, r_out)
    assert py_out["minbucket"] == minbucket
    assert py_out["minsplit"] == minbucket * 3


# ---------------------------------------------------------------------------
# 4. Both minsplit and minbucket supplied explicitly: neither is
#    back-derived from the other, even if "inconsistent".
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_and_minbucket_both_supplied_matches_r():
    r_out = r_rpart_control(minsplit=15, minbucket=9)
    py_out = rpart_control(minsplit=15, minbucket=9)

    _assert_matches_r(py_out, r_out)
    assert py_out["minsplit"] == 15
    assert py_out["minbucket"] == 9


# ---------------------------------------------------------------------------
# 5. Non-default cp.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cp", [0.05, 0.0, 1.0, 1e-6])
def test_rpart_control_cp_non_default_matches_r(cp):
    r_out = r_rpart_control(cp=cp)
    py_out = rpart_control(cp=cp)

    _assert_matches_r(py_out, r_out)
    assert py_out["cp"] == cp


# ---------------------------------------------------------------------------
# 6. Non-default maxcompete / maxsurrogate (including 0, which disables
#    the corresponding search).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("maxcompete,maxsurrogate", [(2, 0), (0, 0), (10, 10)])
def test_rpart_control_maxcompete_and_maxsurrogate_matches_r(maxcompete, maxsurrogate):
    r_out = r_rpart_control(maxcompete=maxcompete, maxsurrogate=maxsurrogate)
    py_out = rpart_control(maxcompete=maxcompete, maxsurrogate=maxsurrogate)

    _assert_matches_r(py_out, r_out)
    assert py_out["maxcompete"] == maxcompete
    assert py_out["maxsurrogate"] == maxsurrogate


# ---------------------------------------------------------------------------
# 7. Every valid usesurrogate value (0, 1, 2) is accepted unchanged, with
#    no warning.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("usesurrogate", [0, 1, 2])
def test_rpart_control_usesurrogate_valid_values_match_r(usesurrogate):
    r_out = r_rpart_control(usesurrogate=usesurrogate)
    py_out = rpart_control(usesurrogate=usesurrogate)

    _assert_matches_r(py_out, r_out)
    assert py_out["usesurrogate"] == usesurrogate


# ---------------------------------------------------------------------------
# 8. Every valid surrogatestyle value (0, 1) is accepted unchanged, with
#    no warning.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("surrogatestyle", [0, 1])
def test_rpart_control_surrogatestyle_valid_values_match_r(surrogatestyle):
    r_out = r_rpart_control(surrogatestyle=surrogatestyle)
    py_out = rpart_control(surrogatestyle=surrogatestyle)

    _assert_matches_r(py_out, r_out)
    assert py_out["surrogatestyle"] == surrogatestyle


# ---------------------------------------------------------------------------
# 9. Non-default scalar xval.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("xval", [0, 1, 5, 20])
def test_rpart_control_xval_scalar_non_default_matches_r(xval):
    r_out = r_rpart_control(xval=xval)
    py_out = rpart_control(xval=xval)

    _assert_matches_r(py_out, r_out)
    assert py_out["xval"] == xval


# ---------------------------------------------------------------------------
# 10. xval as a (non-negative) vector -- rpart.control supports a per-
#     observation cross-validation grouping vector, not just a fold count.
# ---------------------------------------------------------------------------

def test_rpart_control_xval_vector_matches_r():
    xval = np.array([1, 2, 3, 1, 2, 3, 1, 2, 3, 1])
    r_out = r_rpart_control(xval=xval)
    py_out = rpart_control(xval=xval)

    assert_allclose(np.asarray(py_out["xval"], dtype=float), np.asarray(r_out["xval"], dtype=float))
    for key in ("minsplit", "minbucket", "cp", "maxcompete", "maxsurrogate", "usesurrogate", "surrogatestyle", "maxdepth"):
        _assert_matches_r(py_out, r_out, keys=[key])


# ---------------------------------------------------------------------------
# 11. maxdepth at valid boundary values (1, mid-range, 30).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("maxdepth", [1, 15, 30])
def test_rpart_control_maxdepth_boundary_values_match_r(maxdepth):
    r_out = r_rpart_control(maxdepth=maxdepth)
    py_out = rpart_control(maxdepth=maxdepth)

    _assert_matches_r(py_out, r_out)
    assert py_out["maxdepth"] == maxdepth


# ---------------------------------------------------------------------------
# 12. Unrecognized "..." kwargs are silently mopped up (accepted, but not
#     included in the returned options), exactly like R's rpart.control's
#     `...`.
# ---------------------------------------------------------------------------

def test_rpart_control_kwargs_passthrough_ignored_matches_r():
    r_out = r_rpart_control(foo=1, bar=2)
    py_out = rpart_control(foo=1, bar=2)

    assert "foo" not in py_out and "bar" not in py_out
    _assert_matches_r(py_out, r_out)


# ---------------------------------------------------------------------------
# 13. A combination of many non-default parameters at once (integration
#     of the whole formal parameter list simultaneously).
# ---------------------------------------------------------------------------

def test_rpart_control_all_non_default_combination_matches_r():
    kwargs = dict(
        minsplit=12,
        minbucket=4,
        cp=0.02,
        maxcompete=1,
        maxsurrogate=2,
        usesurrogate=1,
        surrogatestyle=1,
        maxdepth=8,
        xval=3,
    )
    r_out = r_rpart_control(**kwargs)
    py_out = rpart_control(**kwargs)

    _assert_matches_r(py_out, r_out)
    for key, value in kwargs.items():
        assert py_out[key] == value


# ---------------------------------------------------------------------------
# 14. maxcompete/maxsurrogate as non-integer floats: rpart.control performs
#     no int-coercion/validation on these, so a "weird" float value simply
#     passes straight through in both implementations.
# ---------------------------------------------------------------------------

def test_rpart_control_maxcompete_non_integer_float_matches_r():
    r_out = r_rpart_control(maxcompete=2.7)
    py_out = rpart_control(maxcompete=2.7)

    _assert_matches_r(py_out, r_out)
    assert py_out["maxcompete"] == 2.7


# ---------------------------------------------------------------------------
# 15. cp given as a boolean: R has no strict type-checking on cp, so TRUE
#     (numeric 1) passes straight through -- Python's bool (an int subclass)
#     behaves identically.
# ---------------------------------------------------------------------------

def test_rpart_control_cp_as_boolean_matches_r():
    r_out = r_rpart_control(cp=True)
    py_out = rpart_control(cp=True)

    assert py_out["cp"] == r_out["cp"] == 1

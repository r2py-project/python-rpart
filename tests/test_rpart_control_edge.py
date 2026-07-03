"""Boundary/edge-case parity tests for r2py_rpart.rpart_control vs. R's
rpart::rpart.control.

These exercise functional extremes: Inf/-Inf and near-boundary maxdepth
values, cp/minsplit/minbucket at 0, empty (length-0) vectors, a
cross-validation grouping vector that mixes negative and non-negative
folds, and R's NULL (Python's closest analogue is None, though the two
diverge -- see below).

Two of these tests document *known, currently-real* divergences (R's
NULL/empty-vector propagation through arithmetic never errors, while
Python's builtin round() rejects both an empty numpy array and None
outright) -- written, per this project's established convention (see
test_rpart_edge.py), to assert the actual observed behavior with a
docstring explaining the root cause, rather than a false parity claim.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.rpart_control import rpart_control

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    r_control,
    r_error_message,
    r_rpart_control,
    r_rpart_control_capturing_warning,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. maxdepth = +Inf: `Inf > 30` is TRUE in both languages, so this hits
#    the same "Maximum depth is 30" error as any other over-30 value.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_positive_infinity_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=float("inf"))))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=float("inf"))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=+Inf")


# ---------------------------------------------------------------------------
# 2. maxdepth = -Inf: fails the *first* guard (`> 30`) as FALSE, then the
#    second guard (`< 1`) as TRUE, so the error message is the "at least
#    1" one, not the "is 30" one -- both implementations agree exactly on
#    which of the two messages fires.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_negative_infinity_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=float("-inf"))))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=float("-inf"))

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=-Inf")
    assert "at least 1" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. maxdepth = 30.5: a float strictly between 30 and 31 still trips the
#    "> 30" guard (there is no int-truncation before the comparison).
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_float_just_above_30_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=30.5)))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=30.5)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=30.5")


# ---------------------------------------------------------------------------
# 4. maxdepth = 1.9999: strictly less than 2 but comfortably within
#    [1, 30] -- both implementations must accept it unchanged (no implicit
#    rounding/truncation to an integer).
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_float_just_above_1_matches_r():
    r_out = r_rpart_control(maxdepth=1.9999)
    py_out = rpart_control(maxdepth=1.9999)

    assert py_out["maxdepth"] == r_out["maxdepth"] == 1.9999


# ---------------------------------------------------------------------------
# 5. xval as a vector mixing negative and non-negative folds: the *entire*
#    xval is replaced by the scalar 0 (not just the negative entries
#    zeroed in place) in both implementations.
# ---------------------------------------------------------------------------

def test_rpart_control_xval_vector_with_negative_entry_resets_to_scalar_zero_matches_r():
    xval = np.array([1, -2, 3])
    r_out, r_warning = r_rpart_control_capturing_warning(xval=xval)
    assert r_warning is not None and "xval" in r_warning

    import warnings as _warnings
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        py_out = rpart_control(xval=xval)
        assert len(caught) == 1

    assert r_out["xval"] == 0
    assert py_out["xval"] == 0


# ---------------------------------------------------------------------------
# 6. xval = 0 exactly: the boundary of the "< 0" guard -- 0 is *not*
#    negative, so no warning fires and 0 passes straight through.
# ---------------------------------------------------------------------------

def test_rpart_control_xval_zero_boundary_no_warning_matches_r():
    import warnings as _warnings
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        py_out = rpart_control(xval=0)
        assert len(caught) == 0

    r_out, r_warning = r_rpart_control_capturing_warning(xval=0)
    assert r_warning is None
    assert py_out["xval"] == r_out["xval"] == 0


# ---------------------------------------------------------------------------
# 7. minbucket = 0 alone (minsplit unsupplied): minsplit is back-derived
#    as minbucket * 3 = 0, a degenerate-but-permitted value in both.
# ---------------------------------------------------------------------------

def test_rpart_control_minbucket_zero_matches_r():
    r_out = r_rpart_control(minbucket=0)
    py_out = rpart_control(minbucket=0)

    assert py_out["minbucket"] == r_out["minbucket"] == 0
    assert py_out["minsplit"] == r_out["minsplit"] == 0


# ---------------------------------------------------------------------------
# 8. minsplit = 0 alone (minbucket unsupplied): minbucket is derived as
#    round(0 / 3) = 0.
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_zero_matches_r():
    r_out = r_rpart_control(minsplit=0)
    py_out = rpart_control(minsplit=0)

    assert py_out["minsplit"] == r_out["minsplit"] == 0
    assert py_out["minbucket"] == r_out["minbucket"] == 0


# ---------------------------------------------------------------------------
# 9. cp = 0: the minimum valid complexity parameter (effectively disables
#    all pruning). rpart.control performs no validation on cp at all, so
#    0 (and even negative values -- see test 10) simply pass through.
# ---------------------------------------------------------------------------

def test_rpart_control_cp_zero_matches_r():
    r_out = r_rpart_control(cp=0)
    py_out = rpart_control(cp=0)

    assert py_out["cp"] == r_out["cp"] == 0


# ---------------------------------------------------------------------------
# 10. cp negative: rpart.control has no range check on cp whatsoever, so a
#     negative (nonsensical, but never validated) value passes straight
#     through unchanged in both implementations.
# ---------------------------------------------------------------------------

def test_rpart_control_cp_negative_matches_r():
    r_out = r_rpart_control(cp=-1)
    py_out = rpart_control(cp=-1)

    assert py_out["cp"] == r_out["cp"] == -1


# ---------------------------------------------------------------------------
# 11. minsplit negative (minbucket unsupplied): exercises "round half to
#     even" banker's-rounding parity between R's round() and Python's
#     builtin round() on a negative fraction (round(-100/3) ==
#     round(-33.333...) == -33 in both).
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_negative_matches_r():
    r_out = r_rpart_control(minsplit=-100)
    py_out = rpart_control(minsplit=-100)

    assert py_out["minsplit"] == r_out["minsplit"] == -100
    assert py_out["minbucket"] == r_out["minbucket"] == -33


# ---------------------------------------------------------------------------
# 12. Empty (length-0) xval and cp vectors: `any(numeric(0) < 0)` is
#     FALSE in R and `np.any(np.asarray([]) < 0)` is also False in numpy,
#     so both simply return the empty vector/array unchanged -- a case
#     where R's and Python's "empty is vacuously not-negative" semantics
#     happen to agree exactly.
# ---------------------------------------------------------------------------

def test_rpart_control_empty_xval_and_cp_vectors_match_r():
    r_out = r_rpart_control(xval=np.array([]), cp=np.array([]))
    py_out = rpart_control(xval=np.array([]), cp=np.array([]))

    assert list(r_out["xval"]) == []
    assert_allclose(np.asarray(py_out["xval"]), np.array([]))
    assert list(r_out["cp"]) == []
    assert_allclose(np.asarray(py_out["cp"]), np.array([]))


# ---------------------------------------------------------------------------
# 13. KNOWN DIVERGENCE: an empty (length-0) minsplit array, minbucket
#     unsupplied. R's round(numeric(0) / 3) vectorizes over zero elements
#     with no error, returning minsplit=minbucket=numeric(0). Python's
#     builtin round() does not support numpy arrays at all
#     ("type numpy.ndarray doesn't define __round__ method"), erroring
#     even on this vacuous, zero-element case.
# ---------------------------------------------------------------------------

def test_rpart_control_empty_minsplit_array_is_a_known_python_gap():
    r_msg = r_error_message(lambda: run_r(r_control(minsplit=np.array([]))))
    assert r_msg is None, "R is expected to vectorize round(numeric(0)/3) without error"

    with pytest.raises(TypeError):
        rpart_control(minsplit=np.array([]))


# ---------------------------------------------------------------------------
# 14. KNOWN DIVERGENCE: minsplit = R's NULL (Python's closest analogue,
#     None). R's round(NULL / 3) evaluates to numeric(0) with no error,
#     leaving minsplit itself as NULL and minbucket as numeric(0). Python
#     has no "empty scalar" concept comparable to R's NULL; None / 3
#     raises TypeError immediately in the round(minsplit / 3) computation.
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_none_is_a_known_python_gap():
    r_msg = r_error_message(lambda: run_r("rpart.control(minsplit=NULL)"))
    assert r_msg is None, "R is expected to silently accept minsplit=NULL"

    with pytest.raises(TypeError):
        rpart_control(minsplit=None)

"""Negative-path parity tests for r2py_rpart.rpart_control vs. R's
rpart::rpart.control.

For each invalid-input scenario we:
  1. Trigger the equivalent R call via rpy2 and capture the error text (or
     confirm R does *not* raise, for the documented divergences below).
  2. Call the Python `rpart_control()` and check whether it raises.
  3. If both raise but with different wording, warn (per the test-suite
     generation protocol) rather than fail -- message text is not part of
     rpart's documented contract, only "does it raise" is.

A handful of cases below are *documented, currently-real* R/Python
divergences uncovered while writing this suite (R's dynamic, loosely-typed
comparison/arithmetic operators tolerate inputs -- strings, vectors, NaN --
that Python's strict operators do not, and vice-versa for one case). Per
the project's established convention (see test_rpart_edge.py /
test_rpart_negative.py's "known divergence" tests), these are written to
assert the actual observed behavior of both implementations (with a
docstring explaining the root cause) rather than papering over the
mismatch -- they are a discovered-bug record, not a false parity claim.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from r2py_rpart.rpart_control import rpart_control

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    r_control,
    r_error_message,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. maxdepth just above the hard limit of 30.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_above_30_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=31)))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=31)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=31 (>30)")


# ---------------------------------------------------------------------------
# 2. maxdepth far above the hard limit.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_far_above_30_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=100)))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=100)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=100 (>30)")


# ---------------------------------------------------------------------------
# 3. maxdepth of exactly 0 (below the minimum of 1).
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_zero_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=0)))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=0)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=0 (<1)")


# ---------------------------------------------------------------------------
# 4. maxdepth negative.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_negative_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=-5)))

    with pytest.raises(Exception) as exc_info:
        rpart_control(maxdepth=-5)

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="maxdepth=-5 (<1)")


# ---------------------------------------------------------------------------
# 5. Non-numeric minsplit ("abc"), minbucket left unsupplied: this forces
#    both implementations to evaluate minbucket's default expression,
#    round(minsplit / 3), which fails immediately on a non-numeric type in
#    both R (`non-numeric argument to binary operator`) and Python
#    (`unsupported operand type(s) for /: 'str' and 'int'`).
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_non_numeric_string_raises_like_r():
    r_msg = r_error_message(lambda: run_r(r_control(minsplit="abc")))

    with pytest.raises(Exception) as exc_info:
        rpart_control(minsplit="abc")

    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="minsplit='abc' (minbucket unsupplied)")


# ---------------------------------------------------------------------------
# 6. KNOWN DIVERGENCE: non-numeric minbucket ("xyz"), minsplit left
#    unsupplied. R computes `minsplit <- minbucket * 3L`, which raises
#    ("non-numeric argument to binary operator") because `*` has no
#    string-repeat meaning in R. Python's rpart_control.py computes
#    `minsplit = minbucket * 3`, but Python's `*` operator *does* define
#    string-repetition semantics ("xyz" * 3 == "xyzxyzxyz"), so no
#    exception is raised at all -- Python silently returns a nonsensical
#    string-valued minsplit instead of rejecting the input like R does.
#    This is a real, reproducible gap in rpart_control.py's input
#    validation (it has no type/numeric check on minbucket), not a
#    tolerance/formatting difference -- documented here rather than
#    papered over.
# ---------------------------------------------------------------------------

def test_rpart_control_minbucket_non_numeric_string_is_a_known_python_validation_gap():
    r_msg = r_error_message(lambda: run_r(r_control(minbucket="xyz")))
    assert r_msg is not None, "R is expected to raise on minbucket='xyz' (non-numeric argument to `*`)"

    # Python does NOT raise here: str.__mul__ silently repeats the string.
    py_out = rpart_control(minbucket="xyz")
    assert py_out["minsplit"] == "xyz" * 3
    assert py_out["minbucket"] == "xyz"


# ---------------------------------------------------------------------------
# 7. KNOWN DIVERGENCE: maxdepth = NaN. R's `if (maxdepth > 30L) ...`
#    evaluates `NaN > 30` to NA, and `if (NA)` is itself a hard error in R
#    ("missing value where TRUE/FALSE needed") -- so R rejects NaN
#    entirely. Python's `if maxdepth > 30` evaluates `float('nan') > 30` to
#    plain `False` (IEEE-754 comparisons involving NaN are simply False,
#    they don't raise), so neither the `> 30` nor the `< 1` guard ever
#    fires and rpart_control() happily returns maxdepth=nan. This is a
#    real behavioral gap (Python fails to reject an input R explicitly
#    guards against), not a message-wording difference.
# ---------------------------------------------------------------------------

def test_rpart_control_maxdepth_nan_is_a_known_python_validation_gap():
    r_msg = r_error_message(lambda: run_r(r_control(maxdepth=float("nan"))))
    assert r_msg is not None, "R is expected to raise on maxdepth=NaN (missing value where TRUE/FALSE needed)"

    # Python does NOT raise: NaN comparisons are simply False, not an error.
    py_out = rpart_control(maxdepth=float("nan"))
    assert py_out["maxdepth"] != py_out["maxdepth"]  # NaN != NaN


# ---------------------------------------------------------------------------
# 8. KNOWN DIVERGENCE (opposite direction): minsplit = NaN, minbucket
#    unsupplied. R's `round(NaN / 3)` propagates NaN with no error at all
#    (rpart.control(minsplit=NaN) succeeds, returning minsplit=minbucket=
#    NaN). Python's builtin `round(float('nan'))` *raises*
#    ("cannot convert float NaN to integer") -- so here it is Python that
#    is stricter than R, rejecting an input R silently accepts.
# ---------------------------------------------------------------------------

def test_rpart_control_minsplit_nan_is_a_known_python_strictness_gap():
    r_msg = r_error_message(lambda: run_r(r_control(minsplit=float("nan"))))
    assert r_msg is None, "R is expected to silently accept minsplit=NaN (propagates through round())"

    with pytest.raises(ValueError, match="NaN"):
        rpart_control(minsplit=float("nan"))


# ---------------------------------------------------------------------------
# 9. KNOWN DIVERGENCE: usesurrogate given as a string that "looks like" a
#    valid integer ("2"). R's `usesurrogate < 0L` / `usesurrogate > 2L`
#    coerce the *numeric* operand to character for the comparison (R's
#    comparison operators between a character and a numeric coerce to
#    character), so "2" < "0" and "2" > "2" are both FALSE -- the guard
#    never fires and R returns usesurrogate="2" completely unvalidated.
#    Python's `usesurrogate < 0` raises TypeError immediately (str/int
#    comparison is not supported), so Python is stricter here too.
# ---------------------------------------------------------------------------

def test_rpart_control_usesurrogate_numeric_looking_string_is_a_known_python_strictness_gap():
    r_msg = r_error_message(lambda: run_r(r_control(usesurrogate="2")))
    assert r_msg is None, "R is expected to silently accept usesurrogate=\"2\" (character-coercing comparison)"

    with pytest.raises(TypeError):
        rpart_control(usesurrogate="2")


# ---------------------------------------------------------------------------
# 10. KNOWN DIVERGENCE: xval given as a non-numeric string ("abc"). R's
#     `any(xval < 0L)` again coerces via character comparison and never
#     raises; Python's `np.asarray(xval) < 0` raises a numpy UFuncTypeError
#     for a string array compared against an int.
# ---------------------------------------------------------------------------

def test_rpart_control_xval_non_numeric_string_is_a_known_python_strictness_gap():
    r_msg = r_error_message(lambda: run_r(r_control(xval="abc")))
    assert r_msg is None, "R is expected to silently accept xval=\"abc\" (character-coercing comparison)"

    with pytest.raises(Exception):
        rpart_control(xval="abc")


# ---------------------------------------------------------------------------
# 11. KNOWN DIVERGENCE: minsplit given as a numeric vector/array, minbucket
#     left unsupplied. R vectorizes `round(minsplit / 3)` elementwise with
#     no error. Python's builtin `round()` does not accept a numpy array
#     (`numpy.ndarray doesn't define __round__`) nor a plain list
#     (`unsupported operand type(s) for /: 'list' and 'int'`), so Python
#     rejects an input R happily vectorizes over.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("as_array", [False, True])
def test_rpart_control_minsplit_vector_without_minbucket_is_a_known_python_gap(as_array):
    minsplit = np.array([10, 20, 30]) if as_array else [10, 20, 30]
    r_msg = r_error_message(lambda: run_r(r_control(minsplit=minsplit)))
    assert r_msg is None, "R is expected to vectorize round(minsplit/3) over a minsplit vector without error"

    with pytest.raises(TypeError):
        rpart_control(minsplit=minsplit)


# ---------------------------------------------------------------------------
# 12. Sanity check that warnings (not exceptions) fire for the
#     out-of-range-but-recoverable parameters, matching R's warning (not
#     error) semantics for maxcompete/xval/usesurrogate/surrogatestyle.
#     rpart_control() must *not* raise for any of these -- only warn and
#     substitute the documented fallback value.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs,expected_key,expected_value",
    [
        ({"maxcompete": -3}, "maxcompete", 0),
        ({"xval": -5}, "xval", 0),
        ({"usesurrogate": 5}, "usesurrogate", 2),
        ({"usesurrogate": -1}, "usesurrogate", 2),
        ({"surrogatestyle": 2}, "surrogatestyle", 0),
        ({"surrogatestyle": -1}, "surrogatestyle", 0),
    ],
)
def test_rpart_control_out_of_range_recoverable_params_warn_not_raise(kwargs, expected_key, expected_value):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_out = rpart_control(**kwargs)
        assert len(caught) == 1
        assert issubclass(caught[0].category, UserWarning)

    assert py_out[expected_key] == expected_value

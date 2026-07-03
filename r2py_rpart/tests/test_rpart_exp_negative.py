"""Negative-path parity tests for r2py_rpart.rpart_exp vs. R's internal
`rpart:::rpart.exp`.

Every `raise`/`stop()` branch in rpart_exp.py is exercised here, paired
with the R call expected to trigger the equivalent `stop()`. Per the
test-suite generation protocol: both sides raising is a PASS even if the
wording differs (a mismatch triggers `warnings.warn` rather than a
failure); only a strict "one side raises, the other doesn't" is a hard
failure -- except for the *documented, intentional* divergences below,
which assert the asymmetry directly instead of forcing (or hiding) a false
equivalence.

See tests/_r_rpart_helpers.py's rpart.exp-specific section for the shared
rpy2 plumbing and a full write-up of the confirmed findings referenced
below.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from r2py_rpart.rpart_exp import rpart_exp

from _r_rpart_helpers import (
    EXP_OMIT,
    assert_python_and_r_errors_agree,
    r_literal,
    r_rpart_exp_error,
    r_surv_assign_2col,
    r_surv_assign_3col,
)


def _py_error(callable_) -> str:
    with pytest.raises(Exception) as exc_info:
        callable_()
    return str(exc_info.value)


# ---------------------------------------------------------------------------
# 1. y is not even array-like (a plain python list) -> both raise ("not a
#    Surv object" in R; python's isinstance(y, np.ndarray) check fails).
# ---------------------------------------------------------------------------

def test_y_plain_list_not_surv():
    n = 5
    wt = np.ones(n)
    py_msg = _py_error(lambda: rpart_exp([1, 2, 3, 4, 5], None, None, wt))

    r_surv_assign_2col("exp_y_tmp", np.array([1, 2, 3, 4, 5.0]), np.array([1, 0, 1, 1, 0.0]))
    # Deliberately reference a bare numeric vector (not the Surv object just
    # built) to mirror "y is not a Surv" on the R side too.
    r_msg = r_rpart_exp_error("c(1,2,3,4,5)", wt, offset="NULL", parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="y plain vector, not Surv")


# ---------------------------------------------------------------------------
# 2. y is a 1-D numpy array -> both raise.
# ---------------------------------------------------------------------------

def test_y_1d_array_not_surv():
    n = 5
    wt = np.ones(n)
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    py_msg = _py_error(lambda: rpart_exp(y, None, None, wt))

    r_msg = r_rpart_exp_error("c(1,2,3,4,5)", wt, offset="NULL", parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="y 1-D array, not Surv")


# ---------------------------------------------------------------------------
# 3. Any first-column (time) value <= 0 -> both raise "Observation time
#    must be > 0".
# ---------------------------------------------------------------------------

def test_time_le_zero_raises():
    time = np.array([-1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, None, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="time <= 0")


def test_time_exactly_zero_raises():
    time = np.array([0.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, None, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="time == 0")


# ---------------------------------------------------------------------------
# 4. All status == 0 (no deaths) -> both raise "No deaths in data set".
# ---------------------------------------------------------------------------

def test_all_status_zero_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.zeros(5)
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, None, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="all status == 0")


# ---------------------------------------------------------------------------
# 5. Unnamed parms (a plain list with no names) -> both raise "You must
#    input a named list for parms".
# ---------------------------------------------------------------------------

def test_parms_unnamed_list_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, [1, 2], wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms="list(1, 2)")
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms unnamed list(1, 2)")


# ---------------------------------------------------------------------------
# 6. parms with an unmatched component name -> both raise "'parms'
#    component not matched: foo".
# ---------------------------------------------------------------------------

def test_parms_unmatched_component_name_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"foo": 1}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"foo": 1}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms unmatched name foo")


# ---------------------------------------------------------------------------
# 7. Invalid/unmatched method string -> both raise "Invalid error method
#    for Poisson".
# ---------------------------------------------------------------------------

def test_parms_invalid_method_string_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"method": "xyz"}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"method": "xyz"}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms invalid method 'xyz'")


def test_parms_ambiguous_empty_method_string_raises():
    """An empty method string matches neither "deviance" nor "sqrt" exactly,
    and (being a prefix of both, and thus ambiguous) matches neither
    uniquely as a partial match either -> pmatch's nomatch=NA path, same as
    any other invalid string."""
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"method": ""}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"method": ""}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms ambiguous method=''")


# ---------------------------------------------------------------------------
# 8. shrink < 0 -> both raise "Invalid shrinkage value".
# ---------------------------------------------------------------------------

def test_parms_shrink_negative_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"shrink": -1}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"shrink": -1}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms shrink=-1")


# ---------------------------------------------------------------------------
# 9. Non-numeric shrink -> both raise "Invalid shrinkage value".
# ---------------------------------------------------------------------------

def test_parms_shrink_non_numeric_raises():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"shrink": "a"}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"shrink": "a"}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms shrink='a'")


# ---------------------------------------------------------------------------
# 10. method given as a bare number rather than a string -- both raise, but
#     for different underlying reasons: R's `pmatch(1, c("deviance",
#     "sqrt"))` coerces 1 to the *character* "1" (matching neither) and
#     hits the documented "Invalid error method for Poisson" `stop()`;
#     python's `str.startswith(1)` raises a bare TypeError instead (the
#     python `_pmatch_scalar`/`_pmatch_vec` helpers assume `x` is always a
#     string, since a genuine string is all rpart.exp.Rd ever documents for
#     `parms$method`). Both raise, so this still passes -- but expect (and
#     tolerate, via the warn-on-mismatch protocol) a very different message.
# ---------------------------------------------------------------------------

def test_parms_method_numeric_raises_for_different_reasons():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])
    py_msg = _py_error(lambda: rpart_exp(y, None, {"method": 1}, wt))

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=r_literal({"method": 1}))
    assert_python_and_r_errors_agree(py_msg, r_msg, context="parms method=1 (numeric)")


# ---------------------------------------------------------------------------
# 11. offset omitted entirely from the call -> both raise, since neither
#     side treats `offset` as optional (R has no `missing(offset)` guard --
#     `length(offset)` forces the promise; python's `offset` parameter has
#     no default either).
# ---------------------------------------------------------------------------

def test_offset_omitted_entirely_errors_on_both_sides():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])

    def _call_missing_offset():
        # Deliberately omit `offset` entirely (a TypeError: missing
        # required positional argument -- python has no equivalent of R's
        # "supplied but unevaluated" promise mechanism, so the failure
        # mode is a plain arity error instead of a lazy-evaluation one).
        return rpart_exp(y, parms=None, wt=wt)  # type: ignore[call-arg]

    py_msg = _py_error(_call_missing_offset)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset=EXP_OMIT, parms=EXP_OMIT)
    assert_python_and_r_errors_agree(py_msg, r_msg, context="offset omitted entirely")


# ---------------------------------------------------------------------------
# 12. DOCUMENTED, INTENTIONAL DIVERGENCE: parms=None (python) vs. an
#     explicit parms=NULL (R). R's `as.list(NULL)` is `list()`, whose
#     `names()` is NULL, so `is.null(names(parms))` is TRUE and R raises
#     "You must input a named list for parms" -- this is a *different*
#     code path from `missing(parms)` (see test_rpart_exp_positive.py's
#     `test_parms_omitted_entirely_matches_python_none_defaults`, which
#     hits the R default branch instead by omitting `parms=` from the call
#     entirely). Python's `rpart_exp(y, offset, None, wt)` has no such
#     "omitted vs. explicitly None" distinction -- `parms=None` always
#     means "use the shrink=1/method=1 defaults" and succeeds. This is a
#     one-sided divergence: R is EXPECTED to raise here, and python is
#     EXPECTED to succeed. Do not "fix" this into an
#     assert_python_and_r_errors_agree() call -- that would incorrectly
#     fail (or mask) a confirmed, permanent calling-convention difference
#     between R's promise-based missing()/NULL distinction and python's
#     None-only optional-argument convention.
# ---------------------------------------------------------------------------

def test_parms_none_python_succeeds_vs_r_explicit_null_errors_known_gap():
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)
    y = np.column_stack([time, status])

    # Python side: parms=None succeeds and resolves to the documented
    # defaults.
    py_out = rpart_exp(y, None, None, wt)
    assert py_out["parms"] == {"shrink": 1, "method": 1}

    # R side: an *explicit* parms=NULL is a genuine error, distinct from
    # omitting parms entirely.
    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms="NULL")
    assert r_msg is not None, (
        "Expected R's rpart.exp(parms=NULL) to raise 'You must input a named "
        "list for parms' -- if this now succeeds, the R-side has changed and "
        "this documented divergence needs to be re-checked."
    )
    assert "named list" in r_msg
    warnings.warn(
        "Confirmed divergence: python's parms=None succeeds (uses defaults) "
        f"while R's explicit parms=NULL raises {r_msg!r} -- see rpart_exp.py's "
        "missing(parms) vs. explicit-NULL handling.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 13. DOCUMENTED, INTENTIONAL DIVERGENCE: python's `isinstance(y, np.ndarray)
#     and y.ndim == 2` check is a simplification of R's `inherits(y,
#     "Surv")` -- any 2-D array (regardless of whether its columns actually
#     encode a survival time/status pair) passes python's check, while R
#     immediately rejects a plain (non-Surv-classed) 2-column matrix.
# ---------------------------------------------------------------------------

def test_arbitrary_2d_array_passes_python_check_but_r_requires_real_surv_known_gap():
    # Two columns of unrelated, arbitrary data -- column 0 all > 0 (so it
    # slips past the "Observation time must be > 0" guard) and column 1
    # contains at least one exact 1.0 (so it slips past both the "No
    # deaths in data set" guard *and* the `time[status == 1]` subsetting
    # -- see test_arbitrary_2d_array_with_no_exact_status_one_crashes_known_bug
    # below for what happens when column 1 has no exact 1.0 at all), but
    # this is NOT a Surv object and bears no survival-analysis meaning.
    arbitrary = np.array([[1.0, 1.0], [2.0, 3.0], [3.0, 9.0], [4.0, 2.0]])
    wt = np.ones(4)

    py_out = rpart_exp(arbitrary, None, None, wt)
    assert py_out["y"].shape == (4, 2)  # python happily "succeeds"

    r_msg = r_rpart_exp_error("matrix(c(1,2,3,4,1,3,9,2), ncol=2)", wt, offset="NULL", parms=EXP_OMIT)
    assert r_msg is not None, (
        "Expected R's rpart.exp() to reject a plain (non-Surv) matrix via "
        "inherits(y, 'Surv') -- if this now succeeds, re-check this "
        "documented gap."
    )
    assert "survival" in r_msg.lower() or "Surv" in r_msg
    warnings.warn(
        "Confirmed divergence: python's rpart_exp() accepts ANY 2-D ndarray "
        "(only checking isinstance/ndim, with no way to check for an R S3 "
        f"class marker), while R rejects a non-Surv-classed matrix: {r_msg!r}",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 13b. A SECOND, COMPOUNDING bug uncovered while building the test above:
#      if the (already-non-Surv, per 13 above) array's last column has NO
#      value exactly equal to 1.0 -- e.g. arbitrary non-binary "status"
#      values like 7/3/9/2 -- `np.all(status == 0)` is still False (so the
#      "No deaths in data set" guard is passed), but
#      `time[status == 1]` is then an EMPTY array, and the very next line,
#      `dtimes[keep]` (`keep = np.concatenate([[True], np.diff(dtimes) >
#      eps])`, always at least length 1), raises an unrelated
#      `IndexError: boolean index did not match indexed array` instead of
#      any of rpart_exp's own documented `ValueError`s. This is a genuine
#      robustness bug (not merely the documented isinstance-only
#      simplification from test 13): even restricting to legitimate 2-D
#      float arrays, rpart_exp() does not handle a "some deaths per the
#      all-zero check, but zero deaths per the status==1 subsetting" input
#      gracefully. R rejects the same (non-Surv) input immediately via its
#      inherits() check, before ever reaching an analogous code path, so
#      this specific IndexError has no direct R analogue to compare
#      against -- both sides still raise, so this remains a pass under the
#      "both must raise" protocol, but the mismatch is large enough to be
#      worth flagging explicitly rather than glossing over.
# ---------------------------------------------------------------------------

def test_arbitrary_2d_array_with_no_exact_status_one_crashes_known_bug():
    arbitrary = np.array([[1.0, 7.0], [2.0, 3.0], [3.0, 9.0], [4.0, 2.0]])
    wt = np.ones(4)

    with pytest.raises(IndexError):
        rpart_exp(arbitrary, None, None, wt)

    r_msg = r_rpart_exp_error("matrix(c(1,2,3,4,7,3,9,2), ncol=2)", wt, offset="NULL", parms=EXP_OMIT)
    assert r_msg is not None
    warnings.warn(
        "Confirmed robustness bug: when a (malformed, non-Surv) 2-D array's "
        "status column has no value exactly equal to 1.0 despite not being "
        "all-zero, rpart_exp() crashes with an unrelated, undocumented "
        "IndexError ('boolean index did not match indexed array') from its "
        "dtimes-dedup step instead of a clear ValueError, because "
        "time[status == 1] silently comes out empty. R rejects the "
        f"equivalent (non-Surv) input earlier and for a different reason: {r_msg!r}.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 14. MAJOR CONFIRMED R-SIDE BUG: the 3-column ("counting process")
#     Surv(start, stop, status) branch of drate2's `ny == 3L` code calls
#     `table(index2, levels = 1:ngrp)`. `table()` has no `levels=` formal,
#     so this is matched by `...` and treated as a SECOND classifying
#     vector requiring `length(index2) == length(1:ngrp)`, i.e. n == ngrp.
#     For any realistic counting-process data (here: ordinary censoring, so
#     ngrp < n), R's rpart.exp raises "all arguments must have the same
#     length" -- confirmed empirically, independent of any of this test
#     suite's own code. Python's `drate2` instead uses
#     `np.bincount(index2, minlength=ngrp)`, which handles n != ngrp fine,
#     so python SUCCEEDS where R fails. This is the primary reason a
#     genuine positive (matching-output) parity test cannot be written for
#     the general 3-column case -- see test_rpart_exp_edge.py's
#     `test_counting_process_all_unique_deaths_ny3_values_diverge_known_bug`
#     for the (narrower, still-diverging) case where R does not even raise.
# ---------------------------------------------------------------------------

def test_counting_process_ny3_realistic_data_r_table_bug_errors():
    rng = np.random.default_rng(20)
    n = 12
    start = np.round(rng.uniform(0.1, 3.0, n), 2)
    stop = start + np.round(rng.uniform(0.5, 8.0, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)  # ordinary censoring -> ngrp < n

    y3 = np.column_stack([start, stop, status])
    wt = np.ones(n)
    py_out = rpart_exp(y3, None, None, wt)
    assert py_out["y"].shape == (n, 2)  # python succeeds

    r_surv_assign_3col("exp_y3_tmp", start, stop, status)
    r_msg = r_rpart_exp_error("exp_y3_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert r_msg is not None, (
        "Expected R's rpart.exp() to raise 'all arguments must have the "
        "same length' for a realistic (n != ngrp) counting-process input "
        "via the table(index2, levels=1:ngrp) bug -- if this now succeeds, "
        "the R-side implementation has changed and this documented bug "
        "needs to be re-verified."
    )
    warnings.warn(
        "Confirmed R-side bug in rpart.exp's ny==3 (counting process) "
        "branch: table(index2, levels=1:ngrp) requires length(index2) == "
        f"ngrp (i.e. n == ngrp), so R raises {r_msg!r} for ordinary "
        "censored counting-process data, while python's bincount-based "
        "drate2 succeeds.",
        UserWarning,
        stacklevel=2,
    )

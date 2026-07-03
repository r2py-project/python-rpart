"""Boundary/edge-case parity tests for r2py_rpart.rpart_exp (and its private
helper drate2) vs. R's internal `rpart:::rpart.exp`.

Covers minimum-n, all-ties, sub-machine-epsilon-tie deduplication, the
>1000-unique-death-times quantile-downsampling path, an ignored
wrong-length offset, shrink boundary/extreme values, a single interval, and
NaN/Inf observation times. Two dedicated tests also lock in confirmed
NaN/Inf-handling and 3-column ("counting process") divergences discovered
while writing this suite (see inline comments and
tests/_r_rpart_helpers.py's rpart.exp-specific module docstring for the
full write-up).

`drate2` is a private helper (not itself exported by the R package -- it is
defined as a *nested* function inside R's rpart.exp, so there is no
`rpart:::drate2` to call standalone). It is exercised indirectly through
every `rpart_exp` call above and below, and directly here via a couple of
hand-verified-by-arithmetic unit tests (no R comparison possible for a
function R itself never exposes on its own).
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.rpart_exp import drate2, rpart_exp

from _r_rpart_helpers import (
    EXP_OMIT,
    r_literal,
    r_rpart_exp,
    r_rpart_exp_error,
    r_rpart_exp_result_to_python,
    r_surv_assign_2col,
    r_surv_assign_3col,
)


# ---------------------------------------------------------------------------
# 1. Minimal dataset: n=2, exactly one death.
# ---------------------------------------------------------------------------

def test_minimal_n2_one_death():
    time = np.array([3.0, 7.0])
    status = np.array([1.0, 0.0])
    wt = np.ones(2)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, None, wt)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 2. All observations die at the exact same time -> a single interval.
# ---------------------------------------------------------------------------

def test_all_observations_die_at_same_time():
    time = np.full(6, 5.0)
    status = np.ones(6)
    wt = np.ones(6)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, None, wt)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)
    # every rescaled rate is exactly 1.0 (a single interval spanning the
    # entire follow-up, one death rate covering everybody)
    assert_allclose(py_out["y"][:, 0], np.ones(6))


# ---------------------------------------------------------------------------
# 3. Two death times differing by exactly R's/numpy's machine epsilon (the
#    smallest possible difference between two distinct float64 values near
#    magnitude 1) -- these must be amalgamated into a single interval by
#    the `diff(dtimes) > eps` dedup step (note the strict `>`: a
#    difference of *exactly* eps is deduplicated, not kept).
# ---------------------------------------------------------------------------

def test_death_times_differing_by_machine_epsilon_are_deduped():
    t1 = 1.0
    t2 = np.nextafter(1.0, 2.0)  # differs from t1 by exactly np.finfo(float).eps
    assert (t2 - t1) == np.finfo(float).eps
    time = np.array([t1, t2, 2.0, 3.0, 4.0])
    status = np.ones(5)
    wt = np.ones(5)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, None, wt)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)
    # t1 and t2 are deduped away as separate *interval boundaries* (dtimes
    # collapses them into one), so they share the same interpolation
    # bucket -- but `time` itself still holds the two distinct (if
    # eps-close) raw values, so their interpolated `newy` values are only
    # equal to within a tolerance proportional to eps, not bit-for-bit
    # identical.
    assert_allclose(py_out["y"][0, 0], py_out["y"][1, 0], atol=1e-12)


# ---------------------------------------------------------------------------
# 4. > 1000 unique death times triggers the quantile-downsampling path
#    (`dtimes <- quantile(dtimes, 0:1000/1000)` in R / `np.quantile(dtimes,
#    np.arange(0, 1001) / 1000)` in python) -- both default to a
#    linear-interpolation quantile estimator (R's type 7 == numpy's default
#    "linear" method), so the resulting rescaled `y` should still match.
# ---------------------------------------------------------------------------

def test_more_than_1000_unique_death_times_triggers_quantile_downsampling():
    rng = np.random.default_rng(42)
    n = 1500
    time = np.unique(np.round(rng.uniform(0.5, 100, n), 6))
    assert len(time) > 1000
    status = np.ones(len(time))
    wt = rng.uniform(0.5, 3.0, len(time))  # non-uniform wt: confirmed no-op

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    assert_allclose(py_out["y"], r_out["y"], rtol=1e-6)


# ---------------------------------------------------------------------------
# 5. offset of length != n is silently ignored on both sides (R:
#    `length(offset) == n`; python: `len(offset) == n`).
# ---------------------------------------------------------------------------

def test_offset_wrong_length_is_ignored():
    rng = np.random.default_rng(13)
    n = 20
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)
    y = np.column_stack([time, status])

    wrong_length_offset = np.array([0.5, -0.3, 0.1])  # length 3 != n=20

    py_out_with_offset = rpart_exp(y, wrong_length_offset, None, wt)
    py_out_no_offset = rpart_exp(y, None, None, wt)
    assert_allclose(py_out_with_offset["y"], py_out_no_offset["y"])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp(
        "exp_y_tmp", wt, offset=r_literal(wrong_length_offset), parms=EXP_OMIT
    )
    r_out = r_rpart_exp_result_to_python(r_result)
    assert_allclose(py_out_with_offset["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 6. shrink == 0 exactly (the boundary of the `shrink < 0` check -- 0 is
#    valid, not an error) and a very large shrink value.
# ---------------------------------------------------------------------------

def test_shrink_zero_boundary():
    rng = np.random.default_rng(14)
    n = 18
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"shrink": 0})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, {"shrink": 0}, wt)
    assert py_out["parms"]["shrink"] == 0
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


def test_shrink_very_large():
    rng = np.random.default_rng(15)
    n = 18
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"shrink": 1.0e6})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, {"shrink": 1.0e6}, wt)
    assert py_out["parms"]["shrink"] == 1.0e6
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)
    # y itself does not depend on shrink at all (shrink only feeds into the
    # later splitting criterion, not rpart.exp's own rescaling) -- sanity
    # check it matches the shrink=0 result's y too.
    py_out_shrink0 = rpart_exp(y, None, {"shrink": 0}, wt)
    assert_allclose(py_out["y"], py_out_shrink0["y"])


# ---------------------------------------------------------------------------
# 7. A single unique death time, but with several censored observations at
#    other times (still one interval boundary overall, i.e.
#    `itable = c(0, max(time))`, but exercising `drate2` with n > (number
#    of deaths) unlike test 2 above, where every observation was a death).
# ---------------------------------------------------------------------------

def test_single_death_time_with_censored_observations_at_other_times():
    time = np.array([4.0, 1.0, 9.0, 4.0, 12.0])
    status = np.array([0.0, 0.0, 1.0, 0.0, 0.0])  # only one death, at t=9
    wt = np.ones(5)
    y = np.column_stack([time, status])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    py_out = rpart_exp(y, None, None, wt)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 8. NaN observation time: CONFIRMED DIVERGENCE. R's `any(y[, 1L] <= 0)`
#    involves `NA <= 0`, which is `NA`; `if (NA)` itself raises "missing
#    value where TRUE/FALSE needed" in R. numpy's `nan <= 0` is plain
#    `False`, so `np.any(...)` silently evaluates to `False` and the `NaN`
#    sails through into np.unique/np.sort/np.interp untouched, producing a
#    NaN-contaminated (but non-raising) result instead of an error.
# ---------------------------------------------------------------------------

def test_nan_time_r_raises_python_silently_propagates_known_gap():
    time = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    wt = np.ones(6)
    y = np.column_stack([time, status])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        py_out = rpart_exp(y, None, None, wt)  # does NOT raise
    assert np.isnan(py_out["y"][2, 0])  # NaN silently propagated into row 2

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert r_msg is not None, (
        "Expected R to raise 'missing value where TRUE/FALSE needed' for a "
        "NaN observation time -- if this now succeeds, re-verify this "
        "documented gap."
    )
    assert "missing value" in r_msg
    warnings.warn(
        "Confirmed divergence: a NaN observation time makes R's "
        f"any(y[,1]<=0)-guarded if() raise {r_msg!r} outright, while "
        "python's np.any(...) silently evaluates the NaN comparison to "
        "False and lets the NaN propagate into the result instead of "
        "raising.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 9. Inf observation time: CONFIRMED DIVERGENCE. `max(time)` becomes Inf,
#    contaminating `itable`/`cumhaz` with Inf/NaN; R's `approx()` then
#    explicitly raises "need at least two non-NA values to interpolate".
#    `np.interp` has no such guard and silently returns a NaN-contaminated
#    (but non-raising) result instead (with a RuntimeWarning from the
#    upstream `rate * diff(itable)` multiplication).
# ---------------------------------------------------------------------------

def test_inf_time_r_raises_python_silently_propagates_known_gap():
    time = np.array([1.0, 2.0, np.inf, 4.0, 5.0, 6.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0, 1.0])
    wt = np.ones(6)
    y = np.column_stack([time, status])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        py_out = rpart_exp(y, None, None, wt)  # does NOT raise
    assert py_out["y"].shape == (6, 2)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_msg = r_rpart_exp_error("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    assert r_msg is not None, (
        "Expected R's approx() to raise 'need at least two non-NA values "
        "to interpolate' for an Inf observation time -- if this now "
        "succeeds, re-verify this documented gap."
    )
    assert "interpolate" in r_msg
    warnings.warn(
        "Confirmed divergence: an Inf observation time makes max(time) "
        "Inf, contaminating itable/cumhaz and making R's approx() raise "
        f"{r_msg!r}, while python's np.interp silently returns a "
        "NaN-contaminated (non-raising) result instead.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 10. 3-column ("counting process") Surv(start, stop, status), restricted
#     to the narrow n == ngrp case (every observation an uncensored,
#     uniquely-timed death) where R's table(index2, levels=1:ngrp) bug
#     (see _r_rpart_helpers.py's module docstring) does not outright crash.
#     Even here, the bug still corrupts the *rescaled rate* column (column
#     0): R computes a 2-D cross-tabulation where a length-ngrp vector was
#     intended, giving numerically wrong pyears/rate. Column 1 (the raw
#     `stop` time, per R's literal `cbind(newy, y[, 2L])` -- NOT the status
#     column, for a 3-column y, another literal-replication quirk worth
#     locking in) is untouched by any of this and matches exactly.
# ---------------------------------------------------------------------------

def test_counting_process_all_unique_deaths_ny3_values_diverge_known_bug():
    rng = np.random.default_rng(21)
    n = 8
    start = np.round(rng.uniform(0.1, 2.0, n), 2)
    stop = start + np.round(rng.uniform(1.0, 5.0, n), 2)
    status = np.ones(n)  # every observation is an uncensored, unique death

    y3 = np.column_stack([start, stop, status])
    wt = np.ones(n)
    py_out = rpart_exp(y3, None, None, wt)

    r_surv_assign_3col("exp_y3_tmp", start, stop, status)
    r_result = r_rpart_exp("exp_y3_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    # Column 1 (`y[:, 1]`, the raw `stop` time) is a straight, unmodified
    # copy on both sides -- untouched by the buggy rate computation --
    # confirming the "cbind(newy, y[,2L]) is column 2 regardless of ny"
    # literal-replication quirk documented in the task instructions.
    assert_allclose(py_out["y"][:, 1], stop, rtol=1e-10)
    assert_allclose(r_out["y"][:, 1], stop, rtol=1e-10)
    assert_allclose(py_out["y"][:, 1], r_out["y"][:, 1], rtol=1e-10)

    # Column 0 (the rescaled hazard-based `newy`) is NOT expected to match:
    # lock in the divergence rather than silently allowing (or hiding) it.
    assert not np.allclose(py_out["y"][:, 0], r_out["y"][:, 0]), (
        "Expected R's table(index2, levels=1:ngrp) cross-tabulation bug to "
        "produce a different rescaled rate column than python's "
        "bincount-based drate2 -- if these now match, R's implementation "
        "has likely been fixed and this test (and its surrounding "
        "documentation) needs to be revisited."
    )
    warnings.warn(
        "Confirmed: even in the narrow n==ngrp case where R's rpart.exp "
        "does not outright crash on ny==3 data, its rescaled rate column "
        "(y[:,0]) numerically diverges from python's due to the "
        "table(index2, levels=1:ngrp) cross-tabulation bug documented in "
        "_r_rpart_helpers.py.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 11. 3-column start==stop boundary: python-only correctness check via a
#     direct drate2 call (R's general ny==3 path is not reliable enough --
#     see above -- to serve as a trustworthy oracle here). Hand-verified by
#     the exact same arithmetic drate2.py itself performs.
# ---------------------------------------------------------------------------

def test_drate2_ny3_start_equals_stop_boundary_hand_verified():
    # obs 0: start==stop==1.0 (a zero-width interval of at-risk time before
    # the interval-boundary itself, itime2 should come out to 0 there)
    start = np.array([1.0, 0.5, 2.5])
    stop = np.array([1.0, 3.0, 4.0])
    status = np.array([1.0, 1.0, 0.0])
    y = np.column_stack([start, stop, status])
    wt = np.ones(3)
    itable = np.array([0.0, 2.0, 5.0])

    rate = drate2(3, 3, y, wt, itable)

    # Hand-derivation (see task write-up): index (by stop) = [0, 1, 1];
    # itime = stop - itable[index] = [1, 1, 2]; tab1 = [1, 2];
    # temp = cumsum(reverse([1,2]))reversed = [3, 2];
    # pyears_end = ilength*append(temp[1:],0) + itime-group-sums
    #            = [2,3]*[2,0] + [1, 3] = [4+1, 0+3] = [5, 3]
    # index2 (by start) = [0, 0, 1]; itime2 = start - itable[index2]
    #            = [1.0-0, 0.5-0, 2.5-2] = [1.0, 0.5, 0.5]
    # tab2 = [2, 1]; temp2 = cumsum(reverse([2,1]))reversed = [3, 1];
    # py2 = ilength*concat([0],temp2[:-1]) + itime2-group-sums
    #     = [2,3]*[0,3] + [1.5, 0.5] = [0+1.5, 9+0.5] = [1.5, 9.5]
    # pyears = pyears_end - py2 = [5-1.5, 3-9.5] = [3.5, -6.5]
    # deaths (status sum per index-by-stop group) = [1, 1]
    # rate = deaths/pyears = [1/3.5, 1/-6.5]
    expected = np.array([1 / 3.5, 1 / -6.5])
    assert_allclose(rate, expected, rtol=1e-10)


def test_drate2_ny2_hand_verified_two_interval_reference():
    """A from-scratch hand computation of drate2's 2-column branch (no R
    counterpart -- drate2 is a private nested function, unreachable via
    `rpart:::`), used as a fixed regression anchor for the person-years/
    hazard-rate arithmetic independent of any particular rpart_exp() call."""
    time = np.array([1.0, 3.0, 4.0, 1.5])
    status = np.array([1.0, 0.0, 1.0, 1.0])
    y = np.column_stack([time, status])
    wt = np.ones(4)
    itable = np.array([0.0, 2.0, 5.0])

    rate = drate2(4, 2, y, wt, itable)
    # index = [0, 1, 1, 0]; itime = [1, 1, 2, 1.5]; tab1 = [2, 2];
    # temp = [4, 2]; pyears = [2,3]*[2,0] + [2.5, 3] = [4+2.5, 0+3] = [6.5, 3]
    # deaths = [2, 1]; rate = [2/6.5, 1/3]
    expected = np.array([2 / 6.5, 1 / 3])
    assert_allclose(rate, expected, rtol=1e-10)


# ---------------------------------------------------------------------------
# 12. Empty offset array (length 0, distinct from offset=None) is also
#     ignored (length(offset) == n is False for n > 0), matching R's
#     length(NULL) == 0 no-rescaling path -- confirms offset=np.array([])
#     and offset=None are handled identically, not just offset=None.
# ---------------------------------------------------------------------------

def test_empty_offset_array_ignored_same_as_none():
    rng = np.random.default_rng(16)
    n = 10
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)
    y = np.column_stack([time, status])

    py_out_empty = rpart_exp(y, np.array([]), None, wt)
    py_out_none = rpart_exp(y, None, None, wt)
    assert_allclose(py_out_empty["y"], py_out_none["y"])

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)
    assert_allclose(py_out_none["y"], r_out["y"], rtol=1e-8)

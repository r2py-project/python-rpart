"""Positive-path parity tests for r2py_rpart.rpart_exp vs. R's internal
`rpart:::rpart.exp` -- the initialization routine for `method="exp"`
(rescaled-exponential/Poisson) survival splitting.

Each test builds an identical `Surv(...)` response (plus offset/parms/wt
combination) in both R (via rpy2) and python, then asserts that the
returned `y` (the rescaled response, column-bound with the *second* column
of the original input per R's literal `cbind(newy, y[, 2L])`), `parms`,
`numresp`, `numy`, and the `summary`/`text` closures all agree.

Two structural findings, confirmed empirically before any test here was
written, are worth calling out up front (see _r_rpart_helpers.py's
module-level docstring on its rpart.exp-specific section for the full
writeup):

  1. `wt` is accepted as a parameter by both `rpart.exp`/`rpart_exp` and the
     nested/private `drate2`, but is never actually read anywhere in either
     implementation's body -- a faithfully-ported dead parameter (not a
     translation bug). `test_wt_is_a_faithfully_ported_no_op` locks this in
     on both sides at once.

  2. R's own `text(..., use.n=FALSE)` closure returns a `paste(x)`-vectorized
     character vector (one string per row of `yval`), not a single joined
     string -- `test_text_closure_use_n_false_single_row_matches` below
     stays in the single-row regime where this does not yet bite (see
     test_rpart_exp_edge.py's dedicated multi-row divergence test for where
     it does).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.rpart_exp import rpart_exp

from _r_rpart_helpers import (
    EXP_OMIT,
    call_r_rpart_exp_summary,
    call_r_rpart_exp_text,
    r_literal,
    r_rpart_exp,
    r_rpart_exp_result_to_python,
    r_surv_assign_2col,
    stagec_df,
)


def _assert_parms_match(py_parms: dict, r_parms: dict) -> None:
    assert set(py_parms.keys()) == set(r_parms.keys())
    for k in py_parms:
        assert_allclose(float(py_parms[k]), float(r_parms[k]), rtol=1e-10)


# ---------------------------------------------------------------------------
# 1. 2-column Surv(pgtime, pgstat) from rpart's own stagec dataset, parms
#    omitted entirely (R's missing(parms) branch) vs python's parms=None.
# ---------------------------------------------------------------------------

def test_stagec_2col_parms_omitted_matches_r_defaults():
    df = stagec_df()
    time = df["pgtime"].to_numpy(dtype=float)
    status = df["pgstat"].to_numpy(dtype=float)
    n = len(time)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    assert py_out["numresp"] == r_out["numresp"] == 2
    assert py_out["numy"] == r_out["numy"] == 2
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 2. Synthetic 2-column data, explicit parms with only `method="deviance"`.
# ---------------------------------------------------------------------------

def test_synthetic_2col_method_deviance_explicit():
    rng = np.random.default_rng(1)
    n = 40
    time = np.round(rng.uniform(1, 40, n), 2)
    status = rng.binomial(1, 0.55, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"method": "deviance"})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"method": "deviance"}, wt)

    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert py_out["parms"]["method"] == 1
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 3. Synthetic 2-column data, explicit parms with only `method="sqrt"`
#    (default shrink resolves to 2 - method = 0 for this method).
# ---------------------------------------------------------------------------

def test_synthetic_2col_method_sqrt_default_shrink():
    rng = np.random.default_rng(2)
    n = 35
    time = np.round(rng.uniform(0.5, 25, n), 3)
    status = rng.binomial(1, 0.6, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"method": "sqrt"})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"method": "sqrt"}, wt)

    assert py_out["parms"]["method"] == 2
    assert py_out["parms"]["shrink"] == 0
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 4. parms with both method and shrink given explicitly, plus a partial
#    (pmatch) method string, "dev" -> "deviance".
# ---------------------------------------------------------------------------

def test_partial_pmatch_method_dev_and_explicit_shrink():
    rng = np.random.default_rng(3)
    n = 25
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = 'list(method="dev", shrink=0.5)'
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"method": "dev", "shrink": 0.5}, wt)

    assert py_out["parms"]["method"] == 1
    assert py_out["parms"]["shrink"] == 0.5
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 5. Partial (pmatch) method string "s" -> "sqrt" (the only method starting
#    with "s"), with an explicit shrink override.
# ---------------------------------------------------------------------------

def test_partial_pmatch_method_s_matches_sqrt():
    rng = np.random.default_rng(4)
    n = 20
    time = np.round(rng.uniform(1, 10, n), 2)
    status = rng.binomial(1, 0.7, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = "list(method=\"s\", shrink=2)"
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"method": "s", "shrink": 2}, wt)

    assert py_out["parms"]["method"] == 2
    assert py_out["parms"]["shrink"] == 2
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 6. offset with length == n rescales `y` by exp(offset).
# ---------------------------------------------------------------------------

def test_offset_length_n_rescales_y():
    rng = np.random.default_rng(5)
    n = 28
    time = np.round(rng.uniform(1, 30, n), 2)
    status = rng.binomial(1, 0.6, n).astype(float)
    offset = rng.uniform(-1, 1, n)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset=r_literal(offset), parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, offset, None, wt)

    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)
    # sanity: the rescaling actually did something (vs. offset=None)
    py_out_no_offset = rpart_exp(y, None, None, wt)
    assert not np.allclose(py_out["y"][:, 0], py_out_no_offset["y"][:, 0])


# ---------------------------------------------------------------------------
# 7. parms omitted entirely (R's missing(parms) branch) vs. python's
#    parms=None -- both resolve to shrink=1, method=1.
# ---------------------------------------------------------------------------

def test_parms_omitted_entirely_matches_python_none_defaults():
    rng = np.random.default_rng(6)
    n = 18
    time = np.round(rng.uniform(1, 12, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    assert py_out["parms"] == {"shrink": 1, "method": 1}
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 8. wt is a faithfully-ported no-op: varying wt (all-ones vs. a
#    non-uniform case-weight vector) changes nothing on either side.
# ---------------------------------------------------------------------------

def test_wt_is_a_faithfully_ported_no_op():
    rng = np.random.default_rng(7)
    n = 22
    time = np.round(rng.uniform(1, 20, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt_ones = np.ones(n)
    wt_varied = rng.uniform(0.2, 5.0, n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result_ones = r_rpart_exp("exp_y_tmp", wt_ones, offset="NULL", parms=EXP_OMIT)
    r_result_varied = r_rpart_exp("exp_y_tmp", wt_varied, offset="NULL", parms=EXP_OMIT)
    r_out_ones = r_rpart_exp_result_to_python(r_result_ones)
    r_out_varied = r_rpart_exp_result_to_python(r_result_varied)

    y = np.column_stack([time, status])
    py_out_ones = rpart_exp(y, None, None, wt_ones)
    py_out_varied = rpart_exp(y, None, None, wt_varied)

    # R-side wt-invariance
    assert_allclose(r_out_ones["y"], r_out_varied["y"], rtol=1e-8)
    # python-side wt-invariance
    assert_allclose(py_out_ones["y"], py_out_varied["y"], rtol=1e-8)
    # cross-check against R for good measure
    assert_allclose(py_out_varied["y"], r_out_varied["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 9. stagec_df again, but with both parms components given explicitly and
#    a non-uniform wt, exercising several combinations at once.
# ---------------------------------------------------------------------------

def test_stagec_2col_explicit_parms_and_nonuniform_wt():
    df = stagec_df()
    time = df["pgtime"].to_numpy(dtype=float)
    status = df["pgstat"].to_numpy(dtype=float)
    n = len(time)
    rng = np.random.default_rng(8)
    wt = rng.uniform(0.5, 2.0, n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"shrink": 3, "method": "sqrt"})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"shrink": 3, "method": "sqrt"}, wt)

    assert py_out["parms"]["shrink"] == 3
    assert py_out["parms"]["method"] == 2
    _assert_parms_match(py_out["parms"], r_out["parms"])
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 10. Small dataset size sanity check (n well below the >1000 quantile
#     downsampling threshold, but bigger than the minimal-n edge case).
# ---------------------------------------------------------------------------

def test_small_dataset_n5():
    time = np.array([2.0, 4.0, 4.0, 6.0, 10.0])
    status = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
    wt = np.ones(5)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)


# ---------------------------------------------------------------------------
# 11. summary(yval, dev, wt, ylevel, digits) closure output matches R's.
# ---------------------------------------------------------------------------

def test_summary_closure_matches_r():
    rng = np.random.default_rng(9)
    n = 12
    time = np.round(rng.uniform(1, 20, n), 1)
    status = rng.binomial(1, 0.6, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    yval = np.array([[1.2, 5.0], [0.8, 3.0], [1.5, 7.0]])
    dev = np.array([0.5, 0.3, 0.9])
    wt_sample = np.array([10.0, 8.0, 12.0])

    py_summary = list(py_out["summary"](yval, dev, wt_sample, None, 4))
    r_summary = call_r_rpart_exp_summary(r_result, yval, dev, wt_sample, 4)

    assert py_summary == r_summary


# ---------------------------------------------------------------------------
# 12. text(yval, dev, wt, ylevel, digits, n, use.n=True) closure output
#     matches R's (the `use.n=True` branch always agrees regardless of row
#     count -- see module docstring for the `use.n=False` multi-row caveat).
# ---------------------------------------------------------------------------

def test_text_closure_use_n_true_matches_r():
    rng = np.random.default_rng(10)
    n = 14
    time = np.round(rng.uniform(1, 20, n), 1)
    status = rng.binomial(1, 0.6, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    yval = np.array([[1.2, 5.0], [0.8, 3.0], [1.5, 7.0]])
    dev = np.array([0.5, 0.3, 0.9])
    wt_sample = np.array([10.0, 8.0, 12.0])
    n_sample = np.array([20, 15, 25])

    py_text = list(py_out["text"](yval, dev, wt_sample, None, 4, n_sample, True))
    r_text = call_r_rpart_exp_text(r_result, yval, dev, wt_sample, 4, n_sample, True)

    assert py_text == r_text


# ---------------------------------------------------------------------------
# 13. text(..., use.n=False) with a SINGLE row: R's non-collapsing paste()
#     and python's " ".join() produce the same single-element output (the
#     divergence documented above/in test_rpart_exp_edge.py only shows up
#     for more than one row).
# ---------------------------------------------------------------------------

def test_text_closure_use_n_false_single_row_matches():
    rng = np.random.default_rng(11)
    n = 10
    time = np.round(rng.uniform(1, 20, n), 1)
    status = rng.binomial(1, 0.6, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=EXP_OMIT)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, None, wt)

    yval = np.array([[1.2, 5.0]])
    dev = np.array([0.5])
    wt_sample = np.array([10.0])
    n_sample = np.array([20])

    py_text = py_out["text"](yval, dev, wt_sample, None, 4, n_sample, False)
    r_text = call_r_rpart_exp_text(r_result, yval, dev, wt_sample, 4, n_sample, False)

    assert py_text == r_text[0]


# ---------------------------------------------------------------------------
# 14. numresp/numy are always the fixed constants 2/2, regardless of parms.
# ---------------------------------------------------------------------------

def test_numresp_numy_always_two():
    rng = np.random.default_rng(12)
    n = 16
    time = np.round(rng.uniform(1, 15, n), 2)
    status = rng.binomial(1, 0.5, n).astype(float)
    wt = np.ones(n)

    r_surv_assign_2col("exp_y_tmp", time, status)
    parms_r = r_literal({"method": "sqrt", "shrink": 5})
    r_result = r_rpart_exp("exp_y_tmp", wt, offset="NULL", parms=parms_r)
    r_out = r_rpart_exp_result_to_python(r_result)

    y = np.column_stack([time, status])
    py_out = rpart_exp(y, None, {"method": "sqrt", "shrink": 5}, wt)

    assert py_out["numresp"] == 2
    assert py_out["numy"] == 2
    assert r_out["numresp"] == 2
    assert r_out["numy"] == 2

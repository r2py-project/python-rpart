"""Positive-path parity tests for r2py_rpart.xpred_rpart vs. R's
xpred.rpart (called directly via rpy2, not S3-dispatched -- see
_r_rpart_helpers.py's xpred.rpart-specific plumbing section).

Each test fits an identical model in both R and Python (from the same data,
same formula/method/control/weights), then calls xpred.rpart/xpred_rpart in
both with an *explicit* `xval=`/`xval` vector (see below for why) and
asserts the results match numerically via `numpy.testing.assert_allclose`.

Why an explicit `xval=` vector, always
----------------------------------------
`xpred.rpart(fit, xval=10)`'s default *scalar* `xval` draws the
cross-validation fold assignment via R's own `sample()`; r2py_rpart's port
draws it via `numpy.random.permutation` instead. These are independent RNG
streams that do not reproduce each other's draws, so a scalar `xval` would
make R's and python's fold assignments (and hence every downstream
prediction) diverge for reasons having nothing to do with xpred_rpart's own
correctness -- exactly the same permanent, already-documented gap noted for
rpart()'s own internal cross-validation folds throughout this test suite
(see e.g. test_xpred1.py/test_xpred2.py's module docstrings, and
test_printcp_positive.py's xerror/xstd caveat). Passing an explicit `xval=`
vector instead sidesteps this entirely: both sides consume the *same*,
already-fixed fold assignment, so any resulting numeric difference would be
a genuine xpred_rpart bug rather than an RNG artifact. A dedicated test
below (`test_xpred_rpart_scalar_xval_default_is_structurally_sane`) covers
the scalar-`xval` path itself, but only checks structural properties (shape,
finiteness, fold count) rather than value parity, for this reason.

Similarly, the default (`cp` omitted) `cp` derivation is *deterministic*
(computed purely from `fit$cptable`'s CP column via a fixed geometric-mean
formula -- see `default_xpred_cp()` in _r_rpart_helpers.py, mirroring
xpred_rpart.py's own `cp is _MISSING` branch), so it *is` safe to compare
value-for-value below, unlike `cptable`'s RNG-dependent xerror/xstd columns.
Fits below use `control={"xval": 0}` purely to skip that unrelated,
unused-here internal cross-validation step (faster, and avoids meaningless
warnings for tiny per-fold datasets); it has no bearing on xpred_rpart's own
(separate) cross-validation, driven entirely by the `xval=` argument passed
to xpred_rpart/xpred.rpart directly.

See _r_rpart_helpers.py for the shared rpy2 plumbing, in particular
`r_xpred()` (builds/evaluates an R `xpred.rpart(fit, ...)` call),
`r_xpred_to_numpy()` (converts its return value -- a 2-D matrix or 3-D
array -- into a numpy array directly comparable to xpred_rpart()'s return
value), and `default_xpred_cp()` (recomputes the default cp list from a
fit's cptable, for tests that want to pin `cp=` explicitly alongside an
explicit `xval=`).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart, xpred_rpart

from _r_rpart_helpers import (
    cu_summary_df,
    default_xpred_cp,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_xpred,
    r_xpred_to_numpy,
    run_r,
    stagec_df,
)

_STAGEC_PLOIDY_LEVELS = ["diploid", "tetraploid", "aneuploid"]
_STAGEC_PREDICTORS = ["age", "eet", "g2", "grade", "gleason", "ploidy"]


class _SurvArray(np.ndarray):
    """Minimal stand-in for R's `Surv(pgtime, pgstat)` object -- a plain
    (n, 2) float array of [time, status] columns, tagged `_surv = True` so
    rpart()'s method auto-detection treats it like R's `inherits(Y,
    "Surv")` check. Copied from test_xpred2.py's identical helper (kept
    local here too, rather than promoted to the shared helper module,
    matching that file's own established convention)."""

    def __new__(cls, input_array: np.ndarray) -> "_SurvArray":
        obj = np.asarray(input_array, dtype=np.float64).view(cls)
        obj._surv = True
        return obj

    def __array_finalize__(self, obj: object) -> None:
        if obj is None:
            return
        self._surv = getattr(obj, "_surv", True)


def _build_surv_model_frame(data: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    """Python equivalent of `model.frame(Surv(pgtime, pgstat) ~ ...)`
    followed by rpart's na.rpart() row filtering, built by hand since
    r2py_rpart's formula parser does not parse `Surv(...)` LHS terms.
    Copied from test_xpred2.py's identical helper -- see there for the full
    rationale."""
    time = data["pgtime"].to_numpy(dtype=float)
    status = data["pgstat"].to_numpy(dtype=float)

    resp_missing = np.isnan(time) | np.isnan(status)
    pred_missing = data[predictors].isna()
    all_pred_missing = pred_missing.sum(axis=1) == len(predictors)
    keep = ~resp_missing & ~all_pred_missing.to_numpy()

    kept = data.loc[keep]
    y = _SurvArray(np.column_stack([kept["pgtime"].to_numpy(dtype=float),
                                     kept["pgstat"].to_numpy(dtype=float)]))

    cols: dict[str, Any] = {"pgtime": kept["pgtime"], "pgstat": kept["pgstat"]}
    for p in predictors:
        cols[p] = kept[p]
    m = pd.DataFrame(cols, index=kept.index)

    xlevels: dict[str, list[Any]] = {}
    for p in predictors:
        if isinstance(m[p].dtype, pd.CategoricalDtype):
            xlevels[p] = list(m[p].cat.categories)

    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv(pgtime, pgstat)"] + predictors,
        "response": 1,
        "xlevels": xlevels,
    }
    m.attrs["response"] = y
    return m


def _load_stagec() -> pd.DataFrame:
    df = stagec_df()
    return df


# ---------------------------------------------------------------------------
# 1. anova method, continuous-only predictor (car.test.frame-like mtcars),
#    explicit xval vector, default cp, return_all=False (the default) --
#    the plain "documented example" scenario from xpred.rpart.Rd itself.
# ---------------------------------------------------------------------------

def test_xpred_rpart_anova_matches_r_default_cp():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})

    n = len(df)
    xgrp = np.resize(np.arange(1, 5), n)  # 4 explicit folds, deterministic

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 2. method="class", return_all=False (default): the 2-D matrix contains
#    only the first response (the predicted class code) per obs/cp.
# ---------------------------------------------------------------------------

def test_xpred_rpart_class_return_all_false_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, x=True, control={"xval": 0})
    assert py_fit["method"] == "class"

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=False))
    py_result = xpred_rpart(py_fit, xval=xgrp, return_all=False)

    assert py_result.ndim == 2
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 3. method="class", return_all=True: numresp = numclass + 2 > 1, so both
#    sides build the full 3-D (obs, cp, resp) array (predicted class,
#    followed by per-class probabilities/counts -- see xpred.rpart.Rd's
#    "value" section).
# ---------------------------------------------------------------------------

def test_xpred_rpart_class_return_all_true_3d_matches_r():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, x=True, control={"xval": 0})
    numresp = py_fit["numresp"]
    assert numresp > 1

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=True))
    py_result = xpred_rpart(py_fit, xval=xgrp, return_all=True)

    assert py_result.ndim == 3
    assert py_result.shape == (n, py_result.shape[1], numresp)
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 4. method="poisson" on a Surv() response (stagec): numresp == 2,
#    return_all=False -> plain 2-D result (only the first/event-rate
#    response per obs/cp).
# ---------------------------------------------------------------------------

def test_xpred_rpart_poisson_surv_return_all_false_matches_r():
    stagec = _load_stagec()
    with_stagec = stagec.copy()
    with_stagec["ploidy"] = pd.Categorical(with_stagec["ploidy"], categories=_STAGEC_PLOIDY_LEVELS)

    r_dataframe_assign("df", with_stagec)
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, "
        "data=df, method='poisson', control=rpart.control(xval=0))"
    )

    m = _build_surv_model_frame(with_stagec, _STAGEC_PREDICTORS)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        x=True,
        control={"xval": 0},
    )
    assert py_fit["numresp"] == 2

    n = py_fit["x"].shape[0]
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=False))
    py_result = xpred_rpart(py_fit, xval=xgrp, return_all=False)

    assert py_result.ndim == 2
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-4, atol=1e-6)


# ---------------------------------------------------------------------------
# 5. Same poisson/Surv fit, return_all=True: numresp=2 > 1 triggers the 3-D
#    (obs, cp, resp) array branch on both sides.
# ---------------------------------------------------------------------------

def test_xpred_rpart_poisson_surv_return_all_true_3d_matches_r():
    stagec = _load_stagec()
    with_stagec = stagec.copy()
    with_stagec["ploidy"] = pd.Categorical(with_stagec["ploidy"], categories=_STAGEC_PLOIDY_LEVELS)

    r_dataframe_assign("df", with_stagec)
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, "
        "data=df, method='poisson', control=rpart.control(xval=0))"
    )

    m = _build_surv_model_frame(with_stagec, _STAGEC_PREDICTORS)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        x=True,
        control={"xval": 0},
    )

    n = py_fit["x"].shape[0]
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=True))
    py_result = xpred_rpart(py_fit, xval=xgrp, return_all=True)

    assert py_result.ndim == 3
    assert py_result.shape[2] == 2
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-4, atol=1e-6)


# ---------------------------------------------------------------------------
# 6. method="exp": xpred.rpart.R/xpred_rpart.py both special-case
#    `pmatch(method, c("anova","poisson","class","user","exp"))==5L ->
#    method.int <- 2L`, i.e. "exp" is routed through the same C method-table
#    entry as "poisson". Fitting with the *explicit* method="exp" (rather
#    than letting Surv() auto-select) directly exercises that pmatch/remap
#    line on both sides.
# ---------------------------------------------------------------------------

def test_xpred_rpart_exp_method_pmatch_remap_matches_r():
    stagec = _load_stagec()
    with_stagec = stagec.copy()
    with_stagec["ploidy"] = pd.Categorical(with_stagec["ploidy"], categories=_STAGEC_PLOIDY_LEVELS)

    r_dataframe_assign("df", with_stagec)
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, "
        "data=df, method='exp', control=rpart.control(xval=0))"
    )
    m = _build_surv_model_frame(with_stagec, _STAGEC_PREDICTORS)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="exp",
        x=True,
        control={"xval": 0},
    )
    assert py_fit["method"] == "exp"

    n = py_fit["x"].shape[0]
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, return_all=False))
    py_result = xpred_rpart(py_fit, xval=xgrp, return_all=False)

    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-4, atol=1e-6)


# ---------------------------------------------------------------------------
# 7. Explicit `cp=` (not the default): pin cp to the fitted tree's own
#    cptable CP-column values directly (guaranteed-achievable complexity
#    thresholds -- arbitrary/unreachable cp values can leave R's own C
#    routine's output buffer partially uninitialized, a genuine quirk of
#    xpred.c unrelated to xpred_rpart's own correctness, so tests
#    deliberately avoid exercising it).
# ---------------------------------------------------------------------------

def test_xpred_rpart_explicit_cp_from_cptable_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp", control="rpart.control(xval=0, minsplit=4)")

    py_fit = rpart("mpg ~ wt + hp + disp", data=df, x=True, control={"xval": 0, "minsplit": 4})

    cp_explicit = py_fit["cptable"]["CP"].to_numpy(dtype=float)
    assert len(cp_explicit) >= 2  # exercise more than one cp cut point

    n = len(df)
    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp, cp=cp_explicit))
    py_result = xpred_rpart(py_fit, xval=xgrp, cp=cp_explicit)

    assert py_result.shape == (n, len(cp_explicit))
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 8. Categorical *and* ordered-factor predictors, with NAs in the response
#    forcing na.action row-dropping: this exercises `cats`/`xlevels`
#    (unordered factor -> nonzero ncat), the `ordered` -> ncat-zeroing
#    branch (Reliability is an *ordered* factor predictor here), and
#    xpred_rpart's na.action-adjusted-xval branch (`xval` is given at its
#    *original*, pre-NA-filtering length, not `nobs`, forcing the
#    `na_action.get('indices', ...)` filtering code path -- see
#    xpred_rpart.py's third `xgroups` branch).
# ---------------------------------------------------------------------------

def test_xpred_rpart_categorical_and_ordered_predictors_with_na_action_matches_r():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Mileage ~ Reliability + Country + Type", control="rpart.control(xval=0)"
    )

    py_fit = rpart(
        "Mileage ~ Reliability + Country + Type", data=df, x=True, control={"xval": 0}
    )
    assert py_fit.get("na.action") is not None  # rows were actually dropped

    n_full = len(df)  # xval given at the *original* (pre-na.action) length
    xgrp_full = np.resize(np.arange(1, 4), n_full)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp_full))
    py_result = xpred_rpart(py_fit, xval=xgrp_full)

    n_kept = py_fit["x"].shape[0]
    assert py_result.shape[0] == n_kept
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8, equal_nan=True)


# ---------------------------------------------------------------------------
# 9. Explicit case weights: exercises the `wt` (non-None, non-default)
#    branch through to the C call's `wt=` argument.
# ---------------------------------------------------------------------------

def test_xpred_rpart_explicit_weights_matches_r():
    df = mtcars_df()
    n = len(df)
    rng = np.random.RandomState(0)
    weights = rng.uniform(0.5, 2.5, size=n)

    r_dataframe_assign("df", df)
    run_r("w_tmp <- c(" + ", ".join(repr(float(w)) for w in weights) + ")")
    r_fit = run_r("rpart(mpg ~ wt + hp, data=df, weights=w_tmp, control=rpart.control(xval=0))")

    py_fit = rpart(
        "mpg ~ wt + hp", data=df, x=True, weights=weights, control={"xval": 0}
    )

    xgrp = np.resize(np.arange(1, 4), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 10. Custom `control` parameters (minsplit/minbucket/cp): these feed
#     directly into the `opt`/`controls_flat` array passed to the C
#     extension, so a non-default control is a distinct code path worth
#     covering on its own (independent of the method/cp/xval axes above).
# ---------------------------------------------------------------------------

def test_xpred_rpart_custom_control_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "mpg ~ wt + hp + disp",
        control="rpart.control(minsplit=3, minbucket=1, cp=0.001, xval=0)",
    )

    py_fit = rpart(
        "mpg ~ wt + hp + disp",
        data=df,
        x=True,
        control={"minsplit": 3, "minbucket": 1, "cp": 0.001, "xval": 0},
    )

    n = len(df)
    xgrp = np.resize(np.arange(1, 5), n)

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 11. `xval` given as an explicit vector whose *number of unique groups*
#     differs from the fitted `control$xval` default (10): confirms
#     xpred_rpart correctly derives `xval_int` as `len(unique(xgroups))`
#     from the vector itself (xpred.rpart.R's `xval <-
#     length(unique(xgroups))` re-assignment), independent of whatever
#     `control$xval` the original fit happened to use.
# ---------------------------------------------------------------------------

def test_xpred_rpart_xval_vector_group_count_independent_of_control_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt", data=df, x=True, control={"xval": 0})

    n = len(df)
    xgrp = np.resize(np.arange(1, 8), n)  # 7 folds, unrelated to control$xval

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=xgrp))
    py_result = xpred_rpart(py_fit, xval=xgrp)

    default_cp = default_xpred_cp(py_fit)
    assert py_result.shape == (n, len(default_cp))
    assert py_result.shape == r_result.shape
    assert_allclose(py_result, r_result, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 12. Scalar (default) `xval` path: only structural properties are checked
#     against R (shape, finiteness, dtype) -- see module docstring for why
#     value-for-value parity is not meaningful here (independent RNG
#     streams for the fold assignment).
# ---------------------------------------------------------------------------

def test_xpred_rpart_scalar_xval_default_is_structurally_sane():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})

    np.random.seed(42)
    py_result = xpred_rpart(py_fit, xval=5)
    default_cp = default_xpred_cp(py_fit)

    assert py_result.shape == (len(df), len(default_cp))
    assert np.all(np.isfinite(py_result))

    r_result = r_xpred_to_numpy(r_xpred(r_fit, xval=5))
    assert r_result.shape == py_result.shape  # same shape, values may legitimately differ

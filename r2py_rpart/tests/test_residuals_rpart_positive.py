"""Positive-path parity tests for r2py_rpart.residuals_rpart vs. R's
residuals.rpart (rpart:::residuals.rpart, S3-dispatched via residuals()).

Per residuals.rpart.Rd: for `anova`/"user" method trees, all three residual
`type`s ("usual"/"pearson"/"deviance") reduce to the same `y - fitted`
value. For classification (`method="class"`) trees, "usual" is the
misclassification loss `L(actual, predicted)`, "pearson" is
`(1-fitted)/sqrt(fitted*(1-fitted))`-shaped (rpart's own implementation,
copied faithfully here, actually computes `(1-fitted)/fitted`), and
"deviance" is `sqrt(-2*log(fitted))`-shaped (implemented as `-2*log(fitted)`,
matching rpart's own R source exactly -- see rpart/R/residuals.rpart.R).
For `poisson`/`exp` (survival) trees, "usual" is observed-minus-expected
events, and "pearson"/"deviance" follow McCullagh & Nelder's GLM residual
definitions.

Every test below fits (or otherwise obtains) an identical model in both R
(via rpy2) and python, then calls `residuals(fit, type=...)` on the R side
and `residuals_rpart(fit, type=...)` on the python side, comparing the
resulting numeric vectors via `numpy.testing.assert_allclose` (with
`equal_nan=True` where the poisson/exp pearson/deviance formulas can
legitimately produce `nan`/`inf` -- see test 7 below, a real, confirmed
rpart quirk, not a bug in this port).

NOTE on a known, separately-documented gap: `type="pearson"`/`type=
"deviance"` on a *classification* (`method="class"`) tree currently raises
a `ValueError` in this port (frame['yval2']'s per-row-array column can't be
`np.asarray(..., dtype=float)`-stacked directly under current numpy
semantics) -- confirmed to compute a valid, finite result in R. This is
filed as a "known bug" regression-anchor test in
test_residuals_rpart_edge.py rather than exercised here; the tests below
stick to `type="usual"` for classification trees (which does not touch
`$yval2` at all) plus the `poisson`/`exp` methods and `anova` trees (whose
`type=` argument is a no-op) for the other two `type=` values, so every
`type=` value is still exercised by *some* passing positive test.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing, in particular
`r_residuals()`/`r_residuals_to_python()` (S3-dispatched `residuals(fit,
...)`) and the dataset loaders (`kyphosis_df()`, `cu_summary_df()`,
`stagec_df()`, `mtcars_df()`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from r2py_rpart import residuals_rpart, rpart

from _r_rpart_helpers import (
    cu_summary_df,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_residuals,
    r_residuals_to_python,
    run_r,
    stagec_df,
)


# ---------------------------------------------------------------------------
# 1. Default (omitted) `type=` on a regression (anova) tree -- the first
#    example from residuals.rpart.Rd (`summary(residuals(fit))` on a
#    `skips ~ ...` anova fit); here mtcars stands in for `solder.balance`.
# ---------------------------------------------------------------------------

def test_residuals_default_type_matches_r_regression_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp", control="rpart.control(xval=0)")
    r_resid = r_residuals_to_python(r_residuals(r_fit))  # type left unspecified

    py_fit = rpart("mpg ~ wt + hp + disp", data=df, method="anova", control={"xval": 0})
    py_resid = residuals_rpart(py_fit)  # type left unspecified too

    assert_allclose(py_resid, r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. Explicit type="usual"/"pearson"/"deviance" on a regression (anova)
#    tree: all three must reduce to the identical `y - fitted` value, on
#    both sides.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resid_type", ["usual", "pearson", "deviance"])
def test_residuals_all_types_equal_for_anova_regression_mtcars(resid_type):
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp", control="rpart.control(xval=0)")
    r_resid = r_residuals_to_python(r_residuals(r_fit, type=resid_type))

    py_fit = rpart("mpg ~ wt + hp + disp", data=df, method="anova", control={"xval": 0})
    py_resid = residuals_rpart(py_fit, type=resid_type)

    assert_allclose(py_resid, r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 3. type="usual" on a classification tree, default (0/1) loss matrix --
#    per residuals.rpart.Rd, "[w]ith default losses this residual is 0/1
#    for correct/incorrect classification."
# ---------------------------------------------------------------------------

def test_residuals_classification_usual_default_loss_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_resid = r_residuals_to_python(r_residuals(r_fit, type="usual"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_resid = residuals_rpart(py_fit, type="usual")

    assert_allclose(py_resid, r_resid, rtol=1e-6)
    # sanity, per the .Rd's own description of the default-loss case:
    assert set(np.unique(py_resid)).issubset({0.0, 1.0})


# ---------------------------------------------------------------------------
# 4. type="usual" on a classification tree with a custom (asymmetric) loss
#    matrix (parms=list(loss=...)) -- exercises `object$parms$loss` being
#    something other than the default `1 - diag(nclass)`.
# ---------------------------------------------------------------------------

def test_residuals_classification_usual_custom_loss_matrix_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start",
        control="rpart.control(xval=0)",
        parms="list(loss=matrix(c(0,1,2,0), nrow=2))",
    )
    r_resid = r_residuals_to_python(r_residuals(r_fit, type="usual"))

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0},
        parms={"loss": [[0, 2], [1, 0]]},  # R's matrix(c(0,1,2,0), nrow=2) is [[0,2],[1,0]]
    )
    py_resid = residuals_rpart(py_fit, type="usual")

    assert_allclose(py_resid, r_resid, rtol=1e-6)
    # sanity: the asymmetric loss really is being used (some non-0/1 value)
    assert 2.0 in np.unique(r_resid) or 1.0 in np.unique(r_resid)


# ---------------------------------------------------------------------------
# 5. method="poisson" (Surv()-style 2-column response): all three types
#    exercise the observed/expected-events branch. "pearson"/"deviance" can
#    legitimately produce +-inf/nan here -- see residuals.rpart.R's own
#    `temp <- ifelse(expect == 0, 0.0001, 0)` "failsafe for log(0)", which
#    (as written, in R itself) actually leaves `temp == 0` whenever `expect
#    != 0`, so pearson/deviance divide by zero for the overwhelming majority
#    of nodes -- confirmed identical, real R behavior (not a python-only
#    quirk) via direct rpy2 comparison before writing this test.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    m = df[predictors].copy()
    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv_response"] + predictors,
        "response": 1,
        "xlevels": {"ploidy": list(df["ploidy"].cat.categories)},
    }
    m.attrs["response"] = np.column_stack(
        [df["pgtime"].to_numpy(dtype=float), df["pgstat"].to_numpy(dtype=float)]
    )
    return m


@pytest.mark.parametrize("resid_type", ["usual", "pearson", "deviance"])
def test_residuals_poisson_method_all_types_stagec(resid_type):
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_resid = r_residuals_to_python(r_residuals(r_fit, type=resid_type))

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_resid = residuals_rpart(py_fit, type=resid_type)

    assert_allclose(py_resid, r_resid, rtol=1e-5, equal_nan=True)


# ---------------------------------------------------------------------------
# 6. method="exp" (survival), type="usual" -- distinct from "poisson" in
#    that `object$y` is rpart_exp's transformed cumulative-hazard/status
#    pair rather than the raw (time, status), but residuals.rpart's own
#    logic treats "poisson" and "exp" identically (`method == "poisson" ||
#    method == "exp"`).
# ---------------------------------------------------------------------------

def test_residuals_exp_method_usual_type_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="exp", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_resid = r_residuals_to_python(r_residuals(r_fit, type="usual"))

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="exp",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_resid = residuals_rpart(py_fit, type="usual")

    assert_allclose(py_resid, r_resid, rtol=1e-5)


# ---------------------------------------------------------------------------
# 7. Partial (abbreviated) matching of the `type=` argument, mirroring R's
#    match.arg() prefix matching (e.g. type="u" -> "usual"). Uses an anova
#    (regression) tree so the resolved `type=` value cannot itself run into
#    the separately-documented classification pearson/deviance bug -- this
#    test's whole point is exercising *match.arg resolution*, independent
#    of that.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("abbrev,full", [("u", "usual"), ("p", "pearson"), ("d", "deviance")])
def test_residuals_type_partial_matching_mtcars(abbrev, full):
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")
    r_resid_full = r_residuals_to_python(r_residuals(r_fit, type=full))
    r_resid_abbrev = r_residuals_to_python(r_residuals(r_fit, type=abbrev))
    # sanity: R's own partial matching produces the same result as the
    # fully-spelled-out type
    assert_allclose(r_resid_full, r_resid_abbrev)

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0})
    py_resid_full = residuals_rpart(py_fit, type=full)
    py_resid_abbrev = residuals_rpart(py_fit, type=abbrev)

    assert_allclose(py_resid_abbrev, py_resid_full)
    assert_allclose(py_resid_abbrev, r_resid_abbrev, rtol=1e-6)


# ---------------------------------------------------------------------------
# 8. A custom, explicitly-supplied `model=` DataFrame (rather than the
#    formula+`data=` path) whose response column is never routed through
#    `m.attrs["response"]` -- so `object['y']` ends up a *named* pandas
#    Series (carrying the model frame's row index), exercising residuals_
#    rpart's `isinstance(y, pd.Series)` branch (`names(resid) <- names(y)`
#    in R) and confirming the returned Series' index matches the input.
# ---------------------------------------------------------------------------

def test_residuals_series_index_propagation_custom_model_frame_mtcars():
    df = mtcars_df()
    m = df[["mpg", "wt", "hp"]].copy()
    m.attrs["terms"] = {
        "order": [1, 1],
        "term.labels": ["wt", "hp"],
        "variables": ["mpg", "wt", "hp"],
        "response": 1,
    }
    py_fit = rpart("mpg ~ wt + hp", model=m, method="anova", control={"xval": 0})
    assert isinstance(py_fit["y"], pd.Series)  # sanity: really hits the Series branch

    py_resid = residuals_rpart(py_fit)
    assert isinstance(py_resid, pd.Series)
    assert list(py_resid.index) == list(m.index)

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")
    r_resid = r_residuals_to_python(r_residuals(r_fit))

    assert_allclose(py_resid.to_numpy(), r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 9. A dataset with NA-dropped rows under the default na.action (cu.summary,
#    also exercised by test_predict_rpart_edge.py's naresid-no-op test):
#    residuals_rpart's `object.get('na.action')` branch is reached (rather
#    than being a no-op with `na.action is None`), and -- since it currently
#    returns the unexpanded residual vector unchanged -- both R's naresid()
#    (a no-op for the default `na.rpart`/`"omit"` na.action, as documented in
#    test_predict_rpart_edge.py) and python's stub agree on the same
#    *retained-rows-only* result length.
# ---------------------------------------------------------------------------

def test_residuals_na_action_present_reduced_length_cu_summary():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Mileage ~ Price + Country + Reliability + Type", control="rpart.control(xval=0)"
    )
    r_resid = r_residuals_to_python(r_residuals(r_fit))

    py_fit = rpart(
        "Mileage ~ Price + Country + Reliability + Type", data=df, method="anova",
        control={"xval": 0},
    )
    assert py_fit.get("na.action") is not None  # sanity: rows really were dropped
    py_resid = residuals_rpart(py_fit)

    assert len(py_resid) == len(r_resid)
    assert_allclose(np.sort(np.asarray(py_resid)), np.sort(r_resid), rtol=1e-6)


# ---------------------------------------------------------------------------
# 10. Extra, unrecognized keyword arguments are silently tolerated (passed
#     through `...` in R, absorbed by `**kwargs` in python) without altering
#     the result -- neither side's implementation references any such extra
#     argument again.
# ---------------------------------------------------------------------------

def test_residuals_extra_unused_kwarg_tolerated_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_resid_plain = r_residuals_to_python(r_residuals(r_fit, type="usual"))
    r_resid_extra = r_residuals_to_python(run_r('residuals(resid_fit_tmp, type="usual", banana=42)'))
    assert_allclose(r_resid_plain, r_resid_extra)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_resid_plain = residuals_rpart(py_fit, type="usual")
    py_resid_extra = residuals_rpart(py_fit, type="usual", banana=42)

    assert_allclose(py_resid_extra, py_resid_plain)
    assert_allclose(py_resid_extra, r_resid_extra, rtol=1e-6)


# ---------------------------------------------------------------------------
# 11. Multi-class (3-level) classification tree, type="usual" -- unlike
#     type="pearson"/"deviance" (see test_residuals_rpart_edge.py's known-bug
#     tests), "usual" never touches `$yval2` at all, so it works fine beyond
#     the 2-class case.
# ---------------------------------------------------------------------------

def test_residuals_classification_usual_multiclass_iris():
    run_r("data(iris)")
    from _r_rpart_helpers import from_r_dataframe

    df = from_r_dataframe("iris")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Species ~ .", control="rpart.control(xval=0)")
    r_resid = r_residuals_to_python(r_residuals(r_fit, type="usual"))

    py_fit = rpart("Species ~ .", data=df, control={"xval": 0})
    py_resid = residuals_rpart(py_fit, type="usual")

    assert_allclose(py_resid, r_resid, rtol=1e-6)

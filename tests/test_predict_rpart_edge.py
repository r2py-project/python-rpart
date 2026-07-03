"""Boundary/edge-case parity tests for r2py_rpart.predict_rpart vs. R's
predict.rpart (rpart:::predict.rpart, S3-dispatched via predict()).

These focus on the functional extremes: a root-only (no-split) tree, empty
newdata, NaN/Inf predictor values, a factor level that was never used to
grow the tree, single-row newdata (which exercises an R matrix-drop quirk),
and the interaction between predict()'s own newdata path and the *fitted*
object's na.action.

See tests/_r_rpart_helpers.py for r_predict()/r_predict_to_python() (the
predict-specific rpy2 plumbing) and the general dataset loaders.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import rpy2.robjects as ro
from numpy.testing import assert_allclose

from r2py_rpart import predict_rpart, rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    cu_summary_df,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_predict,
    r_predict_to_python,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. Root-only tree (a single leaf node, forced via cp=1 so no split ever
#    clears the complexity threshold): every type= must still work and
#    return the same constant prediction for every observation.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pred_type", ["vector", "class", "prob", "matrix"])
def test_predict_root_only_tree_all_types(pred_type):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=1)")
    r_pred = r_predict_to_python(r_predict(r_fit, type=pred_type))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0, "cp": 1})
    assert len(py_fit["frame"]) == 1  # sanity: really is root-only
    py_pred = predict_rpart(py_fit, type=pred_type)

    if pred_type == "class":
        assert list(py_pred.astype(str)) == r_pred
    elif isinstance(py_pred, pd.DataFrame):
        assert_allclose(py_pred.to_numpy(), r_pred.to_numpy(), rtol=1e-6)
    else:
        assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. Empty newdata (0 rows): both R and Python must return a length-0
#    result rather than erroring.
# ---------------------------------------------------------------------------

def test_predict_empty_newdata_returns_empty():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    nd = df.iloc[0:0]
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type="vector"))
    assert len(r_pred) == 0

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=nd, type="vector")
    assert len(py_pred) == 0


# ---------------------------------------------------------------------------
# 3. NaN in a newdata predictor column, with surrogates disabled
#    (maxsurrogate=0): the C splitting code's own missing-value handling
#    (not an R-level/Python-level na.action) must still produce a
#    prediction for that row.
# ---------------------------------------------------------------------------

def test_predict_newdata_nan_predictor_no_surrogates():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, maxsurrogate=0)"
    )
    nd = df.iloc[0:5].copy()
    nd["Age"] = nd["Age"].astype(float)
    nd.loc[nd.index[1], "Age"] = np.nan
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type="vector"))

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0, "maxsurrogate": 0}
    )
    py_pred = predict_rpart(py_fit, newdata=nd, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 4. Inf in a newdata predictor column: must fall to whichever side of every
#    split Inf naturally belongs to, without erroring.
# ---------------------------------------------------------------------------

def test_predict_newdata_inf_predictor():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    nd = df.iloc[0:3].copy()
    nd["Age"] = nd["Age"].astype(float)
    nd.loc[nd.index[0], "Age"] = np.inf
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type="vector"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=nd, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 5. A factor level that is a legitimate xlevel of the fitted tree (i.e. it
#    appears in the training column's categories) but never actually
#    occurred in any training row, so no split was ever built to route it:
#    per predict.rpart.Rd, "it is left at the deepest possible node and
#    frame$yval at the node is the prediction" (contrast with a genuinely
#    *new*, un-declared level, which model.frame() raises an error for --
#    see the newdata-missing-column negative tests for that failure mode).
# ---------------------------------------------------------------------------

def test_predict_newdata_factor_level_unused_in_training():
    rng = np.random.RandomState(42)
    n = 60
    df = pd.DataFrame(
        {
            "x1": rng.uniform(0, 10, n),
            "grp": pd.Categorical(rng.choice(["A", "B"], n), categories=["A", "B", "C"]),
        }
    )
    df["y"] = df["x1"] + (df["grp"] == "B").astype(float) * 5 + rng.normal(0, 0.1, n)

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x1 + grp", control="rpart.control(xval=0, minsplit=5, cp=0.001)")
    r_xlevels_grp = list(ro.r["attr"](r_fit, "xlevels").rx2("grp"))
    assert r_xlevels_grp == ["A", "B", "C"]

    nd = df.iloc[0:3].copy()
    nd["grp"] = pd.Categorical(["C", "C", "A"], categories=["A", "B", "C"])
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type="vector"))

    py_fit = rpart("y ~ x1 + grp", data=df, control={"xval": 0, "minsplit": 5, "cp": 0.001})
    assert py_fit["_xlevels"]["grp"] == ["A", "B", "C"]
    py_pred = predict_rpart(py_fit, newdata=nd, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 6. Singleton (single-row) newdata for type="vector"/"class"/"prob": these
#    must all still work.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pred_type", ["vector", "class", "prob"])
def test_predict_singleton_newdata(pred_type):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    nd = df.iloc[0:1]
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type=pred_type))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=nd, type=pred_type)

    if pred_type == "class":
        assert list(py_pred.astype(str)) == r_pred
    elif isinstance(py_pred, pd.DataFrame):
        assert py_pred.shape[0] == 1
        assert_allclose(py_pred.to_numpy(), r_pred.to_numpy(), rtol=1e-6)
    else:
        assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 7. Singleton (single-row) newdata for type="matrix": R's own
#    `frame$yval2[where, ]` (no `drop = FALSE`) *drops* to a plain vector
#    when only one row is selected, and the subsequent
#    `dimnames(pred) <- list(names(where), NULL)` then errors out because
#    the (now dimension-less) result is no longer an array/matrix -- i.e.
#    R itself cannot serve type="matrix" for exactly one newdata row. This
#    documents that quirk as a parity requirement: both sides must raise
#    (or, if this Python port diverges by not raising, the mismatch should
#    surface here rather than silently going untested).
# ---------------------------------------------------------------------------

def test_predict_singleton_newdata_type_matrix_matches_r_quirk():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    nd = df.iloc[0:1]

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})

    r_message = r_error_message(lambda: r_predict(r_fit, newdata=nd, type="matrix"))
    try:
        predict_rpart(py_fit, newdata=nd, type="matrix")
        py_message = None
    except Exception as exc:  # noqa: BLE001 - want to compare "did it raise" either way
        py_message = str(exc)

    if r_message is not None:
        assert py_message is not None, (
            "R raises for type='matrix' with single-row newdata (a matrix->vector "
            f"drop quirk in R's own dimnames<- call: {r_message!r}) but the Python "
            "port did not raise -- this is a genuine behavioral divergence."
        )
        assert_python_and_r_errors_agree(py_message, r_message, context="type='matrix', 1-row newdata")
    else:
        assert py_message is None, f"R did not raise but python did: {py_message!r}"


# ---------------------------------------------------------------------------
# 8. Duplicate rows in newdata: predictions must be identical for exact
#    duplicates (a purely deterministic-routing sanity check at the
#    boundary of "newdata has repeated observations").
# ---------------------------------------------------------------------------

def test_predict_newdata_duplicate_rows_give_identical_predictions():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    one_row = df.iloc[[3]]
    nd = pd.concat([one_row, one_row, one_row], ignore_index=True)
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=nd, type="vector"))
    assert r_pred[0] == r_pred[1] == r_pred[2]

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=nd, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)
    assert py_pred[0] == py_pred[1] == py_pred[2]


# ---------------------------------------------------------------------------
# 9. predict()'s own na.action expansion (naresid) is only ever applied on
#    the *fitted-object* path (no newdata given); when the fit dropped rows
#    via the default na.action (na.rpart, whose class is c("na.rpart",
#    "omit")), R's naresid() dispatches to naresid.default (a no-op) rather
#    than naresid.exclude, since neither "na.rpart" nor "omit" has a
#    registered naresid method of its own in base R -- so the *returned*
#    prediction length equals the number of *retained* training rows, not
#    the original row count. This documents that surprising-but-real R
#    behavior as the parity target for the object['where']/no-newdata path.
# ---------------------------------------------------------------------------

def test_predict_no_newdata_na_action_naresid_is_effectively_a_noop():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Mileage ~ Price + Country + Reliability + Type", control="rpart.control(xval=0)"
    )
    n_dropped = int(ro.r["length"](r_fit.rx2("na.action"))[0])
    n_total = int(run_r("nrow(df)")[0])
    assert 0 < n_dropped < n_total  # sanity: this dataset really has dropped rows

    r_pred = r_predict_to_python(r_predict(r_fit))
    assert len(r_pred) == n_total - n_dropped  # R: naresid is a no-op here

    py_fit = rpart(
        "Mileage ~ Price + Country + Reliability + Type", data=df, method="anova",
        control={"xval": 0},
    )
    py_pred = predict_rpart(py_fit)

    assert len(py_pred) == len(r_pred), (
        "Python's predict_rpart(fit) (no newdata) is expected to match R's "
        "naresid-is-a-no-op behavior for the default na.rpart/omit na.action "
        f"(R returns {len(r_pred)} predictions for {n_total} rows with "
        f"{n_dropped} dropped), but got {len(py_pred)}."
    )
    assert_allclose(np.sort(py_pred), np.sort(r_pred), rtol=1e-6)

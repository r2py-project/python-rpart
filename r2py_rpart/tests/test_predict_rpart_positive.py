"""Positive-path parity tests for r2py_rpart.predict_rpart vs. R's
predict.rpart (rpart:::predict.rpart, S3-dispatched via predict()).

Each test fits an identical model in both R (via rpy2) and Python, then
calls predict in both and asserts the results match: for `type="vector"`
via numeric comparison, for `type="class"` via the predicted level labels,
and for `type="matrix"`/`type="prob"` via the full value matrix (plus
column names for `type="prob"`).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing, in particular
`r_predict()` (builds/evaluates an R `predict(fit, ...)` call) and
`r_predict_to_python()` (normalizes the R return value -- numeric vector,
factor, or matrix -- into something directly comparable to
r2py_rpart.predict_rpart()'s return value).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from r2py_rpart import predict_rpart, rpart

from _r_rpart_helpers import (
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_predict,
    r_predict_to_python,
    run_r,
    stagec_df,
)


# ---------------------------------------------------------------------------
# 1. type="vector" on a regression tree, no newdata (uses object$where /
#    object['where'] directly) -- the first example from predict.rpart.Rd:
#    `z.auto <- rpart(Mileage ~ Weight, car.test.frame); predict(z.auto)`.
# ---------------------------------------------------------------------------

def test_predict_vector_no_newdata_matches_r_car_test_frame():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_pred = predict_rpart(py_fit)

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. Default (missing) `type=` on a classification tree: mtype/nclass logic
#    must select "prob" automatically, matching R's `mtype && nclass > 0`.
# ---------------------------------------------------------------------------

def test_predict_default_type_is_prob_for_classification_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit))  # type left unspecified

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit)  # type left unspecified too

    assert isinstance(py_pred, pd.DataFrame)
    assert list(py_pred.columns) == list(r_pred.columns)
    assert_allclose(py_pred.to_numpy(), r_pred.to_numpy(), rtol=1e-6)


# ---------------------------------------------------------------------------
# 3. Explicit type="vector" on a classification tree returns numeric class
#    codes (not labels).
# ---------------------------------------------------------------------------

def test_predict_type_vector_classification_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, type="vector"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 4. type="class" on a classification tree returns the predicted factor
#    labels.
# ---------------------------------------------------------------------------

def test_predict_type_class_classification_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, type="class"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, type="class")

    assert list(py_pred.astype(str)) == r_pred
    assert list(py_pred.categories) == list(df["Kyphosis"].cat.categories)


# ---------------------------------------------------------------------------
# 5. type="matrix" on a classification tree returns the full yval2 matrix
#    (predicted class, class counts, class probabilities, node probability).
# ---------------------------------------------------------------------------

def test_predict_type_matrix_classification_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, type="matrix"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, type="matrix")

    assert isinstance(py_pred, pd.DataFrame)
    assert_allclose(py_pred.to_numpy(), r_pred.to_numpy(), rtol=1e-6)


# ---------------------------------------------------------------------------
# 6. type="matrix" on a regression tree (no $yval2 column) falls back to the
#    plain yval vector, exactly like `type="vector"`.
# ---------------------------------------------------------------------------

def test_predict_type_matrix_regression_falls_back_to_vector_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp", control="rpart.control(xval=0)")
    r_pred_matrix = r_predict_to_python(r_predict(r_fit, type="matrix"))
    r_pred_vector = r_predict_to_python(r_predict(r_fit, type="vector"))
    assert_allclose(r_pred_matrix, r_pred_vector)  # sanity: R itself falls back

    py_fit = rpart("mpg ~ wt + hp + disp", data=df, method="anova", control={"xval": 0})
    py_pred = predict_rpart(py_fit, type="matrix")

    assert not isinstance(py_pred, pd.DataFrame)
    assert_allclose(py_pred, r_pred_matrix, rtol=1e-6)


# ---------------------------------------------------------------------------
# 7. Explicit newdata (held-out rows) on a regression tree.
# ---------------------------------------------------------------------------

def test_predict_with_newdata_regression_holdout_mtcars():
    df = mtcars_df()
    train, test = df.iloc[:24].reset_index(drop=True), df.iloc[24:].reset_index(drop=True)
    r_dataframe_assign("df", train)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=test, type="vector"))

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=train, method="anova", control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=test, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6)


# ---------------------------------------------------------------------------
# 8. Explicit newdata on a classification tree, type="class" -- mirrors the
#    predict.rpart.Rd `iris` example (`table(predict(fit, iris[-sub,],
#    type = "class"), iris[-sub, "Species"])`).
# ---------------------------------------------------------------------------

def test_predict_with_newdata_classification_class_type_iris():
    run_r("data(iris)")
    df = from_r_dataframe("iris")

    train = pd.concat([df.iloc[0:30], df.iloc[50:80], df.iloc[100:130]]).reset_index(drop=True)
    test = pd.concat([df.iloc[30:50], df.iloc[80:100], df.iloc[130:150]]).reset_index(drop=True)

    r_dataframe_assign("df", train)
    r_fit = r_fit_rpart("Species ~ .", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=test, type="class"))

    py_fit = rpart("Species ~ .", data=train, control={"xval": 0})
    py_pred = predict_rpart(py_fit, newdata=test, type="class")

    assert list(py_pred.astype(str)) == r_pred


# ---------------------------------------------------------------------------
# 9. Explicit newdata mixing an *ordered* factor (Reliability) with plain
#    (unordered) factors (Country, Type) -- cu.summary, type="vector".
# ---------------------------------------------------------------------------

def test_predict_with_newdata_ordered_and_unordered_factors_cu_summary():
    df = cu_summary_df()
    train, test = df.iloc[:80].reset_index(drop=True), df.iloc[80:].reset_index(drop=True)
    r_dataframe_assign("df", train)
    run_r(
        'df$Reliability <- factor(df$Reliability, levels=c("Much worse", "worse", "average", '
        '"better", "Much better"), ordered=TRUE)'
    )
    r_fit = r_fit_rpart(
        "Mileage ~ Price + Country + Reliability + Type", control="rpart.control(xval=0)"
    )
    r_pred = r_predict_to_python(r_predict(r_fit, newdata=test, type="vector"))

    py_fit = rpart(
        "Mileage ~ Price + Country + Reliability + Type", data=train, method="anova",
        control={"xval": 0},
    )
    py_pred = predict_rpart(py_fit, newdata=test, type="vector")

    assert_allclose(py_pred, r_pred, rtol=1e-6, equal_nan=True)


# ---------------------------------------------------------------------------
# 10. type="prob" on a 3-class classification tree: columns must be in
#     ylevels order (setosa, versicolor, virginica).
# ---------------------------------------------------------------------------

def test_predict_type_prob_multiclass_iris():
    run_r("data(iris)")
    df = from_r_dataframe("iris")

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Species ~ .", control="rpart.control(xval=0)")
    r_pred = r_predict_to_python(r_predict(r_fit, type="prob"))

    py_fit = rpart("Species ~ .", data=df, control={"xval": 0})
    py_pred = predict_rpart(py_fit, type="prob")

    assert list(py_pred.columns) == list(r_pred.columns) == ["setosa", "versicolor", "virginica"]
    assert_allclose(py_pred.to_numpy(), r_pred.to_numpy(), rtol=1e-6)


# ---------------------------------------------------------------------------
# 11. Partial (abbreviated) matching of the `type=` argument, mirroring
#     R's match.arg() prefix matching (e.g. type="v" -> "vector").
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("abbrev,full", [("v", "vector"), ("cl", "class"), ("pr", "prob"), ("ma", "matrix")])
def test_predict_type_partial_matching_kyphosis(abbrev, full):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_pred_full = r_predict_to_python(r_predict(r_fit, type=full))
    r_pred_abbrev = r_predict_to_python(r_predict(r_fit, type=abbrev))
    # sanity check: R's own partial matching produces the same result as the
    # fully-spelled-out type
    if isinstance(r_pred_full, pd.DataFrame):
        assert_allclose(r_pred_full.to_numpy(), r_pred_abbrev.to_numpy())
    elif isinstance(r_pred_full, list):
        assert r_pred_full == r_pred_abbrev
    else:
        assert_allclose(r_pred_full, r_pred_abbrev)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    py_pred_full = predict_rpart(py_fit, type=full)
    py_pred_abbrev = predict_rpart(py_fit, type=abbrev)

    if isinstance(py_pred_full, pd.DataFrame):
        assert_allclose(py_pred_abbrev.to_numpy(), py_pred_full.to_numpy())
    elif isinstance(py_pred_full, pd.Categorical):
        assert list(py_pred_abbrev) == list(py_pred_full)
    else:
        assert_allclose(py_pred_abbrev, py_pred_full)


# ---------------------------------------------------------------------------
# 12. method="poisson" (Surv()-style 2-column response): type="vector" and
#     type="matrix" both exercise the multi-response $yval2 branch.
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


def test_predict_poisson_method_vector_and_matrix_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_pred_vec = r_predict_to_python(r_predict(r_fit, type="vector"))
    r_pred_mat = r_predict_to_python(r_predict(r_fit, type="matrix"))

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_pred_vec = predict_rpart(py_fit, type="vector")
    py_pred_mat = predict_rpart(py_fit, type="matrix")

    assert_allclose(py_pred_vec, r_pred_vec, rtol=1e-5)
    assert_allclose(py_pred_mat.to_numpy(), r_pred_mat.to_numpy(), rtol=1e-5)

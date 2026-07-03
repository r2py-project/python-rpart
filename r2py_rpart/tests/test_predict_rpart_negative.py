"""Negative-path parity tests for r2py_rpart.predict_rpart vs. R's
predict.rpart (rpart:::predict.rpart, S3-dispatched via predict()).

Each test triggers an error condition in both R (via rpy2) and Python, and
asserts that *both* raise. If both raise but with differently-worded
messages, `assert_python_and_r_errors_agree` warns rather than fails (error
text is not part of rpart's documented contract) -- see
tests/_r_rpart_helpers.py.

Every `raise` branch inside predict_rpart.py is exercised here:
  - `object` is not a legitimate "rpart" object            -> ValueError
  - `type=` doesn't match/partially-match any valid type    -> ValueError
  - `type="class"` requested on a non-classification tree   -> ValueError
  - `type="prob"` requested on a non-classification tree    -> ValueError (falls
    through to the same "Invalid prediction" branch as type="class")
  - `newdata` missing a predictor column the tree needs      -> KeyError (Python)
  - missing the required `object` positional argument        -> TypeError
"""
from __future__ import annotations

import pytest
import rpy2.robjects as ro

from r2py_rpart import predict_rpart, rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_predict,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. `object` is not a legitimate rpart object (plain dict/list/etc).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_object", ["not a dict", 123, [1, 2, 3], {"no_frame_key": 1}, None])
def test_predict_invalid_object_raises(bad_object):
    with pytest.raises(Exception) as exc_info:
        predict_rpart(bad_object)
    # rpart:::predict.rpart's own `inherits(object, "rpart")` check requires
    # calling the internal method directly (bypassing S3 dispatch via
    # predict(), which would itself fail to *find* a method for a bare list
    # before ever reaching that check).
    r_message = r_error_message(lambda: run_r("rpart:::predict.rpart(list(a=1))"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid object {bad_object!r}")


# ---------------------------------------------------------------------------
# 2. Missing the required `object` positional argument entirely.
# ---------------------------------------------------------------------------

def test_predict_missing_object_argument_raises():
    with pytest.raises(TypeError) as exc_info:
        predict_rpart()
    r_message = r_error_message(lambda: run_r("rpart:::predict.rpart()"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="missing object argument")


# ---------------------------------------------------------------------------
# 3. `type=` is a string that neither exactly nor partially matches any of
#    "vector"/"prob"/"class"/"matrix".
# ---------------------------------------------------------------------------

def test_predict_invalid_type_string_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, type="bogus")

    r_message = r_error_message(lambda: r_predict(r_fit, type="bogus"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type='bogus'")


# ---------------------------------------------------------------------------
# 4. `type=` an empty string: no valid type starts with "", but match.arg()
#    still requires a unique match, so R errors just like an unmatched type.
# ---------------------------------------------------------------------------

def test_predict_empty_type_string_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, type="")

    r_message = r_error_message(lambda: r_predict(r_fit, type=""))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type=''")


# ---------------------------------------------------------------------------
# 5. `type=` a non-string (R's match.arg requires a character vector).
# ---------------------------------------------------------------------------

def test_predict_non_string_type_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, type=123)

    ro.globalenv["neg_fit_tmp"] = r_fit
    r_message = r_error_message(lambda: run_r("predict(neg_fit_tmp, type=123)"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type=123 (non-string)")


# ---------------------------------------------------------------------------
# 6. type="class" requested on a regression (non-classification) tree.
# ---------------------------------------------------------------------------

def test_predict_type_class_on_regression_tree_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, type="class")

    r_message = r_error_message(lambda: r_predict(r_fit, type="class"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type='class' on regression tree")


# ---------------------------------------------------------------------------
# 7. type="prob" requested on a regression (non-classification) tree.
# ---------------------------------------------------------------------------

def test_predict_type_prob_on_regression_tree_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, type="prob")

    r_message = r_error_message(lambda: r_predict(r_fit, type="prob"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="type='prob' on regression tree")


# ---------------------------------------------------------------------------
# 8. `newdata` is missing a predictor column the fitted tree actually needs.
# ---------------------------------------------------------------------------

def test_predict_newdata_missing_required_column_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    nd = df[["Age", "Number"]].iloc[0:3].copy()  # missing 'Start'
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, newdata=nd, type="vector")

    r_message = r_error_message(lambda: r_predict(r_fit, newdata=nd, type="vector"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="newdata missing 'Start' column")


# ---------------------------------------------------------------------------
# 9. `newdata` missing *all* predictor columns.
# ---------------------------------------------------------------------------

def test_predict_newdata_missing_all_predictor_columns_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0})
    nd = df[["Kyphosis"]].iloc[0:3].copy()
    with pytest.raises(Exception) as exc_info:
        predict_rpart(py_fit, newdata=nd, type="vector")

    r_message = r_error_message(lambda: r_predict(r_fit, newdata=nd, type="vector"))
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="newdata missing all predictor columns"
    )

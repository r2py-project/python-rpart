"""Positive-path parity tests for r2py_rpart.na_rpart vs. R's
rpart:::na.rpart (rpart's default na.action, used internally by
model.frame() -- see rpart/man/na.rpart.Rd).

na.rpart(x) drops rows of a model frame `x` where either:
  - the response ("y") is missing (if x has a `terms` attribute with a
    non-zero `response` attribute identifying the response column), or
  - *every* explanatory variable is missing (all cases: with or without a
    response column, ANY single non-missing predictor is enough to keep a
    row -- only an all-missing row of predictors is dropped for that
    reason alone).
If nothing is dropped, `x` is returned unchanged (no na.action attached).
Otherwise the returned (filtered) frame carries a `na.action` attribute --
here, r2py_rpart's `.attrs['na.action']` dict of {'indices' (1-based
positions dropped), 'names' (original row labels), 'class'} -- directly
mirroring R's own `attr(result, "na.action")` (an integer vector, named,
classed c("na.rpart", "omit")).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing, in particular:
  - r_na_rpart_result(df, yvar) -- calls R's rpart:::na.rpart(x) (after
    attaching a synthetic `terms`/`response` attribute pair mirroring what
    model.frame() would normally attach) and returns (filtered_df,
    na_action_dict_or_None).
  - with_response_attr(df, yvar) -- the python-side mirror, setting
    df.attrs['terms'] = {'response': yvar} (or leaving it unset for
    yvar=None), for feeding directly into r2py_rpart.na_rpart().
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from r2py_rpart.na_rpart import na_rpart

from _r_rpart_helpers import (
    cu_summary_df,
    r_na_rpart_result,
    with_response_attr,
)


def _assert_matches_r(df: pd.DataFrame, yvar: int | None) -> None:
    """Run both sides on an identical (df, yvar) input and assert the
    filtered frame's values and the na.action metadata agree."""
    r_out, r_na_action = r_na_rpart_result(df, yvar)
    py_out = na_rpart(with_response_attr(df, yvar))

    assert list(py_out.columns) == list(r_out.columns)
    assert_frame_equal(
        py_out.reset_index(drop=True),
        r_out[py_out.columns].reset_index(drop=True),
        check_dtype=False,
    )
    assert list(py_out.index.astype(str)) == list(r_out.index.astype(str))
    assert py_out.attrs.get("na.action") == r_na_action


# ---------------------------------------------------------------------------
# 1. No terms attribute at all (yvar=0 fallback), no missing values at all:
#    x is returned completely unchanged, no na.action attached.
# ---------------------------------------------------------------------------

def test_na_rpart_no_missing_values_no_terms_returns_unchanged():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0], "x1": [10.0, 20.0, 30.0], "x2": [1, 2, 3]})
    _assert_matches_r(df, None)

    py_out = na_rpart(with_response_attr(df, None))
    assert py_out.attrs.get("na.action") is None
    assert len(py_out) == 3


# ---------------------------------------------------------------------------
# 2. yvar=0 (no response column tracked): a row with a missing value in
#    *some but not all* columns is still kept (only fully-missing rows are
#    dropped in this branch).
# ---------------------------------------------------------------------------

def test_na_rpart_partial_missing_row_kept_when_yvar_zero():
    df = pd.DataFrame({
        "a": [1.0, np.nan, 3.0],
        "b": [10.0, 20.0, np.nan],
        "c": [100.0, 200.0, 300.0],
    })
    _assert_matches_r(df, 0)

    py_out = na_rpart(with_response_attr(df, 0))
    assert len(py_out) == 3
    assert py_out.attrs.get("na.action") is None


# ---------------------------------------------------------------------------
# 3. yvar=0: a row missing in *every* column is dropped.
# ---------------------------------------------------------------------------

def test_na_rpart_fully_missing_row_dropped_when_yvar_zero():
    df = pd.DataFrame({
        "a": [1.0, np.nan, 3.0],
        "b": [10.0, np.nan, 30.0],
    })
    _assert_matches_r(df, 0)

    py_out = na_rpart(with_response_attr(df, 0))
    assert len(py_out) == 2
    assert py_out.attrs["na.action"]["indices"] == [2]


# ---------------------------------------------------------------------------
# 4. yvar=1 (response is the first column): a missing response drops the
#    row regardless of how complete the predictors are.
# ---------------------------------------------------------------------------

def test_na_rpart_missing_response_dropped_yvar1():
    df = pd.DataFrame({
        "y": [1.0, np.nan, 3.0, 4.0],
        "x1": [1.0, 2.0, 3.0, 4.0],
        "x2": [1.0, 2.0, 3.0, 4.0],
    })
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 3
    assert py_out.attrs["na.action"]["indices"] == [2]
    assert py_out.attrs["na.action"]["names"] == ["1"]


# ---------------------------------------------------------------------------
# 5. yvar=1: a single (not all) missing predictor, with the response
#    present, is kept.
# ---------------------------------------------------------------------------

def test_na_rpart_single_missing_predictor_kept_yvar1():
    df = pd.DataFrame({
        "y": [1.0, 2.0, 3.0],
        "x1": [1.0, np.nan, 3.0],
        "x2": [1.0, 2.0, 3.0],
    })
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 3
    assert py_out.attrs.get("na.action") is None


# ---------------------------------------------------------------------------
# 6. yvar=1: ALL predictors missing (but response present) still drops the
#    row, even though no single predictor is "the" response.
# ---------------------------------------------------------------------------

def test_na_rpart_all_predictors_missing_dropped_yvar1():
    df = pd.DataFrame({
        "y": [1.0, 2.0, 3.0],
        "x1": [1.0, np.nan, 3.0],
        "x2": [1.0, np.nan, 3.0],
    })
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 2
    assert py_out.attrs["na.action"]["indices"] == [2]


# ---------------------------------------------------------------------------
# 7. Response column in the middle of the frame (yvar=2 of 3 columns) --
#    generality check that na_rpart() does not assume response is column 1.
# ---------------------------------------------------------------------------

def test_na_rpart_response_in_middle_column_yvar2():
    df = pd.DataFrame({
        "x1": [1.0, 2.0, 3.0, 4.0],
        "y": [1.0, np.nan, 3.0, 4.0],
        "x2": [1.0, 2.0, np.nan, 4.0],
    })
    _assert_matches_r(df, 2)

    py_out = na_rpart(with_response_attr(df, 2))
    # row 1 (0-based) dropped: response missing.
    # row 2 (0-based) kept: x2 missing but x1 present (not ALL predictors missing).
    assert len(py_out) == 3
    assert py_out.attrs["na.action"]["indices"] == [2]


# ---------------------------------------------------------------------------
# 8. Response column is the last column (yvar=ncol) -- another generality
#    check on column position.
# ---------------------------------------------------------------------------

def test_na_rpart_response_last_column():
    df = pd.DataFrame({
        "x1": [1.0, 2.0, 3.0],
        "x2": [1.0, 2.0, 3.0],
        "y": [1.0, 2.0, np.nan],
    })
    _assert_matches_r(df, 3)

    py_out = na_rpart(with_response_attr(df, 3))
    assert len(py_out) == 2
    assert py_out.attrs["na.action"]["indices"] == [3]
    assert py_out.attrs["na.action"]["names"] == ["2"]


# ---------------------------------------------------------------------------
# 9. Categorical ("factor") column with a missing value participates in
#    the missingness check exactly like a numeric column.
# ---------------------------------------------------------------------------

def test_na_rpart_categorical_column_with_na_yvar1():
    df = pd.DataFrame({
        "y": [1.0, 2.0, 3.0, 4.0],
        "grp": pd.Categorical(["a", None, "b", "a"], categories=["a", "b"]),
    })
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 3
    assert py_out.attrs["na.action"]["indices"] == [2]


# ---------------------------------------------------------------------------
# 10. Real dataset with NAs (rpart's own cu.summary): both Mileage and
#     Reliability contain missing values, Reliability is an ordered
#     factor -- a realistic multi-column, mixed-dtype model frame.
# ---------------------------------------------------------------------------

def test_na_rpart_real_dataset_cu_summary_yvar1():
    df = cu_summary_df()[["Reliability", "Price", "Country", "Mileage", "Type"]]
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    # Reliability (the response here) has known NAs in cu.summary -- some
    # rows must have been dropped.
    assert len(py_out) < len(df)
    assert py_out.attrs["na.action"] is not None
    assert py_out.attrs["na.action"]["class"] == ("na.rpart", "omit")


# ---------------------------------------------------------------------------
# 11. Larger synthetic frame with missingness scattered across many rows
#     and several predictor columns -- a stress/volume check beyond the
#     small hand-built frames above.
# ---------------------------------------------------------------------------

def test_na_rpart_many_rows_scattered_missingness_yvar1():
    rng = np.random.default_rng(0)
    n = 50
    y = rng.normal(size=n)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    # Drop the response in a few rows, and BOTH predictors in a few others.
    y[[3, 10, 22]] = np.nan
    x1[[5, 6]] = np.nan
    x2[[5, 6]] = np.nan
    x1[[7]] = np.nan  # single missing predictor -- must NOT be dropped for this reason alone
    df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    dropped = set(df.index) - set(py_out.index)
    assert dropped == {3, 5, 6, 10, 22}

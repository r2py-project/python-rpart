"""Boundary/edge-case parity tests for r2py_rpart.rpart vs. R's rpart::rpart.

These exercise functional extremes: empty data, singleton rows, Inf
predictors, entirely-missing predictor columns, degenerate (unsplittable)
data, and control settings pushed to their limits (cp=1, maxdepth=1,
minsplit larger than n). Each test fits the identical data/args in both R
(via rpy2) and Python and compares the resulting `$frame` numerically.

Two of these tests (empty data / an entirely-NaN predictor column) are
included even though they currently *fail*: R resolves them to a valid
(degenerate) single-node tree, but r2py_rpart's C bridge currently raises
a RuntimeError for the same zero-row model frame. That is a real,
reproducible discrepancy uncovered while writing this suite -- see the
docstring on each test for the underlying root cause -- and the tests are
written to assert R's (correct) behavior rather than to encode the bug, so
they will start passing once the underlying buffer-sizing issue is fixed.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart

from _r_rpart_helpers import extract_r_fit, r_dataframe_assign, r_fit_rpart, run_r


# ---------------------------------------------------------------------------
# 1. Empty data (0 observations).
#
#    R's rpart() does not error on this: it returns a degenerate one-row
#    frame (n=0, dev=0, yval=NaN, complexity=NaN). r2py_rpart currently
#    raises `RuntimeError: ... internal output buffer 'dnode' was
#    undersized (tree needed 4 elements, pre-allocated 0)` instead -- the
#    buffer-size calculation in the C bridge assumes at least one
#    observation. This test documents the expected (R-matching) behavior.
# ---------------------------------------------------------------------------

def test_rpart_empty_data_matches_r():
    df = pd.DataFrame({"x": pd.Series([], dtype=float), "y": pd.Series([], dtype=float)})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 2. A predictor column that is entirely NaN.
#
#    R's na.rpart() drops a row only when *every* predictor is missing for
#    that row (see rpart/R/na.rpart.R); with a single all-NaN predictor
#    column, every row qualifies, so the model frame R actually fits on
#    has 0 rows -- the same degenerate case as test 1 above, reached via a
#    different route. This currently fails for the same buffer-sizing
#    reason.
# ---------------------------------------------------------------------------

def test_rpart_all_nan_predictor_column_matches_r():
    n = 20
    df = pd.DataFrame({"x": [np.nan] * n, "y": np.arange(1, n + 1, dtype=float)})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 3. Rows with a missing (NaN) response are dropped by the default
#    na.action, while rows with a missing predictor are kept.
# ---------------------------------------------------------------------------

def test_rpart_nan_response_row_dropped_by_default_na_action_matches_r():
    n = 10
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": [np.nan] + list(range(2, n + 1))})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"xval": 0})

    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert py_fit["frame"]["n"].iloc[0] == n - 1


# ---------------------------------------------------------------------------
# 4. A single Inf value amid an otherwise degenerate predictor: both
#    implementations must handle the infinite value without raising, and
#    (in this configuration) still find no split is worthwhile.
# ---------------------------------------------------------------------------

def test_rpart_inf_valued_predictor_matches_r():
    df = pd.DataFrame(
        {
            "x": [1.0] * 10 + [np.inf] + [1.0] * 9,
            "y": [0.0] * 10 + [100.0] + [0.0] * 9,
        }
    )
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(xval=0, minsplit=2, cp=0.001)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"xval": 0, "minsplit": 2, "cp": 0.001})

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])


# ---------------------------------------------------------------------------
# 5. A singleton (1-row) dataset -- the smallest non-empty input rpart
#    can be given.
# ---------------------------------------------------------------------------

def test_rpart_singleton_row_anova_matches_r():
    df = pd.DataFrame({"x": [1.0], "y": [1.0]})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova")

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])


def test_rpart_singleton_row_class_matches_r():
    r_fit = run_r('rpart(y ~ x, data=data.frame(x=1, y=factor("a")), method="class")')
    r_out = extract_r_fit(r_fit)

    py_fit = rpart(
        "y ~ x",
        data=pd.DataFrame({"x": [1.0], "y": pd.Categorical(["a"])}),
        method="class",
    )

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 6. A constant predictor column: there is nothing to split on, so the
#    fit must degenerate to a single root node regardless of the response.
# ---------------------------------------------------------------------------

def test_rpart_constant_predictor_no_split_matches_r():
    n = 10
    df = pd.DataFrame({"x": [1.0] * n, "y": np.arange(1, n + 1, dtype=float)})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])


# ---------------------------------------------------------------------------
# 7. cp=1 (the maximum allowed complexity parameter): no split can ever
#    improve the tree enough to be kept, even on perfectly separable data.
# ---------------------------------------------------------------------------

def test_rpart_cp_equal_to_one_forces_no_splits_matches_r():
    n = 20
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": [1.0] * 10 + [20.0] * 10})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(cp=1, xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"cp": 1, "xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"])


# ---------------------------------------------------------------------------
# 8. maxdepth=1 (the minimum depth that still allows one split): exactly
#    one split is permitted, regardless of how separable the data is.
# ---------------------------------------------------------------------------

def test_rpart_maxdepth_one_matches_r():
    n = 20
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": [1.0] * 10 + [20.0] * 10})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(maxdepth=1, xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"maxdepth": 1, "xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"]
    assert len(py_fit["frame"]) == 3  # one internal split + two leaves
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])


# ---------------------------------------------------------------------------
# 9. minsplit larger than the number of observations: no node ever
#    qualifies to be split.
# ---------------------------------------------------------------------------

def test_rpart_minsplit_larger_than_n_matches_r():
    n = 20
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": [1.0] * 10 + [20.0] * 10})
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("y ~ x", control="rpart.control(minsplit=100, xval=0)")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, method="anova", control={"minsplit": 100, "xval": 0})

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"])


# ---------------------------------------------------------------------------
# 10. All-zero case weights: every node's weighted deviance/mean becomes
#     NaN (division by a zero total weight) in both implementations.
# ---------------------------------------------------------------------------

def test_rpart_all_zero_weights_matches_r():
    n = 10
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": np.arange(1, n + 1, dtype=float)})
    r_dataframe_assign("df", df)
    run_r(f"w <- rep(0, {n})")
    r_fit = run_r('rpart(y ~ x, data=df, weights=w, method="anova", control=rpart.control(xval=0))')
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, weights=np.zeros(n), method="anova", control={"xval": 0})

    assert_allclose(py_fit["frame"]["wt"].to_numpy(), r_out["wt"])
    # Both R and Python produce NaN dev/yval here; assert_allclose's
    # equal_nan default (True) treats matching NaNs as equal.
    assert_allclose(py_fit["frame"]["dev"].to_numpy(), r_out["dev"], equal_nan=True)
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"], equal_nan=True)


# ---------------------------------------------------------------------------
# 11. subset selecting a single observation.
# ---------------------------------------------------------------------------

def test_rpart_subset_single_row_matches_r():
    n = 10
    df = pd.DataFrame({"x": np.arange(1, n + 1, dtype=float), "y": np.arange(1, n + 1, dtype=float)})
    r_dataframe_assign("df", df)
    run_r("subv <- c(3)")  # 1-based: 3rd row
    r_fit = run_r("rpart(y ~ x, data=df, subset=subv, control=rpart.control(xval=0))")
    r_out = extract_r_fit(r_fit)

    py_fit = rpart("y ~ x", data=df, subset=np.array([2]), method="anova", control={"xval": 0})  # 0-based: 3rd row

    assert py_fit["frame"]["var"].tolist() == r_out["var"] == ["<leaf>"]
    assert_allclose(py_fit["frame"]["n"].to_numpy(), r_out["n"])
    assert_allclose(py_fit["frame"]["yval"].to_numpy(), r_out["yval"])

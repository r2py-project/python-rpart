"""Boundary/edge-case parity tests for r2py_rpart.na_rpart vs. R's
rpart:::na.rpart.

These exercise functional extremes: a 0-row frame, a 0-column frame,
singleton (1-row) frames, `Inf`/`-Inf` (which `is.na()` does NOT treat as
missing, unlike `NaN`), a negative `response` column index (an
undocumented but well-defined R indexing quirk), the `response=0`
"no-response" path expressed two different ways, and the exact shape of
the attached `na.action` metadata.

Two of these tests document *known, currently-real* R/python divergences
uncovered while writing this suite -- written, per this project's
established convention (see test_rpart_control_edge.py /
test_rpart_negative.py's "known divergence" tests), to assert the actual
observed behavior of both implementations (with a docstring explaining the
root cause) rather than a false parity claim:

  - a bare numeric matrix (no `terms` attribute at all) is a perfectly
    legitimate `x` for R's na.rpart (`ncol()` is well-defined for a
    matrix) but has no direct pandas equivalent that r2py_rpart.na_rpart()
    accepts (it unconditionally calls `.attrs.get(...)`, which only a
    pandas object has);
  - a matrix-*valued* response column (as produced by `Surv()` for
    survival trees) exercises na.rpart.R's `is.matrix(ymiss)` branch on
    the R side, but r2py_rpart.na_rpart() always selects the response via
    `x.iloc[:, yvar - 1]`, which -- for any genuine `pandas.DataFrame` --
    can only ever return a 1-D `Series`, never a 2-D "matrix" value; that
    branch is therefore permanently unreachable in the python
    implementation, since pandas has no notion of a single matrix-valued
    column the way R's `data.frame` does.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from r2py_rpart.na_rpart import na_rpart

from _r_rpart_helpers import (
    r_na_action_to_dict,
    r_na_rpart_result,
    run_r,
    with_response_attr,
)


def _assert_matches_r(df: pd.DataFrame, yvar: int | None) -> None:
    r_out, r_na_action = r_na_rpart_result(df, yvar)
    py_out = na_rpart(with_response_attr(df, yvar))

    assert_frame_equal(
        py_out.reset_index(drop=True),
        r_out[py_out.columns].reset_index(drop=True),
        check_dtype=False,
    )
    assert py_out.attrs.get("na.action") == r_na_action


# ---------------------------------------------------------------------------
# 1. A 0-row frame: `keep` is a length-0 boolean vector; `all(keep)` is
#    (vacuously) TRUE in R, and pandas' `.all()` on an empty Series is
#    likewise True -- so the frame is returned unchanged, no na.action.
# ---------------------------------------------------------------------------

def test_na_rpart_zero_rows_returns_unchanged():
    df = pd.DataFrame({"y": pd.Series([], dtype=float), "x1": pd.Series([], dtype=float)})
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 0
    assert py_out.attrs.get("na.action") is None


# ---------------------------------------------------------------------------
# 2. A 0-column frame with rows and no `terms` attribute (yvar=0): every
#    row has `ncol(xmiss) == 0`, so `0 < 0` is FALSE for every row -- ALL
#    rows are dropped, even though none of them contain any (column)
#    value at all to be "missing".
# ---------------------------------------------------------------------------

def test_na_rpart_zero_columns_drops_all_rows():
    df = pd.DataFrame(index=[0, 1, 2])
    assert df.shape == (3, 0)

    # rpy2's pandas2ri round trip collapses a 0-COLUMN pandas DataFrame's
    # row index to 0 rows too (there are no columns left to carry the
    # index through the conversion) -- so the row count must be built
    # directly on the R side (mirroring `data.frame(row.names=c(...))`)
    # rather than via r_na_rpart_result()'s normal to_r_dataframe() path,
    # to actually exercise R's genuine 3-row/0-column na.rpart behavior.
    run_r('x <- data.frame(row.names = c("0", "1", "2"))')
    assert tuple(int(v) for v in run_r("dim(x)")) == (3, 0)
    r_na_action = r_na_action_to_dict(run_r('attr(rpart:::na.rpart(x), "na.action")'))

    py_out = na_rpart(with_response_attr(df, None))

    assert tuple(int(v) for v in run_r("dim(rpart:::na.rpart(x))")) == (0, 0)
    assert py_out.shape == (0, 0)
    assert py_out.attrs["na.action"] == r_na_action
    assert py_out.attrs["na.action"]["indices"] == [1, 2, 3]
    assert py_out.attrs["na.action"]["names"] == ["0", "1", "2"]


# ---------------------------------------------------------------------------
# 3. Singleton (1-row) frame, entirely missing: dropped -> 0-row result,
#    with na.action naming that single original row.
# ---------------------------------------------------------------------------

def test_na_rpart_single_row_all_missing_dropped():
    df = pd.DataFrame({"y": [np.nan], "x1": [np.nan]})
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 0
    assert py_out.attrs["na.action"]["indices"] == [1]
    assert py_out.attrs["na.action"]["names"] == ["0"]


# ---------------------------------------------------------------------------
# 4. Singleton (1-row) frame, entirely present: kept unchanged.
# ---------------------------------------------------------------------------

def test_na_rpart_single_row_all_present_kept():
    df = pd.DataFrame({"y": [1.0], "x1": [2.0]})
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 1
    assert py_out.attrs.get("na.action") is None


# ---------------------------------------------------------------------------
# 5. `Inf`/`-Inf` values are NOT missing (`is.na(Inf)` is FALSE in R, and
#    `pandas.isna(np.inf)` is likewise False) -- a response of Inf/-Inf
#    does not trigger a drop.
# ---------------------------------------------------------------------------

def test_na_rpart_inf_values_not_treated_as_missing():
    df = pd.DataFrame({"y": [1.0, np.inf, -np.inf], "x1": [1.0, 2.0, 3.0]})
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    assert len(py_out) == 3
    assert py_out.attrs.get("na.action") is None


# ---------------------------------------------------------------------------
# 6. A negative `response` index -- an undocumented, essentially
#    accidental R indexing quirk (`x[-yvar]` with `yvar=-1` becomes
#    `x[1]`, i.e. "keep only column 1"; `x[[yvar]]` with `yvar=-1` also
#    resolves to column 1) rather than a runtime error. r2py_rpart.na_rpart
#    mirrors this exactly via plain python negative-index semantics
#    (`x.columns[yvar - 1]` / `x.iloc[:, yvar - 1]` with `yvar - 1 == -2`
#    also resolving to column 0 on a 2-column frame) -- confirmed to
#    genuinely agree with R here (not merely "both do something"), so this
#    is asserted as a real parity case, not a documented divergence.
# ---------------------------------------------------------------------------

def test_na_rpart_negative_response_index_matches_r_quirk():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0], "x1": [1.0, np.nan, 3.0]})
    _assert_matches_r(df, -1)

    py_out = na_rpart(with_response_attr(df, -1))
    # x.columns[-2] == "y" (dropped from xmiss), x.iloc[:, -2] == "y" (used
    # as ymiss) -- so only x1's own NaN (row 1) drives the drop.
    assert py_out.attrs["na.action"]["indices"] == [2]
    assert py_out.attrs["na.action"]["names"] == ["1"]


# ---------------------------------------------------------------------------
# 7. response=0 expressed two different ways -- omitting the `terms`
#    attribute entirely (na_rpart's own `yvar = 0` fallback) vs. an
#    explicit `{'response': 0}` terms dict -- must behave identically.
# ---------------------------------------------------------------------------

def test_na_rpart_explicit_response_zero_matches_omitted_terms():
    df = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [1.0, np.nan, np.nan]})

    out_omitted = na_rpart(with_response_attr(df, None))
    out_explicit_zero = na_rpart(with_response_attr(df, 0))

    assert_frame_equal(out_omitted, out_explicit_zero)
    assert out_omitted.attrs.get("na.action") == out_explicit_zero.attrs.get("na.action")

    # And both agree with R's own yvar=0 fallback (no terms attr at all).
    _assert_matches_r(df, None)


# ---------------------------------------------------------------------------
# 8. Exact shape/contents of the attached na.action metadata: 1-based
#    dropped positions, original row labels as the "names", and the
#    literal ("na.rpart", "omit") class tuple -- checked explicitly rather
#    than only implicitly via dict equality in the other tests.
# ---------------------------------------------------------------------------

def test_na_rpart_na_action_metadata_shape():
    df = pd.DataFrame(
        {"y": [1.0, np.nan, 3.0, 4.0], "x1": [1.0, 2.0, 3.0, 4.0]},
        index=["r0", "r1", "r2", "r3"],
    )
    _assert_matches_r(df, 1)

    py_out = na_rpart(with_response_attr(df, 1))
    na_action = py_out.attrs["na.action"]
    assert na_action["indices"] == [2]
    assert na_action["names"] == ["r1"]
    assert na_action["class"] == ("na.rpart", "omit")


# ---------------------------------------------------------------------------
# 9. KNOWN DIVERGENCE: a bare numeric matrix with no `terms` attribute at
#    all. R's na.rpart accepts any matrix-like `x` (`ncol()` is
#    well-defined for a matrix, so `is.na(x) %*% rep(1, ncol(xmiss)) <
#    ncol(xmiss)` runs fine) and drops only the fully-missing row.
#    r2py_rpart.na_rpart(), however, unconditionally calls `x.attrs.get(
#    "terms")` as its very first step -- a bare `numpy.ndarray` has no
#    `.attrs` attribute at all, so the python side raises immediately
#    instead of processing the matrix. This is a real, permanent gap (not
#    a documentation/wording nuance): r2py_rpart.na_rpart only ever
#    accepts a pandas.DataFrame, never a bare array-like, matching how it
#    is actually invoked elsewhere in the package (always on a
#    model-frame DataFrame) -- but it is a genuine divergence from R's
#    (looser) na.rpart if that boundary is crossed directly.
# ---------------------------------------------------------------------------

def test_na_rpart_bare_matrix_known_divergence():
    run_r("x <- matrix(c(1, 2, NA, 4, 5, 6), nrow = 3, ncol = 2)")
    r_result = run_r("rpart:::na.rpart(x)")
    # R succeeds, dropping nothing (row 3 has col 2 = 6, not fully missing).
    assert np.asarray(r_result).shape == (3, 2)

    arr = np.array([[1.0, 4.0], [2.0, 5.0], [np.nan, 6.0]])
    with pytest.raises(AttributeError):
        na_rpart(arr)


# ---------------------------------------------------------------------------
# 10. KNOWN GAP: a matrix-valued ("Surv"-style) response column exercises
#     na.rpart.R's `is.matrix(ymiss)` branch on the R side, but has no
#     representable python-side analogue via r2py_rpart.na_rpart() -- see
#     module docstring. This test documents R's actual behavior on such an
#     input (for the record) and confirms there is no equivalent
#     `pandas.DataFrame` construction that reaches the analogous branch in
#     the python implementation (`isinstance(ymiss, pd.DataFrame)` in
#     na_rpart.py can never be True for a single `.iloc[:, k]` column
#     selection).
# ---------------------------------------------------------------------------

def test_na_rpart_matrix_valued_response_known_gap():
    run_r(
        """
        library(survival)
        df <- data.frame(x1 = c(1, NA, 3, 4))
        df <- cbind(data.frame(y = I(Surv(c(1, 2, NA, 4), c(1, 0, 1, 1)))), df)
        Terms <- 1; attr(Terms, "response") <- 1L; attr(df, "terms") <- Terms
        """
    )
    assert bool(run_r("is.matrix(df[[1]])")[0])
    r_result = run_r("rpart:::na.rpart(df)")
    # R drops row 2 (y$time is NA) and row 3 (x1 is the only predictor and
    # it is NA) -- rows 1 and 4 survive.
    r_na_action = run_r('attr(rpart:::na.rpart(df), "na.action")')
    assert list(r_na_action) == [2, 3]

    # No pandas.DataFrame column can itself be a 2-D matrix the way R's
    # `I(Surv(...))` column is -- there is no python-side call that
    # exercises na_rpart.py's `isinstance(ymiss, pd.DataFrame)` branch via
    # a genuine single-column `.iloc[:, yvar - 1]` selection.
    df_py = pd.DataFrame({"y": [1.0, 2.0, np.nan, 4.0], "x1": [1.0, np.nan, 3.0, 4.0]})
    ymiss = df_py.iloc[:, 0].isna()
    assert not isinstance(ymiss, pd.DataFrame)

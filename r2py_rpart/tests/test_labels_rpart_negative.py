"""Negative-path parity tests for r2py_rpart.labels_rpart vs. R's
`labels.rpart`.

Unlike print.rpart/plot.rpart/text.rpart, `labels.rpart` has no
`inherits(object, "rpart")` legitimacy check of its own -- its body simply
does `ff <- object$frame` directly (see
`/groups/jli9/Yufei/python-rpart/rpart/R/labels.rpart.R`), exactly
mirroring r2py_rpart's `labels_rpart()`, which likewise has no class check
and simply does `ff = object['frame']`. So every malformed-`object` test
below calls `rpart:::labels.rpart(...)` *directly* (`generic=False` in
`_r_rpart_helpers.py`'s `r_labels_error()`/`r_labels_result()`), bypassing
the `labels()` S3 generic's own dispatch-by-class behavior -- confirmed
empirically that the generic route sidesteps labels.rpart's body entirely
for an unclassed `x` (`labels(NULL)` returns `character(0)`, `labels(5)`
returns `"1"`, neither of which error) -- exactly the same convention
`test_text_rpart_negative.py`/`test_print_rpart_negative.py` already
established for their own S3-method subjects.

Section 1 covers scenarios where **both** implementations demonstrably
raise (R via `rpart:::labels.rpart(...)`, python via
`r2py_rpart.labels_rpart(...)`), using
`assert_python_and_r_errors_agree()` to *warn* (rather than fail) on any
wording mismatch, per this test-generation task's negative-test protocol.

Section 2 documents four **permanent, confirmed** one-sided-raise gaps
(R's `$`/attribute access degrades gracefully to `NULL`/empty-vector
semantics for a handful of missing pieces that python's dict/DataFrame
column indexing instead raises `KeyError` for immediately, plus one
argument-type-coercion difference for `collapse=`) -- each documented
by a dedicated test that pins the *actual* (asymmetric) behavior on each
side, mirroring this test suite's established convention for other
functions' known, permanent parity gaps (e.g.
test_text_rpart_positive.py's `fancy=True` split-edge-label bug,
test_printcp_positive.py's cp-table print-format gap).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart
from r2py_rpart.labels_rpart import labels_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    cu_summary_df,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_labels_error,
    r_labels_result,
    run_r,
)


def _kyphosis_fits():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    return fit, r_fit


def _cu_summary_fits():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", method='"class"')
    fit = rpart("Reliability ~ Price + Country + Mileage + Type", data=df, method="class")
    return fit, r_fit


# ---------------------------------------------------------------------------
# Section 1: genuine both-sides-raise parity.
# ---------------------------------------------------------------------------

def test_labels_rpart_object_none_raises():
    r_msg = r_labels_error("NULL", generic=False)
    with pytest.raises(Exception) as exc_info:
        labels_rpart(None)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="object=None")


def test_labels_rpart_object_empty_dict_raises():
    r_msg = r_labels_error("list()", generic=False)
    with pytest.raises(Exception) as exc_info:
        labels_rpart({})
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="object={}")


def test_labels_rpart_object_scalar_int_raises():
    r_msg = r_labels_error("5", generic=False)
    with pytest.raises(Exception) as exc_info:
        labels_rpart(5)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="object=5")


def test_labels_rpart_object_string_raises():
    r_msg = r_labels_error('"abc"', generic=False)
    with pytest.raises(Exception) as exc_info:
        labels_rpart("abc")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='object="abc"')


def test_labels_rpart_missing_object_argument_raises():
    """Neither side supplies any default for the first (`object`)
    argument -- calling with zero arguments must raise on both sides."""
    r_msg = r_error_message(lambda: run_r("rpart:::labels.rpart()"))
    with pytest.raises(TypeError) as exc_info:
        labels_rpart()  # type: ignore[call-arg]
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="object omitted entirely")


def test_labels_rpart_minlength_non_numeric_string_raises():
    """minlength="abc" on a fit with an actual categorical (`ncat > 1L`)
    split: R's `abbreviate(..., "abc")` raises "invalid 'minlength'
    argument"; python's `elif minlength > 1:` comparison (`"abc" > 1`)
    raises TypeError -- both raise, for different underlying reasons."""
    fit, r_fit = _cu_summary_fits()
    import rpy2.robjects as ro

    ro.globalenv["cu_fit_tmp"] = r_fit
    r_msg = r_error_message(lambda: run_r('rpart:::labels.rpart(cu_fit_tmp, minlength="abc")'))
    with pytest.raises(TypeError) as exc_info:
        labels_rpart(fit, minlength="abc")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='minlength="abc"')


def test_labels_rpart_non_numeric_splits_column_raises_with_matching_message():
    """A non-numeric (character) `splits` matrix reaches `formatg()`'s own
    explicit `stop("'x' must be a numeric vector")` guard on both sides --
    the one case in this whole test suite where the *exact* error message
    text is expected to match verbatim (not just warned-on-mismatch),
    since r2py_rpart.formatg()'s message is a direct, deliberate copy of
    rpart's own formatg.R string."""
    r_code = """
    frame_tmp <- data.frame(var = c("X", "<leaf>", "<leaf>"),
                             ncompete = c(0, 0, 0), nsurrogate = c(0, 0, 0),
                             row.names = c("1", "2", "3"), stringsAsFactors = FALSE)
    splits_tmp <- matrix(as.character(c(0, 1, 0, 5, 0)), nrow = 1, ncol = 5)
    nonnumeric_splits_obj_tmp <- list(frame = frame_tmp, splits = splits_tmp)
    nonnumeric_splits_obj_tmp
    """
    run_r(r_code)
    r_msg = r_labels_error("nonnumeric_splits_obj_tmp", generic=False)
    assert r_msg is not None
    assert "'x' must be a numeric vector" in r_msg

    frame = pd.DataFrame(
        {"var": ["X", "<leaf>", "<leaf>"], "ncompete": [0, 0, 0], "nsurrogate": [0, 0, 0]},
        index=[1, 2, 3],
    )
    splits = np.array([["0", "1", "0", "5", "0"]])
    with pytest.raises(TypeError) as exc_info:
        labels_rpart({"frame": frame, "splits": splits})
    assert str(exc_info.value) == "'x' must be a numeric vector"


# ---------------------------------------------------------------------------
# Section 2: documented, permanent one-sided-raise / behavior gaps.
#
# In every case below, R's `object$frame`/`attr(object, "xlevels")`-style
# access degrades gracefully (missing pieces read as NULL, and R's
# NULL-tolerant vector/list arithmetic and indexing silently propagate that
# into an empty-but-valid result) where python's dict/DataFrame column
# indexing raises `KeyError` immediately -- these are genuine, structural
# differences between R's `$`/`attr()` semantics and python's `dict`/
# pandas indexing, not incidental bugs specific to one test input.
# ---------------------------------------------------------------------------

def test_labels_rpart_missing_splits_key_is_a_known_gap():
    """KNOWN GAP: with no `splits` element at all, R's `object$splits`
    reads as NULL; `NULL[irow, 2L]` is itself NULL (R never errors
    subsetting NULL), so `ncat` becomes NULL, both `any(ncat < 2L)`/
    `any(ncat > 1L)` are FALSE, and labels.rpart falls through to
    unadorned `varname[parent]` labels (e.g. "X", not "X>=5"). Python's
    `splits_arr = np.asarray(object['splits'])` instead raises `KeyError`
    immediately -- there is no equivalent NULL-propagation path."""
    r_code = """
    frame_tmp2 <- data.frame(var = c("X", "<leaf>", "<leaf>"),
                              ncompete = c(0, 0, 0), nsurrogate = c(0, 0, 0),
                              row.names = c("1", "2", "3"), stringsAsFactors = FALSE)
    missing_splits_obj_tmp <- list(frame = frame_tmp2)
    missing_splits_obj_tmp
    """
    run_r(r_code)
    r_result = r_labels_result("missing_splits_obj_tmp", generic=False)
    assert list(r_result) == ["root", "X", "X"]  # R: no error, degenerate labels

    frame = pd.DataFrame(
        {"var": ["X", "<leaf>", "<leaf>"], "ncompete": [0, 0, 0], "nsurrogate": [0, 0, 0]},
        index=[1, 2, 3],
    )
    with pytest.raises(KeyError):
        labels_rpart({"frame": frame})  # python: raises


def test_labels_rpart_missing_ncompete_nsurrogate_columns_is_a_known_gap():
    """KNOWN GAP: with `ncompete`/`nsurrogate` columns absent from
    `frame`, R's `ff$ncompete`/`ff$nsurrogate` read as NULL, and
    `ncompete + nsurrogate + !is.leaf` propagates that into a length-0
    intermediate -- R still resolves a (degenerate) result without
    erroring. Python's `ff['ncompete'].values` instead raises `KeyError`
    for the missing DataFrame column immediately."""
    r_code = """
    frame_tmp3 <- data.frame(var = c("X", "<leaf>", "<leaf>"),
                              row.names = c("1", "2", "3"), stringsAsFactors = FALSE)
    splits_tmp3 <- matrix(c(0, 1, 0, 5, 0), nrow = 1, ncol = 5)
    missing_cols_obj_tmp <- list(frame = frame_tmp3, splits = splits_tmp3)
    missing_cols_obj_tmp
    """
    run_r(r_code)
    r_result = r_labels_result("missing_cols_obj_tmp", generic=False)
    assert list(r_result) == ["root", "X>=5", "X< 5"]  # R: no error

    frame = pd.DataFrame({"var": ["X", "<leaf>", "<leaf>"]}, index=[1, 2, 3])
    splits = np.zeros((1, 5))
    splits[0, 1] = 1
    splits[0, 3] = 5.0
    with pytest.raises(KeyError):
        labels_rpart({"frame": frame, "splits": splits})  # python: raises


def test_labels_rpart_missing_xlevels_attr_is_a_known_gap():
    """KNOWN GAP: with a categorical (`ncat > 1L`) split but no `xlevels`
    attribute at all, R's `attr(object, "xlevels")` reads as NULL;
    `xlevels[[cindex[i]]]` on a list built from NULL resolves to NULL
    (list-indexing by an out-of-range/NA position returns NULL rather than
    erroring), so the level-set label degrades to an empty string ("X=",
    not "X=<levels>"). Python's `xlevels = object['_xlevels']` instead
    raises `KeyError` immediately."""
    r_code = """
    frame_tmp4 <- data.frame(var = c("X", "<leaf>", "<leaf>"),
                              ncompete = c(0, 0, 0), nsurrogate = c(0, 0, 0),
                              row.names = c("1", "2", "3"), stringsAsFactors = FALSE)
    splits_tmp4 <- matrix(c(0, 5, 0, 1, 0), nrow = 1, ncol = 5)
    csplit_tmp4 <- matrix(c(1, 1, 3, 3, 3), nrow = 1, ncol = 5)
    missing_xlevels_obj_tmp <- list(frame = frame_tmp4, splits = splits_tmp4, csplit = csplit_tmp4)
    missing_xlevels_obj_tmp
    """
    run_r(r_code)
    r_result = r_labels_result("missing_xlevels_obj_tmp", generic=False)
    assert list(r_result) == ["root", "X=", "X="]  # R: no error, empty level-set

    frame = pd.DataFrame(
        {"var": ["X", "<leaf>", "<leaf>"], "ncompete": [0, 0, 0], "nsurrogate": [0, 0, 0]},
        index=[1, 2, 3],
    )
    splits = np.zeros((1, 5))
    splits[0, 1] = 5
    splits[0, 3] = 1
    csplit = np.array([[1, 1, 3, 3, 3]])
    with pytest.raises(KeyError):
        labels_rpart({"frame": frame, "splits": splits, "csplit": csplit})  # python: raises


def test_labels_rpart_non_bool_collapse_is_a_known_gap():
    """KNOWN GAP: `collapse="yes"` (a non-empty, "truthy" string). R's
    `if (!collapse)` applies `!` to a character vector, which raises
    "invalid argument type" -- R has no implicit character-to-logical
    coercion for `!`. Python's `if not collapse:` instead evaluates
    `not "yes"` as plain truthiness (`False`, since a non-empty string is
    truthy) and proceeds normally, silently treating any non-empty string
    the same as `collapse=True`."""
    fit, r_fit = _kyphosis_fits()
    import rpy2.robjects as ro

    ro.globalenv["kyphosis_fit_tmp"] = r_fit
    r_msg = r_error_message(lambda: run_r('rpart:::labels.rpart(kyphosis_fit_tmp, collapse="yes")'))
    assert r_msg is not None
    assert "invalid argument type" in r_msg  # R: raises

    py_result = labels_rpart(fit, collapse="yes")  # python: does NOT raise
    assert py_result == labels_rpart(fit, collapse=True)

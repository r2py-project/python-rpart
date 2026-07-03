"""Negative-path parity tests for r2py_rpart.xpred_rpart vs. R's
xpred.rpart (called directly via rpy2 -- see _r_rpart_helpers.py's
xpred.rpart-specific plumbing section, and test_xpred_rpart_positive.py's
module docstring for why it, like this suite, always calls xpred.rpart
directly rather than through any generic).

Every scenario below was confirmed, via a live rpy2 session, to make *both*
sides raise before being included here (per this test-suite generation
protocol's "both sides must raise" pass condition for a negative test); the
Python-vs-R error *text* is compared only loosely
(`assert_python_and_r_errors_agree` warns rather than fails on a wording
mismatch, since error-message text is not part of rpart's documented
contract).

A GENUINE SEGFAULT, found empirically and deliberately NOT turned into a
test: `xpred.rpart(fit, cp=NULL)` (i.e. an *explicit*, non-missing NULL
`cp=` argument -- as opposed to simply omitting `cp` altogether, which is
the well-behaved, extensively covered-elsewhere default path) crashes R's
own C `xpred` routine outright (observed as a hard process segfault, not a
catchable R error) on this build of rpart's C sources, apparently from
`length(cp) == 0` reaching a buffer computation in xpred.c unguarded for
that case. Since that crash kills the whole test process rather than
merely failing an assertion, no test here (or anywhere in this suite)
exercises `cp=NULL` explicitly; this is recorded here for anyone tempted to
add such a test in the future.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing
(`r_xpred_error`, `assert_python_and_r_errors_agree`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart, xpred_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    mtcars_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_xpred_error,
    run_r,
)


def _valid_fit_pair() -> tuple[dict, object]:
    """Build a matching valid (python fit, R fit) pair, shared by several
    negative tests below that need a legitimate `fit` to then corrupt/probe
    around (e.g. wrong-length `xval`, an unmatched `method`). The R fit is
    also bound into R's globalenv as `xpred_neg_fit_tmp`, so subsequent
    R-source snippets (e.g. `xpred.rpart(xpred_neg_fit_tmp, xval=1:5)`) can
    reference it directly."""
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0)")
    ro.globalenv["xpred_neg_fit_tmp"] = r_fit
    py_fit = rpart("mpg ~ wt + hp", data=df, x=True, control={"xval": 0})
    return py_fit, r_fit


# ---------------------------------------------------------------------------
# 1-6. `fit` is not a legitimate "rpart" object: R's `!inherits(fit,
#      "rpart")` vs. python's `not (isinstance(fit, dict) and
#      fit.get('_rpart_class') == 'rpart')` -- both raise the identical
#      "Invalid fit object" text for every one of these variants.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "r_expr, py_value",
    [
        ("NULL", None),
        ("list()", {}),
        ("5", 5),
        ('"hello"', "hello"),
        ("1:3", [1, 2, 3]),
        ("data.frame(x=1:3)", pd.DataFrame({"x": [1, 2, 3]})),
    ],
    ids=["null", "empty_list", "numeric_scalar", "string", "integer_vector", "dataframe"],
)
def test_xpred_rpart_invalid_fit_object_matches_r(r_expr, py_value):
    r_msg = r_xpred_error(r_expr)
    with pytest.raises(Exception) as exc_info:
        xpred_rpart(py_value)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context=f"invalid fit: {r_expr}")


def test_xpred_rpart_valid_dict_missing_rpart_class_marker_matches_r():
    """A plain dict with rpart-like keys but no `_rpart_class` marker (the
    python-side stand-in for an R object with no "rpart" S3 class
    attribute) must still be rejected."""
    py_fit, _ = _valid_fit_pair()
    fake = dict(py_fit)
    del fake["_rpart_class"]

    r_msg = r_xpred_error('structure(list(), class="notrpart")')
    with pytest.raises(Exception) as exc_info:
        xpred_rpart(fake)
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_msg, context="dict without _rpart_class marker"
    )


# ---------------------------------------------------------------------------
# 7-9. `xval` given as an explicit vector of the wrong length (and no
#      `na.action` to reconcile it against) -> "Wrong length for 'xval'" on
#      both sides.
# ---------------------------------------------------------------------------

def test_xpred_rpart_xval_vector_too_short_matches_r():
    py_fit, _ = _valid_fit_pair()
    r_msg = r_error_message(lambda: run_r("xpred.rpart(xpred_neg_fit_tmp, xval=1:5)"))

    with pytest.raises(Exception) as exc_info:
        xpred_rpart(py_fit, xval=np.array([1, 2, 3, 4, 5]))
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="xval too short")


def test_xpred_rpart_xval_vector_empty_matches_r():
    py_fit, _ = _valid_fit_pair()
    r_msg = r_error_message(lambda: run_r("xpred.rpart(xpred_neg_fit_tmp, xval=integer(0))"))

    with pytest.raises(Exception) as exc_info:
        xpred_rpart(py_fit, xval=np.array([], dtype=np.int32))
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="xval empty")


def test_xpred_rpart_xval_vector_too_long_matches_r():
    py_fit, _ = _valid_fit_pair()
    n = py_fit["x"].shape[0]
    too_long = np.resize(np.arange(1, 4), n + 5)
    r_msg = r_error_message(
        lambda: run_r(f"xpred.rpart(xpred_neg_fit_tmp, xval=rep(1:3, length.out={n + 5}))")
    )

    with pytest.raises(Exception) as exc_info:
        xpred_rpart(py_fit, xval=too_long)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="xval too long")


# ---------------------------------------------------------------------------
# 10. `fit$method` an unmatched/bogus string: R's `pmatch(method, c("anova",
#     "poisson", "class", "user", "exp"))` returns `NA`, and `if (method.int
#     == 5L)` on an `NA` trips R's "missing value where TRUE/FALSE needed";
#     python's `_pmatch` correspondingly returns `None`, and `int(None)`
#     later raises TypeError. Different exception classes/text, but both
#     genuinely raise.
# ---------------------------------------------------------------------------

def test_xpred_rpart_unmatched_method_string_matches_r():
    py_fit, _ = _valid_fit_pair()
    fake = dict(py_fit)
    fake["method"] = "bogus"

    r_msg = r_error_message(
        lambda: run_r('tmp <- xpred_neg_fit_tmp; tmp$method <- "bogus"; xpred.rpart(tmp)')
    )

    with pytest.raises(Exception) as exc_info:
        xpred_rpart(fake)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="unmatched method string")


# ---------------------------------------------------------------------------
# 11. `fit$method` missing entirely: R's `fit$method` on a list with no
#     "method" element is `NULL`, and `pmatch(NULL, ...)` returns
#     `integer(0)`, so `if (method.int == 5L)` trips "argument is of length
#     zero"; python's `fit['method']` (a required-key dict lookup) raises
#     KeyError immediately instead. Different exception classes/text, but
#     both genuinely raise.
# ---------------------------------------------------------------------------

def test_xpred_rpart_method_key_missing_matches_r():
    py_fit, _ = _valid_fit_pair()
    fake = dict(py_fit)
    del fake["method"]

    r_msg = r_error_message(
        lambda: run_r("tmp2 <- xpred_neg_fit_tmp; tmp2$method <- NULL; xpred.rpart(tmp2)")
    )

    with pytest.raises(Exception) as exc_info:
        xpred_rpart(fake)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="method key missing")


# ---------------------------------------------------------------------------
# 12. Calling xpred_rpart with no arguments at all: python's own
#     "missing 1 required positional argument" TypeError vs. R's "argument
#     'fit' is missing, with no default" -- textually different but both a
#     required-argument error.
# ---------------------------------------------------------------------------

def test_xpred_rpart_missing_required_fit_argument_matches_r():
    r_msg = r_error_message(lambda: run_r("xpred.rpart()"))

    with pytest.raises(TypeError) as exc_info:
        xpred_rpart()
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_msg, context="missing required 'fit' argument"
    )

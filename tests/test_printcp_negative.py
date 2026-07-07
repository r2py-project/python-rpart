"""Negative-path parity tests for r2py_rpart.printcp vs. R's rpart::printcp.

printcp is a plain, *exported* R function (not an S3 generic dispatched away
from itself the way `print()` dispatches to `print.rpart`) -- see NAMESPACE's
`export(..., printcp, ...)`. So, unlike print.rpart's negative tests, a bare
`printcp(x)` call reaches R's `inherits(x, "rpart")` legitimacy check
directly for any `x`, with no `rpart:::` internal-access trick needed (see
tests/_r_rpart_helpers.py's `r_printcp_error`/`r_printcp_call_code`).

Each test triggers an error condition in both R (via rpy2) and Python, and
asserts that *both* raise. If both raise but with differently-worded
messages, `assert_python_and_r_errors_agree` warns rather than fails (error
text is not part of rpart's documented contract) -- see
tests/_r_rpart_helpers.py.

`_rpart_class` sanity check (per this test-generation task's own
instructions): grepping the codebase (`grep -n "_rpart_class" -r
r2py_rpart/r2py_rpart/`) confirms r2py_rpart.rpart()'s own return dict DOES
set `ans["_rpart_class"] = "rpart"` (r2py_rpart/rpart.py, in the `ans`
dict literal just before `rpart()` returns). So printcp.py's
`x.get('_rpart_class') == 'rpart'` check is *not* a blocking bug for genuine
`rpart()` output -- every real fit satisfies it automatically, and none of
the tests below need to work around it. What IS tested here is what happens
when that marker is stripped/never set at all (test 6 below), which is a
*genuine* negative case (an object shaped like an rpart fit, but missing its
class marker) that both R (via `class(fit) <- NULL`) and Python legitimately
reject.

printcp.py's only explicit `raise` is:
  - `x` is not a legitimate "rpart" object (not a dict, or a dict whose
    `_rpart_class` isn't `"rpart"`)                        -> TypeError

The remaining tests below reach implicit raise sites in printcp's own body
(Python's string-formatting mini-language raising ValueError for malformed
`digits=`) which mirror (or, in one KNOWN GAP case, fail to mirror) R's own
`format()`-internal validation of its `digits=` argument -- confirmed
empirically against R via a live rpy2 session before being written up here,
so both sides are known to raise (or, for the one test marked KNOWN GAP
below, known to disagree).
"""
from __future__ import annotations

import pytest

from r2py_rpart import rpart
from r2py_rpart.printcp import printcp

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    from_r_dataframe,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_printcp_error,
    run_r,
)


# ---------------------------------------------------------------------------
# 1-5. `x` is not a legitimate "rpart" object: None, a plain list, a bare
#      string, an empty dict (no `_rpart_class` key), and a plain int.
#      printcp.py's own check (`not isinstance(x, dict) or
#      x.get('_rpart_class') != 'rpart'`) raises TypeError for all of
#      these; R's `inherits(x, "rpart")` check raises the same error for
#      the R-equivalent value in each case (a bare `printcp(...)` call
#      reaches this check directly, since printcp is a plain exported
#      function, not an S3 generic).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_x, r_expr",
    [
        (None, "NULL"),
        ([1, 2, 3], "c(1, 2, 3)"),
        ("hello", '"hello"'),
        ({}, "list()"),
        (5, "5"),
    ],
    ids=["none", "list", "string", "empty_dict", "int"],
)
def test_printcp_invalid_x_raises(bad_x, r_expr):
    with pytest.raises(Exception) as exc_info:
        printcp(bad_x)

    r_message = r_printcp_error(r_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid x={bad_x!r}")


# ---------------------------------------------------------------------------
# 6. A dict carrying all the "real" rpart fit components (frame, method,
#    cptable, ...) but with its `_rpart_class` marker removed -- i.e. an
#    object that "looks like" a legitimate fit but was never actually
#    blessed as one. Both sides reject it: R's equivalent is stripping the
#    "rpart" S3 class attribute via `class(fit) <- NULL` (so
#    `inherits(fit, "rpart")` becomes FALSE despite the list still holding
#    every named component `rpart()` produces), and printcp.py's own
#    `_rpart_class` check catches the python-side analogue directly.
# ---------------------------------------------------------------------------

def test_printcp_valid_looking_dict_missing_rpart_class_marker_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("unclassed_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r("class(unclassed_fit_tmp) <- NULL; printcp(unclassed_fit_tmp)")
    )

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    unclassed = dict(py_fit)
    del unclassed["_rpart_class"]
    with pytest.raises(Exception) as exc_info:
        printcp(unclassed)

    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="valid-looking dict missing _rpart_class"
    )


# ---------------------------------------------------------------------------
# 7. Calling printcp with no arguments at all (`x` missing entirely, not
#    just invalid): Python's ordinary missing-required-positional-argument
#    TypeError vs. R's "argument \"x\" is missing, with no default".
# ---------------------------------------------------------------------------

def test_printcp_missing_required_x_argument_raises():
    r_message = r_error_message(lambda: run_r("printcp()"))

    with pytest.raises(Exception) as exc_info:
        printcp()  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="printcp() with no arguments")


# ---------------------------------------------------------------------------
# 8. `digits="x"` (non-numeric): printcp.py's `format(dev0, f'.{digits}g')`
#    raises `ValueError: Format specifier missing precision` when `digits`
#    can't be interpolated into a valid format-spec. R's
#    `format(frame$dev[1L], digits=digits)` raises "invalid value
#    -2147483648 for 'digits' argument" (R's `as.integer("x")` silently
#    coerces to NA, which internally is the sentinel INT_MIN). Confirmed
#    empirically against a live R session before being written up here.
# ---------------------------------------------------------------------------

def test_printcp_digits_non_numeric_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("printcp_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('printcp(printcp_fit_tmp, digits="x")'))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        printcp(py_fit, digits="x")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='digits="x"')


# ---------------------------------------------------------------------------
# 9. `digits=NaN`: printcp.py's format-spec interpolation similarly raises
#    ValueError (the literal text "nan" can't appear in a '.{}g' precision
#    slot). R's format() raises the same "invalid value ... for 'digits'
#    argument" as the non-numeric case (NA_integer_ after coercion).
#    Confirmed empirically against a live R session first.
# ---------------------------------------------------------------------------

def test_printcp_digits_nan_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("printcp_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("printcp(printcp_fit_tmp, digits=NA)"))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        printcp(py_fit, digits=float("nan"))

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="digits=NaN")


# ---------------------------------------------------------------------------
# 10. `digits=-1` (negative): printcp.py's `f'.{-1}g'` produces the invalid
#     format-spec string `.-1g`, raising ValueError. R's format() raises
#     "invalid value -1 for 'digits' argument" (R requires digits >= 1).
#     Confirmed empirically first.
# ---------------------------------------------------------------------------

def test_printcp_digits_negative_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("printcp_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("printcp(printcp_fit_tmp, digits=-1)"))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        printcp(py_fit, digits=-1)

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="digits=-1")


# ---------------------------------------------------------------------------
# 11. Formerly KNOWN GAP: `digits=0`. R's format() explicitly rejects 0
#     ("invalid value 0 for 'digits' argument" -- R requires digits >= 1).
#     printcp.py used to format via Python's `format(v, '.0g')`, a *valid*
#     format spec (Python's '%g'-style formatting silently treats a
#     requested precision of 0 as 1 significant digit), so printcp.py did
#     NOT raise for digits=0 at all -- it happily printed a (low-precision)
#     cp table. printcp.py now explicitly validates `digits` the way R's
#     format() does (see `_validate_digits` in printcp.py: must coerce to
#     a whole number >= 1), so it raises for digits=0 just like R. The test
#     name is kept as-is (it is the identifier this test suite/tooling
#     tracks it by) even though the gap it documents is fixed.
# ---------------------------------------------------------------------------

def test_printcp_digits_zero_known_gap():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("printcp_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("printcp(printcp_fit_tmp, digits=0)"))
    assert r_message is not None  # sanity: R does raise for digits=0

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_raised = False
    try:
        printcp(py_fit, digits=0)
    except Exception:
        py_raised = True

    # Gap fixed: printcp.py now raises for digits=0, matching R.
    assert py_raised, "printcp.py does not raise for digits=0, unlike R"

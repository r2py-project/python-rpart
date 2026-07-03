"""Negative-path parity tests for r2py_rpart.summary_rpart vs. R's
summary.rpart (rpart:::summary.rpart, called directly rather than through
the S3-dispatched summary() generic -- see summary.rpart.Rd's own note that
it, like print.rpart, "can be invoked by calling summary for an object of
the appropriate class, or directly by calling summary.rpart regardless of
the class of the object", which is exactly what's needed to trigger its
`inherits(object, "rpart")` legitimacy check for objects that carry no
"rpart" class attribute at all; `summary()` would otherwise dispatch those
to summary.default before ever reaching summary.rpart).

Each test triggers an error condition in both R (via rpy2) and Python, and
asserts that *both* raise. If both raise but with differently-worded
messages, `assert_python_and_r_errors_agree` warns rather than fails (error
text is not part of rpart's documented contract) -- see
tests/_r_rpart_helpers.py.

summary_rpart.py's only explicit `raise` is:
  - `object` is not a legitimate "rpart" object (not a dict, or a dict
    lacking a "frame" key)                                  -> ValueError

The remaining regular (non-KNOWN-GAP) tests below reach other, *implicit*
raise sites in summary_rpart's call chain (numpy/python type-coercion
errors triggered by malformed `digits=`/`cp=` arguments, a missing
"functions" key, or an unwritable `file=` path) which mirror R's own
failures for the same malformed inputs -- confirmed empirically against R
via Rscript before being written up here, so both sides are known to raise
(albeit with differently-worded messages in most cases).

KNOWN, PERMANENT BEHAVIORAL GAPS
---------------------------------
Four tests below are marked KNOWN GAP: unlike the formatting-only gaps in
test_summary_rpart_positive.py's module docstring, these are genuine
pass/fail divergences (one side raises, the other side silently succeeds)
-- confirmed empirically via Rscript, following the same convention
test_print_rpart_negative.py/test_printcp_negative.py already established
for their own analogous cases. Each KNOWN GAP assertion is kept in place
(never deleted, watered down, or silently skipped):

  - `test_summary_rpart_digits_zero_known_gap` -- R's `print(x$cptable,
    digits=0)` explicitly rejects digits < 1 ("invalid printing digits 0");
    python's `f'{val:.0g}'` is valid python format syntax (precision 0 is
    silently treated as precision 1), so summary_rpart.py does not raise.
  - `test_summary_rpart_cp_non_numeric_string_known_gap` -- R's `parent.cp >
    cp` coerces the numeric `parent.cp` vector to *character* and does a
    lexicographic comparison against the string `cp` (never raising);
    summary_rpart.py's `ff['complexity'].values > cp` instead asks numpy to
    compare a float64 array against a python `str`, which raises
    UFuncTypeError. (Note this is the *reverse* direction of most KNOWN GAPs
    in this test suite: here it is R, not python, that fails to raise.)
  - `test_summary_rpart_cp_nan_known_gap` -- R's `ff$complexity[i] < cp` (and
    `parent.cp > cp`) with `cp=NA` produces `NA` logical values, and
    `if (NA)` raises "missing value where TRUE/FALSE needed"; python's
    NaN comparisons are simply always `False` (no exception), so
    summary_rpart.py silently proceeds (treating it like `cp=Inf`).
  - `test_summary_rpart_missing_cptable_key_known_gap` -- in R, `bad$cptable
    <- NULL` *removes* the list element entirely, so `x$cptable` afterward
    evaluates to `NULL`, and `print(NULL, digits=digits)` prints the literal
    text "NULL" without error; summary_rpart.py's `x['cptable']` (a plain
    dict subscript) raises `KeyError` for the same "key absent" scenario,
    since python dicts have no `$`-style "return NULL for a missing key"
    fallback.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import pytest

from r2py_rpart import rpart
from r2py_rpart.summary_rpart import summary_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    kyphosis_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_summary_rpart_error,
    run_r,
)


# ---------------------------------------------------------------------------
# 1-5. `object` is not a legitimate "rpart" object: None, a plain list, a
#      bare string, an empty dict (no "frame" key), and a plain int.
#      summary_rpart.py's own check (`not isinstance(object, dict) or
#      "frame" not in object`) raises ValueError for all of these; R's
#      `inherits(object, "rpart")` check (invoked directly via
#      rpart:::summary.rpart, per the module docstring) raises the same
#      "Not a legitimate \"rpart\" object" message for the R-equivalent
#      value in each case -- confirmed the message text itself matches
#      exactly (summary_rpart.py's ValueError text was written to mirror
#      R's stop() message verbatim), so no warning is expected here.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_object, r_expr",
    [
        (None, "NULL"),
        ([1, 2, 3], "c(1, 2, 3)"),
        ("hello", '"hello"'),
        ({}, "list()"),
        (5, "5"),
    ],
    ids=["none", "list", "string", "empty_dict", "int"],
)
def test_summary_rpart_invalid_object_raises(bad_object, r_expr):
    with pytest.raises(Exception) as exc_info:
        summary_rpart(bad_object)

    r_message = r_summary_rpart_error(r_expr)
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context=f"invalid object={bad_object!r}"
    )


# ---------------------------------------------------------------------------
# 6. `digits="x"` (non-numeric): summary_rpart's `f'{val:.{digits}g}'`
#    formatting (used, e.g., for the complexity-param text) raises
#    ValueError ("Format specifier missing precision") the moment a node
#    block is formatted. R's `print(x$cptable, digits="x")` raises "invalid
#    printing digits -2147483648" from inside print.default's own digits
#    validation (coercing the non-numeric digits to NA_integer_ internally)
#    -- earlier in the call, at the cp-table print step, but still before
#    any node output. Both sides raise; message wording differs.
# ---------------------------------------------------------------------------

def test_summary_rpart_digits_non_numeric_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::summary.rpart(summary_fit_tmp, digits="x")'))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        summary_rpart(py_fit, digits="x")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='digits="x"')


# ---------------------------------------------------------------------------
# 7. `digits=-1`: unlike digits=0 (KNOWN GAP below), a *negative* digits
#    value also raises on the python side -- `f'{val:.{-1}g}'` is invalid
#    format-spec syntax (negative precision), raising ValueError ("Format
#    specifier missing precision"). R's `print(x$cptable, digits=-1)`
#    raises "invalid printing digits -1". Both sides raise.
# ---------------------------------------------------------------------------

def test_summary_rpart_digits_negative_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("rpart:::summary.rpart(summary_fit_tmp, digits=-1)"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        summary_rpart(py_fit, digits=-1)

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="digits=-1")


# ---------------------------------------------------------------------------
# 8. `cp=None` (R's `cp=NULL`): R's `ff$complexity[i] < cp` with `cp=NULL`
#    produces `logical(0)` (a zero-length vector), and `if (logical(0))`
#    raises "argument is of length zero" (a different failure mode than the
#    `cp=NA` KNOWN GAP below, which raises "missing value where TRUE/FALSE
#    needed"). python's `ff['complexity'].values[i] < cp` with `cp=None`
#    raises TypeError ("'<' not supported between instances of 'float' and
#    'NoneType'"). Both sides raise; message wording (and underlying
#    mechanism) differs.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_none_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("rpart:::summary.rpart(summary_fit_tmp, cp=NULL)"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        summary_rpart(py_fit, cp=None)

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="cp=None")


# ---------------------------------------------------------------------------
# 9. A "rpart"-classed object missing its `functions` component (the
#    per-method summary/print/text closures normally set by
#    rpart.anova/rpart.class/rpart.poisson/rpart.exp): summary_rpart.py's
#    `x['functions']['summary']` raises KeyError; R's `x$functions$summary`
#    evaluates to `NULL` (no error, since `$` on a missing list element just
#    returns NULL), but then *calling* `NULL(tmp, ...)` raises "attempt to
#    apply non-function". Both sides raise (only after already printing the
#    Call/n=/cptable/Variable-importance sections in both cases); message
#    wording differs.
# ---------------------------------------------------------------------------

def test_summary_rpart_missing_functions_key_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r('bad <- summary_fit_tmp; bad$functions <- NULL; rpart:::summary.rpart(bad)')
    )

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    bad_py_fit = dict(py_fit)
    del bad_py_fit["functions"]
    with pytest.raises(Exception) as exc_info:
        summary_rpart(bad_py_fit)

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="missing 'functions' key")


# ---------------------------------------------------------------------------
# 10. `file=` pointing at a directory that does not exist: R's
#     `sink(file)` raises "cannot open the connection" (the underlying
#     `file(file, ...)` connection fails); python's `open(file, 'w')`
#     raises FileNotFoundError. Both sides raise.
# ---------------------------------------------------------------------------

def test_summary_rpart_file_unwritable_directory_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r('rpart:::summary.rpart(summary_fit_tmp, file="/no/such/directory/out.txt")')
    )

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        summary_rpart(py_fit, file="/no/such/directory/out.txt")

    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="file=<unwritable directory>"
    )


# ---------------------------------------------------------------------------
# 11. KNOWN GAP: `digits=0`. R's `print(x$cptable, digits=0)` explicitly
#     rejects digits < 1 ("invalid printing digits 0"), so summary(fit,
#     digits=0) always raises in R. summary_rpart.py's own digits-driven
#     formatting (`f'{val:.{digits}g}'`) treats a precision of 0 as
#     equivalent to 1 (valid python format-spec syntax), so it does not
#     raise at all -- confirmed empirically (see the module docstring).
#     This assertion is *expected to fail*; kept in place per this test
#     suite's established KNOWN GAP convention.
# ---------------------------------------------------------------------------

def test_summary_rpart_digits_zero_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("rpart:::summary.rpart(summary_fit_tmp, digits=0)"))
    assert r_message is not None and "invalid printing digits" in r_message

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_raised = True
    try:
        summary_rpart(py_fit, digits=0)
        py_raised = False
    except Exception:
        pass

    # KNOWN GAP: expected to fail -- summary_rpart.py does not raise for
    # digits=0, unlike R.
    assert py_raised, "KNOWN GAP: summary_rpart.py does not raise for digits=0, unlike R"


# ---------------------------------------------------------------------------
# 12. KNOWN GAP: `cp="x"` (a non-numeric string). R's `parent.cp > cp`
#     silently coerces the numeric `parent.cp` vector to character and does
#     a (nonsensical, but non-erroring) lexicographic comparison against
#     "x" -- confirmed empirically that R's summary(fit, cp="x") runs to
#     completion, printing just the root node (every numeric-as-character
#     comparison happens to come out False, since digit characters sort
#     below 'x'). summary_rpart.py's `ff['complexity'].values > cp` instead
#     asks numpy to compare a float64 array against a python str directly,
#     which raises numpy.core._exceptions.UFuncTypeError. This is the
#     *reverse* direction from most KNOWN GAPs in this test suite (here R
#     is the side that does NOT raise). Expected to fail; kept in place per
#     convention.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_non_numeric_string_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::summary.rpart(summary_fit_tmp, cp="x")'))
    assert r_message is None  # sanity: R really does not raise here

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_raised = True
    try:
        summary_rpart(py_fit, cp="x")
        py_raised = False
    except Exception:
        pass

    # KNOWN GAP: expected to fail -- python raises for cp="x" where R does not.
    assert not py_raised, 'KNOWN GAP: summary_rpart.py raises for cp="x", unlike R'


# ---------------------------------------------------------------------------
# 13. KNOWN GAP: `cp=NaN` (R's `cp=NA`). R's `ff$complexity[i] < cp`/
#     `parent.cp > cp` comparisons against `NA` produce `NA` logical
#     results, and the subsequent `if (NA)` raises "missing value where
#     TRUE/FALSE needed". python's `nan` comparisons (`x > float('nan')`)
#     are simply always False (no exception raised at all) -- IEEE 754
#     semantics that python's `if` statement never treats as an error the
#     way R's scalar-`if` does for `NA`. summary_rpart.py therefore runs to
#     completion (behaving as if cp were larger than every complexity
#     value, i.e. printing only the root node), unlike R. Expected to fail;
#     kept in place per convention.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_nan_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("rpart:::summary.rpart(summary_fit_tmp, cp=NA)"))
    assert r_message is not None and "missing value" in r_message

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_raised = True
    try:
        summary_rpart(py_fit, cp=float("nan"))
        py_raised = False
    except Exception:
        pass

    # KNOWN GAP: expected to fail -- summary_rpart.py does not raise for
    # cp=NaN, unlike R.
    assert py_raised, "KNOWN GAP: summary_rpart.py does not raise for cp=NaN, unlike R"


# ---------------------------------------------------------------------------
# 14. KNOWN GAP: a "rpart"-classed object with its `cptable` component
#     entirely removed. In R, `bad$cptable <- NULL` deletes the list
#     element, so `x$cptable` afterward evaluates to `NULL` and
#     `print(NULL, digits=digits)` prints the literal text "NULL" without
#     error -- confirmed empirically that R's summary() runs to completion
#     in this scenario. summary_rpart.py's `x['cptable']` is a plain dict
#     subscript with no such "missing key returns None" fallback, so it
#     raises KeyError instead. Expected to fail; kept in place per
#     convention.
# ---------------------------------------------------------------------------

def test_summary_rpart_missing_cptable_key_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("summary_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r("bad <- summary_fit_tmp; bad$cptable <- NULL; rpart:::summary.rpart(bad)")
    )
    assert r_message is None  # sanity: R really does not raise here

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    bad_py_fit = dict(py_fit)
    del bad_py_fit["cptable"]
    py_raised = True
    try:
        summary_rpart(bad_py_fit)
        py_raised = False
    except Exception:
        pass

    # KNOWN GAP: expected to fail -- summary_rpart.py raises KeyError for a
    # missing 'cptable' key, unlike R (which prints "NULL" and continues).
    assert not py_raised, "KNOWN GAP: summary_rpart.py raises for a missing 'cptable' key, unlike R"

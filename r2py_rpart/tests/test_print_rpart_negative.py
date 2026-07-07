"""Negative-path parity tests for r2py_rpart.print_rpart vs. R's
print.rpart (rpart:::print.rpart, called directly rather than through the
S3-dispatched print() generic -- see print.rpart.Rd's own note that
print.rpart "can be invoked ... directly ... regardless of the class of
x", which is exactly what's needed to trigger its `inherits(x, "rpart")`
legitimacy check for objects that carry no "rpart" class attribute at all;
`print()` would otherwise dispatch those to print.default before ever
reaching print.rpart).

Each test triggers an error condition in both R (via rpy2) and Python, and
asserts that *both* raise. If both raise but with differently-worded
messages, `assert_python_and_r_errors_agree` warns rather than fails
(error text is not part of rpart's documented contract) -- see
tests/_r_rpart_helpers.py.

print_rpart.py's only explicit `raise` is:
  - `x` is not a legitimate "rpart" object (not a dict, or a dict lacking
    a "frame" key)                                         -> TypeError

The remaining tests below reach other, *implicit* raise sites in
print_rpart's call chain (numpy/Python type-coercion errors triggered by
malformed `digits=`/`spaces=`/`minlength=` arguments) which mirror R's own
type-coercion failures inside format()/rep()/prune.rpart() for the same
malformed inputs -- confirmed empirically against R via Rscript before
being written up here, so both sides are known to raise (or, for the one
test marked KNOWN GAP below, known to disagree).
"""
from __future__ import annotations

import pytest

from r2py_rpart import print_rpart, rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    capture_print_rpart_lines,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_print_rpart_error,
    r_print_rpart_lines,
    run_r,
)


# ---------------------------------------------------------------------------
# 1-5. `x` is not a legitimate "rpart" object: None, a plain list, a bare
#      string, an empty dict (no "frame" key), and a plain int/float.
#      print_rpart.py's own check (`not isinstance(x, dict) or "frame" not
#      in x`) raises TypeError for all of these; R's `inherits(x,
#      "rpart")` check (invoked directly via rpart:::print.rpart, per the
#      module docstring) raises the same error for the R-equivalent value
#      in each case.
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
def test_print_rpart_invalid_x_raises(bad_x, r_expr):
    with pytest.raises(Exception) as exc_info:
        print_rpart(bad_x)

    r_message = r_print_rpart_error(r_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid x={bad_x!r}")


# ---------------------------------------------------------------------------
# 6. `digits="x"` (non-numeric): print_rpart's `nsmall = min(20, digits)`
#    default-resolution compares an int against a str and raises
#    TypeError before any formatting is attempted. R's
#    `format(signif(frame$dev, digits))` raises "non-numeric argument to
#    mathematical function" inside signif().
# ---------------------------------------------------------------------------

def test_print_rpart_digits_non_numeric_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("print_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::print.rpart(print_fit_tmp, digits="x")'))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        print_rpart(py_fit, digits="x")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='digits="x"')


# ---------------------------------------------------------------------------
# 7. `spaces="x"` (non-numeric): print_rpart's unconditional
#    `' ' * (spaces * 32)` computation raises TypeError ("can't multiply
#    sequence by non-int of type 'str'") since Python's `str * str` isn't
#    defined. R's `rep(" ", spaces * 32L)` raises "non-numeric argument to
#    binary operator" for the same reason (spaces * 32L can't multiply a
#    string by a number).
# ---------------------------------------------------------------------------

def test_print_rpart_spaces_non_numeric_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_assign("print_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::print.rpart(print_fit_tmp, spaces="x")'))

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        print_rpart(py_fit, spaces="x")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='spaces="x"')


# ---------------------------------------------------------------------------
# 8. `minlength="abc"` (non-numeric) on a tree with categorical splits:
#    labels_rpart's `elif minlength > 1:` comparison (str > int) raises
#    TypeError in Python. R's `labels.rpart` raises "invalid 'minlength'
#    argument" from inside its own minlength-driven abbreviate() branch.
#    This branch is only reached when the frame actually has categorical
#    splits (ncat > 1), hence cu.summary's Country/Type factor predictors
#    rather than car.test.frame's purely-numeric Weight.
# ---------------------------------------------------------------------------

def test_print_rpart_minlength_non_numeric_with_categorical_split_raises():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Country + Type", control="rpart.control(xval=0)")
    r_assign("print_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::print.rpart(print_fit_tmp, minlength="abc")'))

    py_fit = rpart("Reliability ~ Country + Type", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        print_rpart(py_fit, minlength="abc")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='minlength="abc"')


# ---------------------------------------------------------------------------
# 9. `nsmall="x"` (non-numeric) on a *classification* tree: rpart_class's
#    print_func computes `max(sig_decimals, nsmall)`, comparing an int
#    against a str, which raises TypeError in Python. R's equivalent
#    `format(yval[...], digits=digits, nsmall=nsmall)` raises "invalid
#    'nsmall' argument". (On an anova/no-tfun tree, nsmall is never used
#    in formatting at all -- confirmed empirically in R, where
#    `print(z, nsmall="x")` raises no error whatsoever for a plain
#    regression tree -- so this must use a classification fit to actually
#    exercise nsmall.)
# ---------------------------------------------------------------------------

def test_print_rpart_nsmall_non_numeric_classification_raises():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("print_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('rpart:::print.rpart(print_fit_tmp, nsmall="x")'))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        print_rpart(py_fit, nsmall="x")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='nsmall="x" (classification)')


# ---------------------------------------------------------------------------
# 10. `cp=[]` (an empty list, R's `cp=list()`). R's `ff$complexity <= cp`
#     with a zero-length `cp` silently produces a zero-length logical
#     result, so `toss` ends up empty and prune.rpart() returns the tree
#     unchanged -- no error, no pruning (confirmed empirically:
#     `print(z, cp=list())` prints the full, unpruned tree). This is
#     therefore NOT an error-raising test at all (despite living in this
#     "negative-path" module): print_rpart.py special-cases an empty `cp`
#     to skip the prune_rpart() call entirely, matching R's silent
#     no-op-pruning behavior instead of letting numpy's broadcast of a
#     length-7 complexity column against a length-0 `cp` raise ValueError.
#     Asserts full line-for-line output parity, like the positive-path
#     tests, rather than the raise/raise agreement the other tests in this
#     module check.
# ---------------------------------------------------------------------------

def test_print_rpart_cp_empty_list_known_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    # cp=[] renders as R's `cp=c()` (i.e. `cp=NULL`), confirmed empirically
    # to print identically to `cp=list()` (both zero-length) -- R doesn't
    # distinguish them here since `missing(cp)` only checks whether the
    # argument was supplied, and `ff$complexity <= cp` broadcasts a
    # zero-length `cp` the same way regardless of its exact empty type.
    r_lines = r_print_rpart_lines(r_fit, cp=[])

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, cp=[])

    assert py_lines == r_lines

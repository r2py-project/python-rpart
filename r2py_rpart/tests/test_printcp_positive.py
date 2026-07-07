"""Positive-path parity tests for r2py_rpart.printcp vs. R's rpart::printcp.

printcp(x, digits=...) is a plain, exported R function (not an S3 generic),
so `printcp(...)` can be called directly on both sides without any
`rpart:::` internal-access trick -- see tests/_r_rpart_helpers.py's
printcp-specific plumbing (`r_printcp_lines_and_result`,
`capture_printcp_lines_and_result`, `r_printcp_error`).

`_rpart_class` sanity check (see the module-level note this test-generation
task was given): r2py_rpart.rpart()'s own return dict DOES set
`ans["_rpart_class"] = "rpart"` (see r2py_rpart/rpart.py's `ans` construction,
just before it returns) -- confirmed by grepping the codebase before writing
any of these tests. So printcp.py's `x.get('_rpart_class') == 'rpart'` check
is *not* a blocking bug for genuine `rpart()` output; every fit built via
`rpart(...)` in these tests satisfies it automatically. (What happens when
that key is stripped/absent is covered instead in
test_printcp_negative.py, since R's own `inherits(x, "rpart")` check would
likewise reject such an object.)

KNOWN, PERMANENT FORMATTING-PARITY GAPS
----------------------------------------
Several of printcp.py's printed lines can never textually match R's
`printcp()` console output, for structural reasons unrelated to any single
test's inputs. Each is documented here once and referenced by number in the
tests below; assertions that hit these gaps are kept as *known-failing*
assertions (never deleted, watered down, or silently skipped), following the
same convention test_print_rpart_edge.py already established for its own
known gaps.

(1) R-call echo. R's `dput(cl, control=NULL)` pretty-prints the actual
    parsed call, e.g. `rpart(formula = Mileage ~ Weight, data = df)`.
    printcp.py instead does `print(repr(cl))` on `x['call']`, which is a
    plain python dict built by r2py_rpart.rpart() (`{"formula": ...,
    "data": <the whole DataFrame>, "weights": ..., "subset": ...}`) -- so
    Python's call-echo line(s) dump the *entire input DataFrame's repr*
    inline inside a dict repr, which will never match R's one-or-two-line
    `dput()` output, for any rpart()-built fit whatsoever. Every test below
    that uses a genuine r2py_rpart.rpart() fit is affected identically, so
    rather than repeat this note per test, all comparisons below explicitly
    skip the call-echo block (the lines between the method header and
    either "Variables actually used..." or "Root node error:") and instead
    assert on it directly, once, in
    `test_printcp_call_echo_is_a_known_formatting_gap` below.

(2) "Variables actually used in tree construction:" list formatting.
    printcp.py does `print(sorted(str(v) for v in used))` (a literal python
    list repr, e.g. `['Country', 'Type']`); R does
    `print(sort(as.character(used)), quote=FALSE)` (R's vector-print
    layout, e.g. `[1] Country Type   `, index-prefixed and
    column-aligned). These never match textually. Tests below instead
    compare the *set of variable names* extracted from each side (via
    `_r_rpart_helpers.printcp_vars_used_r`/`printcp_vars_used_py`).

(3) Root-only/no-split tree: R's `used <- unique(frame$var[!leaves])` on a
    root-only frame is `character(0)`, and `is.null(character(0))` is
    FALSE, so R's `if (!is.null(used))` branch still runs, printing
    "Variables actually used in tree construction:" followed by the literal
    text "character(0)". printcp.py's guard is
    `if used is not None and len(used) > 0:`, which is FALSE for an empty
    `used` array -- Python *skips the entire block*. This is a genuine
    behavioral divergence (not just cosmetic), covered by a dedicated
    root-only test in test_printcp_edge.py (KNOWN GAP there).

(4) cp-table numeric formatting/alignment. R's `print(x$cptable,
    digits=digits)` formats the *whole column* together (via `format()`
    applied to the matrix), padding every row in a column to the same
    number of decimal places (driven by whichever row needs the most
    precision to show `digits` significant digits) -- e.g. digits=5 on the
    printcp.Rd worked example prints CP as `0.595349`/`0.134528`/
    `0.012828`/`0.010000`, all 6 decimals, because the smallest value needs
    that many. printcp.py's `cptable.to_string(float_format=lambda v:
    format(v, f'.{digits}g'))` instead formats each value *independently*
    via Python's '%g'-style formatting, with no cross-row decimal
    alignment -- so it instead prints `0.59535`/`0.13453`/`0.012828`/`0.01`,
    a different decimal count per row. This causes a genuine text mismatch
    in the cp-table's printed rows whenever there is more than one row.
    Because of this, none of the positive tests below assert cp-table
    *line* text equality; instead, they assert numeric equality of the
    *returned* cptable value (point 6 below), which is digits-independent
    and unaffected by this formatting gap. A dedicated single-row-cptable
    edge test in test_printcp_edge.py demonstrates this gap doesn't fully
    disappear even with only one row, due to a distinct column-*padding*
    difference between pandas' `to_string()` and R's matrix printer.

(5) `x['cptable']` may be a pandas.DataFrame (r2py_rpart.rpart()'s normal
    output) or, per printcp.py's own fallback `else:` branch, a bare
    numpy.ndarray. `test_printcp_ndarray_cptable_fallback_matches_dataframe_path`
    below exercises that fallback branch directly by mutating a fit's
    `cptable` entry to a raw ndarray and confirming it reproduces the exact
    same output as the DataFrame path.

(6) The "n=" line, in the *no-na.action* branch only. R's
    `cat("n=", n[1L], "\n\n")` uses cat's *default* `sep=" "`, producing
    `"n= 60 \n\n"` (a space after "n=", and a trailing space before the
    blank line). printcp.py's `f'n={n.iloc[0]}'` has neither space, e.g.
    `"n=60"`. (When na.action *is* present, R's other branch explicitly
    passes `sep=""`, and printcp.py's f-string also has no extra spaces
    there -- so that branch matches exactly; only the no-omission branch
    has this gap. Confirmed empirically before writing these tests.)

(7) Default `digits=` value. printcp.py's Python signature hardcodes
    `digits: int = 2`. R's default is `getOption("digits") - 2L`, which in
    a stock R session (`getOption("digits")` == 7) is 5, not 2. Since
    `digits` controls both the "Root node error" line and the entire
    cp-table's precision, calling both sides with their own *implicit*
    defaults produces wildly different output (2 vs. ~6 significant
    digits) -- demonstrated explicitly in
    `test_printcp_default_digits_value_is_a_known_gap` below. All other
    positive tests sidestep this by passing the *same* explicit `digits=`
    value to both sides.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart
from r2py_rpart.printcp import printcp

from _r_rpart_helpers import (
    capture_printcp_lines_and_result,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    printcp_find_line,
    printcp_vars_used_py,
    printcp_vars_used_r,
    r_dataframe_assign,
    r_fit_rpart,
    r_printcp_lines_and_result,
    run_r,
    stagec_df,
)


def _assert_core_lines_match(py_lines: list[str], r_lines: list[str]) -> None:
    """Assert equality of every printcp output line from "Root node error:"
    onward through the "n=" line and its surrounding blank lines (i.e.
    everything *except* the method header/call-echo block above it, gap 1,
    and the cp-table body below it, gap 4) -- the section of printcp's
    output not subject to either permanent formatting gap, given matching
    `digits=` on both sides."""
    py_root = printcp_find_line(py_lines, "Root node error:")
    r_root = printcp_find_line(r_lines, "Root node error:")
    # "Root node error: ..." line, blank line, "n=..." line: 3 lines,
    # identical positions relative to the root-error line on both sides.
    assert py_lines[py_root] == r_lines[r_root]
    assert py_lines[py_root + 1] == r_lines[r_root + 1] == ""
    # The "n=" line itself: gap 6 affects only the no-na.action branch (no
    # parenthetical); when na.action *is* present, this matches exactly.
    py_n_line = py_lines[py_root + 2]
    r_n_line = r_lines[r_root + 2]
    if "deleted due to missingness" in r_n_line:
        assert py_n_line == r_n_line
    else:
        # KNOWN GAP (6): R's default cat(...) sep=" " inserts spaces
        # printcp.py's f-string does not; only the numeric content agrees.
        assert py_n_line.replace(" ", "") == r_n_line.replace(" ", "")


def _assert_vars_used_match_as_sets(py_lines: list[str], r_lines: list[str]) -> None:
    """Known gap (2): raw text never matches, but the same *set* of
    variable names should appear on both sides."""
    py_vars = printcp_vars_used_py(py_lines)
    r_vars = printcp_vars_used_r(r_lines)
    assert r_vars is not None, "R printcp always prints this block (see gap 3)"
    assert py_vars is not None, "expected a non-root-only tree to have used variables"
    assert py_vars == r_vars


def _assert_cptable_values_match(py_retval, r_mat: np.ndarray, r_cols: list[str]) -> None:
    """Independent of any print-formatting gap: the *returned* cptable
    values (point 6 in the module docstring) must agree numerically."""
    if isinstance(py_retval, pd.DataFrame):
        assert list(py_retval.columns) == r_cols
        py_mat = py_retval.to_numpy(dtype=float)
    else:
        py_mat = np.asarray(py_retval, dtype=float)
    assert py_mat.shape == r_mat.shape
    np.testing.assert_allclose(py_mat, r_mat, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 1. printcp.Rd's own worked example (anova/regression tree, car.test.frame
#    Mileage~Weight, xval=0): pins the documented example's exact CP table
#    values (0.595349, 0.134528, 0.012828, 0.010000 for CP; nsplit
#    0,1,2,3; rel error 1.00000, 0.40465, 0.27012, 0.25729) as a regression
#    check, in addition to the general R-vs-python comparison.
# ---------------------------------------------------------------------------

def test_printcp_default_args_matches_r_car_test_frame_anova(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)

    assert py_lines[0] == r_lines[0] == ""
    assert py_lines[1] == r_lines[1] == "Regression tree:"
    _assert_vars_used_match_as_sets(py_lines, r_lines)
    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)

    ## Pin printcp.Rd's own documented worked-example values.
    expected_cp = np.array([0.595349, 0.134528, 0.012828, 0.010000])
    expected_nsplit = np.array([0, 1, 2, 3])
    expected_rel_error = np.array([1.00000, 0.40465, 0.27012, 0.25729])
    np.testing.assert_allclose(r_mat[:, 0], expected_cp, atol=5e-6)
    np.testing.assert_allclose(r_mat[:, 1], expected_nsplit)
    np.testing.assert_allclose(r_mat[:, 2], expected_rel_error, atol=5e-6)
    np.testing.assert_allclose(py_retval["CP"].to_numpy(), expected_cp, atol=5e-6)
    np.testing.assert_allclose(py_retval["rel error"].to_numpy(), expected_rel_error, atol=5e-6)


# ---------------------------------------------------------------------------
# 2. Classification tree (kyphosis, binary response): exercises the
#    "Classification tree:" method header and a categorical-less predictor
#    set (Age/Number/Start are all numeric, so no gap-2-relevant categorical
#    splits are needed to prove the variable-name-set comparison works).
# ---------------------------------------------------------------------------

def test_printcp_classification_kyphosis(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=4)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    assert py_lines[1] == r_lines[1] == "Classification tree:"
    _assert_vars_used_match_as_sets(py_lines, r_lines)
    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)


# ---------------------------------------------------------------------------
# 3. Classification tree with na.action (cu.summary, 5-level ordered
#    factor, NAs in both response and a predictor): exercises the
#    "n=<n> (<k> observations deleted due to missingness)" header line,
#    which -- unlike the no-omission branch (gap 6) -- matches R *exactly*
#    (both sides use sep="" there), asserted explicitly below in addition
#    to the general core-lines helper.
# ---------------------------------------------------------------------------

def test_printcp_na_action_present_cu_summary(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)
    assert "deleted due to missingness" in r_lines[printcp_find_line(r_lines, "n=")]

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)

    py_n_line = py_lines[printcp_find_line(py_lines, "n=")]
    r_n_line = r_lines[printcp_find_line(r_lines, "n=")]
    assert py_n_line == r_n_line == "n=85 (32 observations deleted due to missingness)"

    _assert_vars_used_match_as_sets(py_lines, r_lines)
    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)


# ---------------------------------------------------------------------------
# 4. method="poisson" (Surv()-style two-column response, stagec dataset):
#    exercises the "Rates regression tree:" method header, mirroring the
#    pre-built model-frame pattern used elsewhere in this test suite for
#    poisson/Surv fits.
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


def test_printcp_poisson_method_stagec(capsys):
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=4)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    assert py_lines[1] == r_lines[1] == "Rates regression tree:"
    _assert_vars_used_match_as_sets(py_lines, r_lines)
    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)


# ---------------------------------------------------------------------------
# 5. Non-default `digits=` value (4), on the anova tree -- exercises the
#    "Root node error" line's formatting precision changing with `digits`
#    (rather than always using the default value).
#
#    Note: digits=3 (rather than 4) was tried first and does NOT match --
#    Python's `format(1354.6, '.3g')` switches to scientific notation
#    ("1.35e+03") because '%g'-style formatting switches to scientific
#    whenever the value's decimal exponent >= the requested precision,
#    while R's `format(1354.6, digits=3)` stays in fixed notation ("1355").
#    This is yet another facet of gap (4) (Python's per-value '%g'
#    formatting vs. R's format()) that also affects the "Root node error"
#    line, not just the cp-table body, whenever the value's magnitude is
#    large relative to `digits`. digits=4 avoids the discrepancy for this
#    particular dev0/n0 pair (both sides print "1355"), so it is used here
#    to test the "non-default digits actually changes precision" behavior
#    without simultaneously re-demonstrating the scientific-notation gap.
# ---------------------------------------------------------------------------

def test_printcp_non_default_digits_value(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=4)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)
    root_line = r_lines[printcp_find_line(r_lines, "Root node error:")]
    assert root_line == "Root node error: 1355/60 = 22.58"


# ---------------------------------------------------------------------------
# 6. Formerly KNOWN GAP (7): calling both sides with their own *implicit*
#    digits= default used to demonstrate that printcp.py's hardcoded
#    `digits=2` default did not match R's actual
#    `getOption("digits") - 2L` default (5 in a stock R session).
#    printcp.py's default is now `digits=5` (see printcp.py), matching R's
#    stock-session default exactly, so both the "Root node error" line and
#    the returned numeric default now agree with no explicit `digits=`
#    passed on either side. The test name is kept as-is (it is the
#    identifier this test suite/tooling tracks it by) even though the gap
#    it documents is fixed.
# ---------------------------------------------------------------------------

def test_printcp_default_digits_value_is_a_known_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_digits_default = int(run_r('getOption("digits")')[0]) - 2
    assert r_digits_default == 5  # sanity: stock R session default

    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit)  # digits omitted -> R default
    r_root_line = r_lines[printcp_find_line(r_lines, "Root node error:")]
    assert r_root_line == "Root node error: 1354.6/60 = 22.576"

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit)  # digits omitted -> python default (now 5)
    py_root_line = py_lines[printcp_find_line(py_lines, "Root node error:")]
    assert py_root_line == "Root node error: 1354.6/60 = 22.576"

    # Gap fixed: printcp.py's default digits= now matches R's default.
    assert py_root_line == r_root_line


# ---------------------------------------------------------------------------
# 7. `xval > 0` (5-column cptable, including xerror/xstd) vs. `xval=0`
#    (3-column cptable): CP/nsplit/rel error are deterministic and must
#    match exactly regardless of xval; xerror/xstd are cross-validation
#    statistics driven by independent R-side/python-side random number
#    generators for the fold assignment (xgroups), so they are *not*
#    expected to agree numerically -- only the cptable's *shape* (5
#    columns, one per xval>0 fold-derived statistic) and column names are
#    checked for that part.
# ---------------------------------------------------------------------------

def test_printcp_xval_zero_vs_xval_positive_column_counts(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)

    ## xval=0 -> 3-column cptable (CP, nsplit, rel error).
    r_fit0 = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines0, r_mat0, r_cols0 = r_printcp_lines_and_result(r_fit0, digits=5)
    py_fit0 = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines0, py_retval0 = capture_printcp_lines_and_result(capsys, py_fit0, digits=5)
    assert r_cols0 == ["CP", "nsplit", "rel error"]
    _assert_cptable_values_match(py_retval0, r_mat0, r_cols0)

    ## xval=5 -> 5-column cptable (CP, nsplit, rel error, xerror, xstd).
    run_r("set.seed(42)")
    r_fit5 = r_fit_rpart("Mileage ~ Weight + Price + Country", control="rpart.control(xval=5)")
    r_lines5, r_mat5, r_cols5 = r_printcp_lines_and_result(r_fit5, digits=5)
    np.random.seed(42)
    py_fit5 = rpart(
        "Mileage ~ Weight + Price + Country", data=df, method="anova", control={"xval": 5}
    )
    py_lines5, py_retval5 = capture_printcp_lines_and_result(capsys, py_fit5, digits=5)
    assert r_cols5 == ["CP", "nsplit", "rel error", "xerror", "xstd"]
    assert list(py_retval5.columns) == r_cols5
    assert py_retval5.shape == r_mat5.shape

    ## Deterministic columns (CP, nsplit, rel error) must match exactly;
    ## xerror/xstd depend on independent RNG streams and are not compared.
    py_mat5 = py_retval5.to_numpy(dtype=float)
    np.testing.assert_allclose(py_mat5[:, :3], r_mat5[:, :3], rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 8. Known gap (5)/point 5: the ndarray-cptable fallback branch. printcp.py
#    falls back to building a fresh DataFrame (with generic row/col labels)
#    when `x['cptable']` is a bare numpy.ndarray rather than a
#    pandas.DataFrame. Exercise that branch directly by mutating a
#    genuine fit's `cptable` entry to `.to_numpy()`, and confirm it
#    reproduces byte-identical output (and equal returned values) to the
#    normal DataFrame-backed path for the same underlying data.
# ---------------------------------------------------------------------------

def test_printcp_ndarray_cptable_fallback_matches_dataframe_path(capsys):
    df = kyphosis_df()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    df_lines, df_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    ndarray_fit = dict(py_fit)
    ndarray_fit["cptable"] = py_fit["cptable"].to_numpy()
    assert isinstance(ndarray_fit["cptable"], np.ndarray)
    nd_lines, nd_retval = capture_printcp_lines_and_result(capsys, ndarray_fit, digits=4)

    assert nd_lines == df_lines
    assert isinstance(nd_retval, np.ndarray)
    np.testing.assert_allclose(nd_retval, df_retval.to_numpy(dtype=float))


# ---------------------------------------------------------------------------
# 9. Numeric (non-factor) response fit with method="class" explicitly --
#    ylevels become character codes "0"/"1" rather than named factor
#    levels. Exercises the variable-name-set comparison (gap 2) on a
#    differently-constructed classification fit than test 2 above.
# ---------------------------------------------------------------------------

def test_printcp_numeric_response_as_class_kyphosis(capsys):
    df = kyphosis_df().copy()
    df["Kyph01"] = (df["Kyphosis"] == "present").astype(int)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyph01 ~ Age + Number + Start", method='"class"', control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=4)

    py_fit = rpart("Kyph01 ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    _assert_vars_used_match_as_sets(py_lines, r_lines)
    _assert_core_lines_match(py_lines, r_lines)
    _assert_cptable_values_match(py_retval, r_mat, r_cols)


# ---------------------------------------------------------------------------
# 10. KNOWN, PERMANENT GAP (1): the R-call echo line(s). Demonstrates
#     explicitly (once, rather than repeating the note in every test above)
#     that printcp.py's `print(repr(x['call']))` can never match R's
#     `dput()`-based call echo for any r2py_rpart.rpart()-built fit, since
#     `x['call']['data']` holds the entire *evaluated* input DataFrame
#     object rather than an unevaluated call expression.
#
#     This was investigated as part of the printcp.py digits-formatting
#     fix (see printcp.py's `_r_format`/`_validate_digits`) but is NOT
#     fixable there, or anywhere within r2py_rpart's normal runtime: R's
#     `dput(cl, control=NULL)` pretty-prints the *unevaluated parse tree* of
#     the original call (e.g. literally the source token `df`, the
#     caller's variable name for the data argument), which R can do because
#     `match.call()` captures call expressions unevaluated, before any
#     argument is looked up/evaluated. Python has no equivalent -- by the
#     time `rpart(formula, data=df, ...)` runs, `data` is already bound to
#     the evaluated DataFrame *object*; the token "df" was discarded by the
#     interpreter at the call site and is not recoverable from within
#     rpart()'s body (short of unreliable source/AST introspection via the
#     caller's stack frame, which would only work for a bare-variable
#     argument, not arbitrary expressions, and is out of scope for
#     printcp.py -- rpart()'s own call-recording lives in rpart.py, a
#     different file). So this is a fundamental representation difference
#     (unevaluated call vs. evaluated object), not a printcp.py formatting
#     bug -- marked xfail(strict=True) rather than left as a bare failing
#     assertion, so a regression that accidentally "fixes" it (and
#     therefore stops raising) would itself be flagged as a test failure.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "R's dput()-based call echo prints the unevaluated call expression "
        "(e.g. the literal source token 'df'); Python has no equivalent -- "
        "rpart()'s stored call dict holds the already-evaluated DataFrame "
        "object, with the caller's original variable name irrecoverably "
        "lost. Not fixable within printcp.py (or without fragile stack/AST "
        "introspection elsewhere in the codebase)."
    ),
    strict=True,
)
def test_printcp_call_echo_is_a_known_formatting_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines, _, _ = r_printcp_lines_and_result(r_fit, digits=5)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, _ = capture_printcp_lines_and_result(capsys, py_fit, digits=5)

    ## R's call echo is a short, one-or-two-line `dput()` rendering...
    r_call_line = r_lines[2]
    assert r_call_line.startswith("rpart(formula = Mileage ~ Weight")
    ## ...while python's dumps the entire 60-row input DataFrame's repr
    ## inline (spanning dozens of lines) instead of a call expression.
    py_call_line = py_lines[2]
    assert "formula" in py_call_line and "data" in py_call_line

    # KNOWN GAP (1): expected to fail -- these can never be the same text.
    assert py_call_line == r_call_line

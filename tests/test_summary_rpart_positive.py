"""Positive-path parity tests for r2py_rpart.summary_rpart vs. R's
summary.rpart (rpart:::summary.rpart, S3-dispatched via summary()).

Each test fits an identical model in both R (via rpy2) and Python, then
summarizes it in both and compares the console layout as rigorously as the
two implementations' formatting allows. See tests/_r_rpart_helpers.py's
summary.rpart-specific plumbing (added for this test-generation task) for
the shared machinery used throughout:

  - `r_summary_rpart_lines(fit, **kwargs)` -- calls R's `summary(fit, ...)`
    (the documented S3-generic calling convention) via `capture.output()`
    and returns its console output as a list of lines.
  - `capture_summary_rpart_lines(capsys, fit, **kwargs)` -- calls
    r2py_rpart.summary_rpart(fit, ...) and returns (its stdout output as a
    list of lines, its return value), via pytest's `capsys` fixture.
  - `summary_rpart_find_n_line(lines)` -- the "n=..." header line.
  - `summary_rpart_variable_importance_dict_r`/`_py(lines)` -- parse the
    "Variable importance" block (both sides: a 2-line column-aligned
    named-vector print, matching R's own `print(temp[temp > 0])` layout --
    see gap (3)'s note below) into a plain `{name: value}` dict.
  - `assert_summary_node_blocks_match(py_lines, r_lines)` -- asserts every
    "Node number ..." block agrees between the two sides, modulo
    `normalize_summary_line`'s cosmetic (trailing-whitespace /
    float-trailing-zero-padding) normalization.
  - `extract_r_fit(fit)` -- pulls `cptable`/`variable_importance` etc.
    straight off the *R* fit object (bypassing any print formatting at all),
    for numeric-only cross-checks against r2py_rpart's own fit dict.

KNOWN, PERMANENT FORMATTING-PARITY GAP
---------------------------------------
Of the three formatting-parity gaps this module originally documented, two
have since been closed by reimplementing summary_rpart.py's number/vector
formatting to match R's own `format()`/`print.default()` rules in full
(see summary_rpart.py's `_r_format_matrix_column`/`_r_format_cptable`/
`_print_r_named_vector`); only the R-call echo remains permanent:

(1) R-call echo. Identical to printcp's/print.rpart's own gap 1: R's
    `dput(x$call, control=NULL)` pretty-prints the *unevaluated call
    expression* (preserving the caller's own source text, e.g. the
    variable name `df`, the unexpanded `rpart.control(xval = 0)` sub-call);
    r2py_rpart.rpart()'s `Call` dict instead records already-*evaluated*
    argument values (e.g. `"data"` holds the actual DataFrame, with no
    record of the caller's variable name at all). Python has no
    equivalent of R's unevaluated-language-object/promise mechanism, and
    summary_rpart.py's print-formatting alone cannot reconstruct one --
    see `test_summary_rpart_call_echo_is_a_known_formatting_gap`
    (`xfail(strict=True)`) for the full reasoning.

(2) [CLOSED] cp-table numeric formatting/alignment. R's `print(x$cptable,
    digits=digits)` column-aligns/pads every column to a shared decimal
    width (or a shared scientific-notation width, whichever is narrower);
    summary_rpart.py now reproduces that exact per-column rule (see
    `_r_format_cptable`) instead of `pandas.DataFrame.to_string()`'s
    independent, non-`digits`-driven default precision. Every positive
    test below still *also* verifies the cp-table's underlying numeric
    values directly (via `extract_r_fit`), independent of print layout,
    but `test_summary_rpart_cptable_print_format_is_a_known_formatting_gap`
    now additionally confirms the *printed* CP-column line matches R's
    exactly.

(3) [CLOSED] "Variable importance" block layout. R's `print(temp[temp >
    0])` prints a named-vector layout (a names line, then a values line,
    both column-aligned); summary_rpart.py now reproduces that same
    layout (see `_print_r_named_vector`) instead of one "name: value" line
    per variable, so
    `test_summary_rpart_variable_importance_layout_is_a_known_formatting_gap`
    now compares the raw printed block line-for-line (not just the parsed
    dict every other test here already checked via
    `_assert_variable_importance_matches`).

Every other section of the output (the "n=" header and every per-node
"Node number ..." block, including "Primary splits:"/"Surrogate splits:")
matches R's text modulo only cosmetic trailing-whitespace/trailing-zero
differences, both collapsed by `normalize_summary_line`
(`assert_summary_node_blocks_match` uses it internally); those sections are
compared with genuine line-for-line rigor below.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart

from _r_rpart_helpers import (
    assert_summary_node_blocks_match,
    capture_summary_rpart_lines,
    cu_summary_df,
    extract_r_fit,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_summary_rpart_lines,
    run_r,
    stagec_df,
    summary_rpart_find_n_line,
    summary_rpart_variable_importance_dict_py,
    summary_rpart_variable_importance_dict_r,
)


def _assert_cptable_values_match(py_fit: dict, r_fit) -> None:
    """Gap (2): the *printed* cp-table can never match textually, but the
    underlying numeric values (and column names) must agree exactly,
    independent of any print-formatting difference."""
    r_extracted = extract_r_fit(r_fit)
    py_cptable = py_fit["cptable"]
    assert list(py_cptable.columns) == r_extracted["cptable_cols"]
    np.testing.assert_allclose(
        py_cptable.to_numpy(dtype=float), r_extracted["cptable"], rtol=1e-5, atol=1e-8
    )


def _assert_variable_importance_matches(py_lines: list[str], r_lines: list[str], r_fit) -> None:
    """Gap (3): parse both sides' "Variable importance" blocks into plain
    {name: value} dicts and compare, plus cross-check against the rounded
    percentage independently recomputed from R's raw `variable.importance`
    vector (pulled directly off the fit, not from any printed text)."""
    py_vi = summary_rpart_variable_importance_dict_py(py_lines)
    r_vi = summary_rpart_variable_importance_dict_r(r_lines)
    assert py_vi is not None and r_vi is not None
    assert py_vi == r_vi

    raw = extract_r_fit(r_fit)["variable_importance"]
    total = sum(raw.values())
    expected = {name: int(round(100 * val / total)) for name, val in raw.items()}
    expected = {name: val for name, val in expected.items() if val > 0}
    assert r_vi == expected


# ---------------------------------------------------------------------------
# 1. summary.rpart.Rd's own first worked example (regression/"anova" tree,
#    car.test.frame Mileage~Weight). Exercises the generic (non-tfun)
#    "mean=..., MSE=..." node-summary format.
# ---------------------------------------------------------------------------

def test_summary_rpart_default_args_matches_r_car_test_frame_anova(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_summary_rpart_lines(capsys, py_fit)

    assert py_retval is py_fit  # mirrors R's invisible(x): same object returned
    assert summary_rpart_find_n_line(py_lines).replace(" ", "") == summary_rpart_find_n_line(r_lines).replace(
        " ", ""
    )
    _assert_cptable_values_match(py_fit, r_fit)
    _assert_variable_importance_matches(py_lines, r_lines, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 2. summary.rpart.Rd's own second worked example (classification tree,
#    kyphosis): exercises the multi-line "predicted class=.../class
#    counts:.../probabilities:..." node-summary format, plus genuine
#    Primary/Surrogate splits sections.
# ---------------------------------------------------------------------------

def test_summary_rpart_default_args_matches_r_kyphosis_classification(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, py_retval = capture_summary_rpart_lines(capsys, py_fit)

    assert py_retval is py_fit
    assert summary_rpart_find_n_line(py_lines).replace(" ", "") == summary_rpart_find_n_line(r_lines).replace(
        " ", ""
    )
    _assert_cptable_values_match(py_fit, r_fit)
    _assert_variable_importance_matches(py_lines, r_lines, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 3. `cp=` trims nodes with complexity <= cp from the listing (a non-zero,
#    non-default value): exercises the `rows` filtering logic itself,
#    confirming both sides agree on exactly *which* nodes get printed, not
#    just how those that are printed are formatted.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_trims_node_listing(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, cp=0.02)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, cp=0.02)

    assert_summary_node_blocks_match(py_lines, r_lines)
    # Sanity: cp=0.02 really does trim the listing relative to cp=0 (fewer
    # node blocks than the full unpruned tree).
    r_lines_full = r_summary_rpart_lines(r_fit)
    assert len(r_lines) < len(r_lines_full)


# ---------------------------------------------------------------------------
# 4. `digits=` a non-default value (3): confirms the digits-driven
#    formatting inside each node block (complexity param, improve=,
#    probabilities) still agrees once `normalize_summary_line`'s numeric
#    normalization is applied, since both sides round to the *same*
#    `digits` value even though they pad the resulting text differently.
# ---------------------------------------------------------------------------

def test_summary_rpart_non_default_digits(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, digits=3)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, digits=3)

    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 5. method="poisson" (Surv()-style two-column response, stagec dataset,
#    mirroring the same pre-built model-frame pattern used elsewhere in this
#    test suite for poisson/Surv fits): exercises the "events=...,
#    estimated rate=..., mean deviance=..." node-summary format.
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


def test_summary_rpart_poisson_method_stagec(capsys):
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r("df$ploidy <- factor(df$ploidy)")
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_lines = r_summary_rpart_lines(r_fit)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)

    _assert_cptable_values_match(py_fit, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 6. na.action header + categorical ("splits as X") primary splits:
#    cu.summary has NAs in both the response and a predictor, and
#    Country/Type are unordered factors -- exercises both the "n=<n> (<k>
#    observations deleted due to missingness)" header and the "splits as
#    L-R"-style cut description (rather than the "< value" numeric-cut
#    description exercised by the other tests).
# ---------------------------------------------------------------------------

def test_summary_rpart_na_action_header_and_categorical_splits(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)
    r_n_line = summary_rpart_find_n_line(r_lines)
    assert "deleted due to missingness" in r_n_line

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)
    py_n_line = summary_rpart_find_n_line(py_lines)

    assert py_n_line == r_n_line  # both sides use sep="" in this branch: exact match
    _assert_cptable_values_match(py_fit, r_fit)
    _assert_variable_importance_matches(py_lines, r_lines, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)
    assert any("splits as" in line for line in r_lines)


# ---------------------------------------------------------------------------
# 7. A numeric (non-factor) response fit with method="class" explicitly --
#    ylevels become the character codes "0"/"1" rather than named factor
#    levels, exercising the ylevel-formatting path with numeric-looking
#    labels (mirroring test_print_rpart_positive.py's analogous test).
# ---------------------------------------------------------------------------

def test_summary_rpart_numeric_response_as_class_kyphosis(capsys):
    df = kyphosis_df().copy()
    df["Kyph01"] = (df["Kyphosis"] == "present").astype(int)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyph01 ~ Age + Number + Start", method='"class"', control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Kyph01 ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)

    _assert_cptable_values_match(py_fit, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 8. `file=` parameter: writes the entire summary to a file instead of
#    stdout. Confirms the file's content is *identical* to the stdout
#    capture for the same fit/kwargs (summary_rpart.py's `_do_summary()`
#    closure is invoked identically either way; only the redirect target
#    differs), on both the R (`sink(file)`) and python
#    (`contextlib.redirect_stdout`) sides.
# ---------------------------------------------------------------------------

def test_summary_rpart_file_argument_matches_stdout_capture(capsys, tmp_path):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines_stdout = r_summary_rpart_lines(r_fit)
    r_file = tmp_path / "r_summary.txt"
    run_r(f'summary(summary_fit_tmp, file="{r_file.as_posix()}")')
    r_lines_file = r_file.read_text().splitlines()
    assert r_lines_file == r_lines_stdout

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines_stdout, _ = capture_summary_rpart_lines(capsys, py_fit)
    py_file = tmp_path / "py_summary.txt"
    from r2py_rpart.summary_rpart import summary_rpart

    retval = summary_rpart(py_fit, file=str(py_file))
    assert retval is py_fit
    py_lines_file = py_file.read_text().splitlines()
    assert py_lines_file == py_lines_stdout

    assert_summary_node_blocks_match(py_lines_file, r_lines_file)


# ---------------------------------------------------------------------------
# 9. All non-default parameters combined at once (cp and digits together)
#    on the classification tree -- exercising the full parameter-
#    combination surface in a single call.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_and_digits_combined(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, cp=0.015, digits=4)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, cp=0.015, digits=4)

    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 10. KNOWN GAP (1): the R-call echo. Demonstrates explicitly (once) that
#     summary_rpart.py's `print(repr(x.get('call')))` can never match R's
#     `dput()`-based call echo for any r2py_rpart.rpart()-built fit.
#
#     Investigated as part of closing gaps (2)/(3) below: unlike those two
#     (pure print-formatting choices, fully fixable inside summary_rpart.py
#     alone), this one is not practically fixable from summary_rpart.py.
#     R's `dput(x$call, control=NULL)` pretty-prints the *unevaluated call
#     expression* captured by `match.call()` -- e.g. the literal source
#     text `data = df` (the caller's variable name), not the DataFrame's
#     contents, and `control = rpart.control(xval = 0)` as the literal
#     unevaluated sub-call, not the individual control values it expands
#     to. r2py_rpart.rpart() (rpart.py, out of scope for this fix -- see
#     this test module's owning task) instead records its `Call` dict with
#     already-*evaluated* argument values (`"data": data` -- the actual
#     DataFrame object, with no record of the caller's variable name at
#     all; `control=` is consumed into `rpart.control()`'s expanded fields
#     before `Call` is even built). Python has no built-in equivalent of R's
#     promise/unevaluated-language-object mechanism, and reconstructing one
#     would require capturing source text at every `rpart()` call site
#     (e.g. via `inspect`), a change to rpart.py's own call-recording logic
#     -- well outside summary_rpart.py's print-formatting responsibility.
#     This assertion is therefore kept, `xfail(strict=True)`, as a
#     permanent, deliberately-undismissed documentation of the gap (per
#     this test suite's established convention for such cases).
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "R's dput()-based call echo pretty-prints the unevaluated call "
        "expression (match.call()), preserving the caller's own source "
        "text (e.g. the variable name 'df', the unexpanded "
        "'rpart.control(xval = 0)' sub-call); r2py_rpart.rpart() records "
        "its Call dict with already-evaluated argument values instead (no "
        "variable-name or unevaluated-expression capture at all), which "
        "summary_rpart.py's print-formatting alone cannot reconstruct. "
        "Fixing this would require rpart.py to capture call-site source "
        "text (e.g. via inspect), out of scope for a summary_rpart.py-only fix."
    ),
    strict=True,
)
def test_summary_rpart_call_echo_is_a_known_formatting_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)

    assert r_lines[0] == py_lines[0] == "Call:"
    r_call_line = r_lines[1]
    assert r_call_line.startswith("rpart(formula = Mileage ~ Weight")
    py_call_line = py_lines[1]
    assert "formula" in py_call_line and "data" in py_call_line

    # KNOWN GAP (1): expected to fail -- these can never be the same text.
    assert py_call_line == r_call_line


# ---------------------------------------------------------------------------
# 11. FORMER KNOWN GAP (2), now closed: the cp-table's printed formatting.
#     Confirms that, in addition to the *underlying* cp-table values
#     already agreeing exactly (checked via `_assert_cptable_values_match`
#     in every test above), the printed CP-column text now matches R's
#     exactly too (see `_r_format_cptable` in summary_rpart.py).
# ---------------------------------------------------------------------------

def test_summary_rpart_cptable_print_format_is_a_known_formatting_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.001, xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, digits=5)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.001, "xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, digits=5)

    _assert_cptable_values_match(py_fit, r_fit)  # numeric values agree exactly

    r_cp_line = next(line for line in r_lines if line.strip().startswith("CP"))
    py_cp_line = next(line for line in py_lines if line.strip().startswith("CP"))
    # Gap closed: column alignment/precision now matches R exactly.
    assert py_cp_line == r_cp_line


# ---------------------------------------------------------------------------
# 12. FORMER KNOWN GAP (3), now closed: the "Variable importance" block's
#     raw text layout. summary_rpart.py used to print one "Name: Value"
#     line per variable; it now prints R's own 2-line column-aligned
#     named-vector layout (see `_print_r_named_vector` in summary_rpart.py),
#     so both the *parsed* {name: value} dicts (already checked via
#     `_assert_variable_importance_matches` in tests 1/2/6 above) and the
#     raw printed lines agree exactly -- confirmed empirically below.
# ---------------------------------------------------------------------------

def test_summary_rpart_variable_importance_layout_is_a_known_formatting_gap(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)

    _assert_variable_importance_matches(py_lines, r_lines, r_fit)  # parsed dicts agree

    r_idx = r_lines.index("Variable importance")
    py_idx = py_lines.index("Variable importance")
    # Both sides' block is now exactly 3 lines: the header, the
    # column-aligned names line, and the column-aligned values line (the
    # old python-side slice of 4 lines was sized for the retired
    # one-"Name: Value"-line-per-variable layout).
    r_block = r_lines[r_idx : r_idx + 3]
    py_block = py_lines[py_idx : py_idx + 3]
    # Gap closed: both sides now use the same 2-line column-aligned
    # named-vector layout.
    assert py_block == r_block

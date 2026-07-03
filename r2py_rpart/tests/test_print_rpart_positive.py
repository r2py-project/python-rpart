"""Positive-path parity tests for r2py_rpart.print_rpart vs. R's
print.rpart (rpart:::print.rpart, S3-dispatched via print()).

Each test fits an identical model in both R (via rpy2) and Python, then
prints it in both and asserts the *entire* console layout -- header,
column-header line, "* denotes terminal node" line, and every per-node
tree line -- matches exactly, line for line. print.rpart's whole contract
*is* its formatted text layout (see print.rpart.Rd's own worked example),
so an exact list-of-lines comparison is the right level of rigor here (as
opposed to, say, only comparing the underlying numeric values).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing, in particular:
  - `r_print_rpart_lines(fit, **kwargs)` -- builds/evaluates an R
    `rpart:::print.rpart(fit, ...)` call (bypassing S3 dispatch, per
    print.rpart.Rd's own note that it may be invoked directly) and
    returns its console output as a list of lines.
  - `capture_print_rpart_lines(capsys, fit, **kwargs)` -- calls
    r2py_rpart.print_rpart(fit, ...) and returns its stdout output as a
    list of lines, via pytest's built-in `capsys` fixture.

NOTE on a known formatting-parity gap: several tests below (marked in
their docstrings) fit models where the printed `dev`/`yval` columns hold
multiple distinct floating-point magnitudes within the same tree. R's
`format(signif(x, digits))` right-*aligns the decimal point* across the
whole column (padding shorter values with trailing zeros so every row
gets the same number of decimal places), whereas print_rpart.py's
per-element `%g`-style formatting only right-justifies by *character
width*, without adding trailing zeros to align decimals. Where this
causes a genuine text mismatch it is called out explicitly in the test
docstring -- it is a real formatting gap in print_rpart.py, not a mistake
in the test. It does not manifest for classification ("class"-method)
trees with uniform case weights, since their `dev` column holds integer
loss counts (no decimals to align), nor for any single-row (root-only)
`frame`, since there is nothing else in the column to align against.

A second, independent known formatting-parity gap affects classification
("class"-method) trees with fewer than 5 response levels: R's
rpart.class's `print` function formats the `(yprob)` column via
`format(yval[, ...], digits = digits, nsmall = nsmall)` -- R's general
`format()`, whose digits= argument means "at least this many *significant*
digits" (expanding as needed). print_rpart.py's Python translation
(`rpart_class.py`'s `print_func`) instead hand-computes a fixed decimal
count from `digits`/`nsmall` via `magnitude = floor(log10(|v|))`, which
produces a different (typically one-too-few) number of decimal places
than R's format() for values less than 1 (e.g. R prints "0.79012346", 8
decimals, where digits=nsmall=7; the Python translation prints
"0.7901235", 7 decimals). This is called out explicitly wherever it
applies (any classification tree with nclass < 5, e.g. the binary
`kyphosis` examples below); it does not affect trees with nclass >= 5
(e.g. the 5-level `cu.summary` examples below), which instead go through
`formatg(..., digits=2L)` and match exactly.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart

from _r_rpart_helpers import (
    capture_print_rpart_lines,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_print_rpart_lines,
    run_r,
    stagec_df,
)


# ---------------------------------------------------------------------------
# 1. Default arguments on a regression ("anova") tree -- this is verbatim
#    print.rpart.Rd's own worked example (`z.auto <- rpart(Mileage ~
#    Weight, car.test.frame); z.auto`). No custom $functions$print, so
#    `yval`/`dev` both go through the generic format(signif(...)) path
#    (the decimal-alignment gap noted in the module docstring applies
#    here).
# ---------------------------------------------------------------------------

def test_print_rpart_default_args_matches_r_car_test_frame_anova(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 2. Default arguments on a classification ("class") tree (kyphosis is a
#    binary/2-level response, so nclass=2 < 5: subject to the yprob
#    decimal-count gap noted in the module docstring). dev holds integer
#    loss counts here, so it is *not* subject to the separate
#    decimal-alignment gap.
# ---------------------------------------------------------------------------

def test_print_rpart_default_args_matches_r_kyphosis_classification(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 3. `spaces=` parameter: a non-default indent width (4 spaces per depth
#    level instead of 2) on the classification tree (nclass=2 < 5: subject
#    to the yprob decimal-count gap noted in the module docstring).
# ---------------------------------------------------------------------------

def test_print_rpart_with_spaces_param_classification(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, spaces=4)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, spaces=4)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 4. `digits=` parameter: a smaller-than-default digits count (3) on the
#    classification tree, changing the yprob decimal precision (nclass=2
#    < 5: subject to the yprob decimal-count gap noted in the module
#    docstring).
# ---------------------------------------------------------------------------

def test_print_rpart_with_digits_param_classification(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, digits=3)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, digits=3)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 5. `minlength=1` abbreviates categorical-split labels down to single
#    letters (the classic `cu.summary` example: `Country`/`Type` factors).
# ---------------------------------------------------------------------------

def test_print_rpart_minlength_one_abbreviates_categorical_splits(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, minlength=1)

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit, minlength=1)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 6. `minlength=3` abbreviates categorical-split labels via R's
#    `abbreviate()` (vowel/consonant-dropping) algorithm rather than
#    single letters.
# ---------------------------------------------------------------------------

def test_print_rpart_minlength_three_abbreviates_categorical_splits(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, minlength=3)

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit, minlength=3)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 7. `cp=` pruning: fit a deep tree (small control cp), then print with a
#    larger cp so print.rpart internally re-prunes (via prune.rpart)
#    before printing -- exercising the `if cp is not _MISSING: x =
#    prune_rpart(x, cp=cp)` branch. Regression tree, so still subject to
#    the decimal-alignment gap noted in the module docstring.
# ---------------------------------------------------------------------------

def test_print_rpart_with_cp_pruning_matches_r(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines = r_print_rpart_lines(r_fit, cp=0.1)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, cp=0.1)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 8. `nsmall=` parameter on a classification tree: forces a minimum
#    number of decimal places in the yprob column even when `digits`
#    alone would produce fewer (nclass=2 < 5: subject to the yprob
#    decimal-count gap noted in the module docstring).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nsmall", [1, 5])
def test_print_rpart_with_nsmall_param_classification(capsys, nsmall):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, nsmall=nsmall)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, nsmall=nsmall)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 9. method="poisson" (a Surv()-style two-column response, matching the
#    same pre-built model-frame pattern used in
#    test_predict_rpart_positive.py's poisson test): exercises the
#    "node), split, n, deviance, yval" header (any non-"class" method)
#    together with the no-tfun yval/dev formatting path.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df, predictors):
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


def test_print_rpart_poisson_method_stagec(capsys):
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.02))'
    )
    r_lines = r_print_rpart_lines(r_fit)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.02},
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 10. na.action header: `cu.summary` has NAs in both the response
#     (Reliability) and a predictor (Mileage), so R's default na.action
#     (na.rpart) omits them and print.rpart's header must read
#     "n=<total> (<k> observations deleted due to missingness)". dev
#     holds integer loss counts here, so this is *not* subject to the
#     decimal-alignment gap and should match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_na_action_header_cu_summary(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit)
    assert "deleted due to missingness" in r_lines[0]

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 11. All non-default parameters combined at once (minlength, spaces,
#     digits, nsmall together) on the classification tree -- exercising
#     the full parameter-combination surface in a single call (nclass=2 <
#     5: subject to the yprob decimal-count gap noted in the module
#     docstring).
# ---------------------------------------------------------------------------

def test_print_rpart_all_params_combined_classification(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, minlength=2, spaces=3, digits=4, nsmall=2)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, minlength=2, spaces=3, digits=4, nsmall=2)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 12. A numeric (non-factor) response fit with method="class" explicitly
#     -- ylevels become the character codes "0"/"1" rather than named
#     factor levels (rpart_class's `pd.Categorical(y)` on a numeric
#     column), exercising the ylevel-formatting path with numeric-looking
#     labels. dev is integer here (no alignment-gap interference), but
#     nclass=2 < 5 still triggers the yprob decimal-count gap noted in the
#     module docstring.
# ---------------------------------------------------------------------------

def test_print_rpart_numeric_response_as_class_kyphosis(capsys):
    df = kyphosis_df()
    df = df.copy()
    df["Kyph01"] = (df["Kyphosis"] == "present").astype(int)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyph01 ~ Age + Number + Start", method='"class"', control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit)

    py_fit = rpart("Kyph01 ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines

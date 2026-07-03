"""Boundary/edge-case parity tests for r2py_rpart.print_rpart vs. R's
print.rpart (rpart:::print.rpart, called directly -- see
tests/_r_rpart_helpers.py's module docstring in test_print_rpart_negative.py
for why -- and via capture.output() to get a line-by-line comparison
against r2py_rpart.print_rpart's stdout output).

These focus on the functional extremes: a root-only (no-split) tree, a
tree deep enough to approach print.rpart's hard-coded 32-level indent
buffer, minimal/maximal `digits=`, `spaces=0`, extreme `cp=` values (both
"prune everything" and "prune nothing"), `nsmall=0`, an oversized
`minlength=`, and the two na.action header branches (present vs. absent).

Several of these are known, *a priori*, to disagree with R due to the two
formatting-parity gaps documented at length in
tests/test_print_rpart_positive.py's module docstring:
  (a) the generic (non-classification) `dev`/`yval` columns don't align
      decimals across multiple rows the way R's `format(signif(x,
      digits))` does, and
  (b) classification trees with nclass < 5 format `(yprob)` decimals via
      a hand-rolled formula rather than R's `format(..., digits=,
      nsmall=)`.
Both gaps disappear whenever the printed frame has only a single row
(nothing else in the column to align against) -- see the root-only and
cp="prune everything" tests below, which pass exactly for that reason.
Each test's docstring says explicitly whether it is expected to pass or
is a known-gap case.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from r2py_rpart import rpart

from _r_rpart_helpers import (
    capture_print_rpart_lines,
    cu_summary_df,
    from_r_dataframe,
    r_dataframe_assign,
    r_fit_rpart,
    r_print_rpart_lines,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. Root-only tree (a single leaf node, forced via a huge minsplit so no
#    split ever happens): both the `if len(node) > 1` / R's `if
#    (length(node) > 1L)` branch and labels_rpart's `n == 1 -> ["root"]`
#    special case are exercised. With only one frame row there is nothing
#    to align decimals against, so this is NOT subject to gap (a) --
#    expected to match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_root_only_tree_matches_r(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(minsplit=1000, xval=0)")
    r_lines = r_print_rpart_lines(r_fit)

    py_fit = rpart("Mileage ~ Weight", data=df, control={"minsplit": 1000, "xval": 0})
    assert len(py_fit["frame"]) == 1  # sanity: really is root-only
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 2. A deep tree (maxdepth=15, well under the hard-coded 32-level indent
#    buffer in both R's `indent <- paste(rep(" ", spaces * 32L), ...)`
#    and print_rpart.py's `' ' * (spaces * 32)`, but deep enough to
#    exercise many distinct indent widths). Built from a shared synthetic
#    dataset (generated once in Python, transferred to R via
#    r_dataframe_assign) so both sides fit on bit-identical data.
#    KNOWN GAP (a): this is a plain "anova" tree with >1 frame row, so the
#    dev/yval decimal-alignment gap applies -- expected to disagree on
#    exact formatting, though the *line count* (i.e. tree structure/split
#    points) is checked separately and does match.
# ---------------------------------------------------------------------------

def test_print_rpart_deep_tree_structure_matches_r(capsys):
    rng = np.random.default_rng(1)
    n = 200
    data = {"y": rng.standard_normal(n)}
    for i in range(1, 9):
        data[f"x{i}"] = rng.standard_normal(n)
    df = pd.DataFrame(data)
    r_dataframe_assign("df", df)

    control = {"cp": 0.002, "minsplit": 6, "minbucket": 2, "maxdepth": 15, "xval": 0}
    r_control = "rpart.control(cp=0.002, minsplit=6, minbucket=2, maxdepth=15, xval=0)"
    r_fit = r_fit_rpart("y ~ .", control=r_control)
    r_lines = r_print_rpart_lines(r_fit)

    py_fit = rpart("y ~ .", data=df, method="anova", control=control)
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    # Same number of lines/rows -> identical tree structure and split
    # points; a real assertion of full-text equality is expected to fail
    # per known gap (a) above, and is included precisely to document that.
    assert len(py_lines) == len(r_lines)
    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 3. `spaces=0`: no indentation at all, regardless of node depth.
#    KNOWN GAP (a) applies (car.test.frame anova tree, >1 row).
# ---------------------------------------------------------------------------

def test_print_rpart_spaces_zero_no_indentation(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines = r_print_rpart_lines(r_fit, spaces=0)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, spaces=0)

    # None of the tree lines should carry any leading indentation once
    # spaces=0 (every node line starts directly with its node number).
    for line in r_lines[5:]:
        assert not line.startswith(" ") or line.split(")")[0].strip().isdigit()

    assert py_lines == r_lines  # KNOWN GAP (a): expected to fail


# ---------------------------------------------------------------------------
# 4. `digits=1`: the smallest digits value R accepts without special-casing
#    (it does NOT raise, unlike a non-numeric digits -- see
#    test_print_rpart_negative.py). KNOWN GAP (a) applies.
# ---------------------------------------------------------------------------

def test_print_rpart_digits_minimal(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines = r_print_rpart_lines(r_fit, digits=1)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, digits=1)

    assert py_lines == r_lines  # KNOWN GAP (a): expected to fail


# ---------------------------------------------------------------------------
# 5. `digits=15`: a large digits value (well beyond the R default of 7,
#    approaching double precision). KNOWN GAP (a) applies.
# ---------------------------------------------------------------------------

def test_print_rpart_digits_large(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines = r_print_rpart_lines(r_fit, digits=15)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, digits=15)

    assert py_lines == r_lines  # KNOWN GAP (a): expected to fail


# ---------------------------------------------------------------------------
# 6. `nsmall=0` (the minimum) on a 5-level classification tree
#    (cu.summary/Reliability, nclass=5): avoids known gap (b) (only
#    applies when nclass < 5), so this is expected to match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_nsmall_zero_classification_five_levels(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, nsmall=0)

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit, nsmall=0)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 7. `minlength=100`: far larger than any category-label length in the
#    data, so R's abbreviate()-based logic (and labels_rpart.py's
#    `_abbrev_one`) both leave every label unabbreviated (full names
#    printed) -- exercises the "target length already satisfied" early
#    return in the abbreviation helper. nclass=5, so no known-gap
#    interference; expected to match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_minlength_oversized_no_abbreviation(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit, minlength=100)

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit, minlength=100)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 8. `cp=` large enough to prune every split back to the root (cp=999):
#    like the root-only test above, the resulting single-row frame sits
#    outside known gap (a) -- expected to match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_cp_prunes_everything_to_root(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines = r_print_rpart_lines(r_fit, cp=999)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines = capture_print_rpart_lines(capsys, py_fit, cp=999)

    assert py_lines == r_lines
    assert len(py_lines) == 6  # header (5 lines) + a single "1) root ... *" line


# ---------------------------------------------------------------------------
# 9. `cp=` negative: complexity is never <= a negative cp (complexity is
#    always >= 0 in a valid cptable), so *no* pruning happens and the full
#    original tree prints unchanged -- confirmed to not raise in R (unlike
#    the non-numeric cp cases explored in test_print_rpart_negative.py).
#    KNOWN GAP (a) applies (multi-row anova tree).
# ---------------------------------------------------------------------------

def test_print_rpart_cp_negative_prunes_nothing(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(cp=0.0001, xval=0)")
    r_lines_full = r_print_rpart_lines(r_fit)
    r_lines_neg_cp = r_print_rpart_lines(r_fit, cp=-1)
    assert r_lines_neg_cp == r_lines_full  # sanity: R itself does no pruning

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"cp": 0.0001, "xval": 0})
    py_lines_full = capture_print_rpart_lines(capsys, py_fit)
    py_lines_neg_cp = capture_print_rpart_lines(capsys, py_fit, cp=-1)
    assert py_lines_neg_cp == py_lines_full  # sanity: Python itself does no pruning either

    assert py_lines_neg_cp == r_lines_neg_cp  # KNOWN GAP (a): expected to fail


# ---------------------------------------------------------------------------
# 10. The na.action header's *complement*: a complete-case subset of
#     cu.summary (all rows with any NA dropped beforehand) has nothing for
#     na.rpart to omit, so the header must read "n=<n> \n\n" (no
#     parenthetical) rather than "n=<n> (<k> observations deleted ...)".
#     nclass=5, so no known-gap interference -- expected to match exactly.
# ---------------------------------------------------------------------------

def test_print_rpart_no_na_action_header_when_no_missingness(capsys):
    df = cu_summary_df().dropna().reset_index(drop=True)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_print_rpart_lines(r_fit)
    assert "deleted due to missingness" not in r_lines[0]

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines = capture_print_rpart_lines(capsys, py_fit)

    assert py_lines == r_lines


# ---------------------------------------------------------------------------
# 11. `nsmall=` explicitly set equal to `digits=` (the same value the
#     default `nsmall = min(20, digits)` would already resolve to):
#     confirms passing it explicitly is a no-op relative to leaving it
#     unset. nclass=5, so no known-gap interference -- expected to match
#     exactly on both the R and the Python side, *and* to equal the
#     digits-only (implicit nsmall) call.
# ---------------------------------------------------------------------------

def test_print_rpart_nsmall_equal_to_digits_matches_implicit_default(capsys):
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines_explicit = r_print_rpart_lines(r_fit, digits=4, nsmall=4)
    r_lines_implicit = r_print_rpart_lines(r_fit, digits=4)
    assert r_lines_explicit == r_lines_implicit

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines_explicit = capture_print_rpart_lines(capsys, py_fit, digits=4, nsmall=4)
    py_lines_implicit = capture_print_rpart_lines(capsys, py_fit, digits=4)
    assert py_lines_explicit == py_lines_implicit

    assert py_lines_explicit == r_lines_explicit

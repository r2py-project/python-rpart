"""Boundary/edge-case parity tests for r2py_rpart.printcp vs. R's
rpart::printcp.

These focus on the functional extremes: a root-only (no-split) tree, a
single-row cp-table's interaction with the column-formatting gaps, minimal/
maximal `digits=`, na.action present vs. absent, a tree using only one
predictor vs. several, an exactly-singular "1 observation deleted" na.action
count, and the ndarray-vs-DataFrame cptable equivalence (printcp.py's
fallback branch for a bare numpy.ndarray `x['cptable']`, exercised here on
the 5-column/xval>0 shape, complementing the 3-column/xval=0 shape already
covered in test_printcp_positive.py).

Several of these are known, *a priori*, to disagree with R due to the
formatting-parity gaps documented at length in
test_printcp_positive.py's module docstring:
  (2) the "Variables actually used" list's raw text never matches (python
      list-repr vs. R's vector-print layout) -- checked here via
      variable-name *sets* instead.
  (3) a root-only/no-split tree: R always prints the "Variables actually
      used..." header (with the literal body "character(0)"), while
      printcp.py's `len(used) > 0` guard skips the whole block -- a
      genuine behavioral divergence, not just a formatting one.
  (4) cp-table numeric formatting: R aligns decimals down each column;
      printcp.py formats each value independently. This also manifests, in
      a more minor form, as a pure column-*padding-width* difference even
      for a single-row table (nothing to decimal-align against, but
      pandas' `to_string()` and R's matrix printer still pick different
      inter-column spacing) -- demonstrated explicitly below.
  (6) the "n=" line's whitespace, in the no-na.action branch only (R's
      `cat(..., sep=" ")` default vs. printcp.py's plain f-string).
Each test's docstring says explicitly whether it is expected to pass or is
a known-gap case; KNOWN GAP assertions are kept in place (not weakened or
deleted) exactly as elsewhere in this test suite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

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
)


def _assert_root_and_n_lines_match(py_lines: list[str], r_lines: list[str], *, omit_present: bool) -> None:
    py_root = printcp_find_line(py_lines, "Root node error:")
    r_root = printcp_find_line(r_lines, "Root node error:")
    assert py_lines[py_root] == r_lines[r_root]
    py_n_line = py_lines[py_root + 2]
    r_n_line = r_lines[r_root + 2]
    if omit_present:
        assert py_n_line == r_n_line
    else:
        # KNOWN GAP (6): whitespace-only difference in the no-omission
        # branch; the numeric content still agrees.
        assert py_n_line.replace(" ", "") == r_n_line.replace(" ", "")


# ---------------------------------------------------------------------------
# 1. Root-only tree (a single leaf node, forced via a huge minsplit so no
#    split ever happens). KNOWN GAP (3): R always prints the "Variables
#    actually used in tree construction:\ncharacter(0)\n" block for a
#    root-only frame (`is.null(character(0))` is FALSE); printcp.py's
#    `len(used) > 0` guard skips the block entirely. This is a genuine
#    behavioral divergence (not just cosmetic) -- the assertion below is
#    *expected to fail* and is kept in place to document it. The
#    "Root node error"/"n=" lines, which do NOT depend on this gap, are
#    checked separately and DO pass.
# ---------------------------------------------------------------------------

def test_printcp_root_only_tree_variables_used_block_known_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(minsplit=1000, xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"minsplit": 1000, "xval": 0})
    assert len(py_fit["frame"]) == 1  # sanity: really is root-only
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)

    ## Not subject to gap (3): these still match given equal digits.
    _assert_root_and_n_lines_match(py_lines, r_lines, omit_present=False)
    np.testing.assert_allclose(py_retval.to_numpy(dtype=float), r_mat, rtol=1e-5, atol=1e-8)

    ## R always prints the block (with literal body "character(0)");
    ## printcp.py's non-positive-length guard skips it outright.
    r_vars = printcp_vars_used_r(r_lines)
    py_vars = printcp_vars_used_py(py_lines)
    assert r_vars == set()  # R's "character(0)" parses to an empty set here
    assert "Variables actually used in tree construction:" in "\n".join(r_lines)

    # KNOWN GAP (3): expected to fail -- python omits the header line
    # entirely for a root-only tree, unlike R.
    assert py_vars == r_vars


# ---------------------------------------------------------------------------
# 2. A single-row cp-table's raw printed text vs. its numeric content. With
#    only one row there is nothing to decimal-*align* against (gap 4's
#    usual trigger), yet the raw text still fails to match byte-for-byte,
#    because pandas' `to_string()` and R's matrix printer pick different
#    inter-column padding widths. The *numeric* content (verified via both
#    a whitespace-insensitive token comparison of the printed row and the
#    independently-returned cptable value) matches exactly. This
#    demonstrates gap (4) is broader than just cross-row decimal alignment
#    -- the raw-text assertion is *expected to fail* and is kept in place.
# ---------------------------------------------------------------------------

def test_printcp_single_row_cptable_values_match_but_padding_does_not(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(minsplit=1000, xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class", control={"minsplit": 1000, "xval": 0}
    )
    assert len(py_fit["frame"]) == 1  # sanity: root-only -> single-row cptable
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)

    assert r_mat.shape == (1, 3)
    np.testing.assert_allclose(py_retval.to_numpy(dtype=float), r_mat, rtol=1e-5, atol=1e-8)

    ## Whitespace-insensitive: the same tokens (row label + 3 numbers)
    ## appear in both, just with different inter-column padding widths.
    r_cp_row = r_lines[-1]
    py_cp_row = py_lines[-1]
    assert r_cp_row.split() == py_cp_row.split()

    # KNOWN GAP (4, padding variant): expected to fail -- raw whitespace
    # widths differ between pandas.to_string() and R's matrix printer even
    # though there's only one row and no decimals to cross-row align.
    assert py_cp_row == r_cp_row


# ---------------------------------------------------------------------------
# 3. `digits=1`, the smallest value R accepts without raising (see
#    test_printcp_negative.py's digits=0 case, where R *does* raise).
#    Formerly a KNOWN GAP: printcp.py used to format via Python's
#    `format(1354.6, '.1g')`, which switches to scientific notation
#    ("1e+03") because '%g'-style formatting switches to scientific
#    whenever the value's decimal exponent >= the requested precision;
#    R's `format(1354.6, digits=1)` stays in fixed notation ("1355").
#    printcp.py now reproduces R's own fixed-vs-scientific width-comparison
#    algorithm (see `_r_format` in printcp.py), so this now matches R
#    exactly; the test name is kept as-is (it is the identifier this test
#    suite/tooling tracks it by) even though the gap it documents is fixed.
# ---------------------------------------------------------------------------

def test_printcp_digits_minimal_known_gap(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=1)
    r_root_line = r_lines[printcp_find_line(r_lines, "Root node error:")]
    assert r_root_line == "Root node error: 1355/60 = 23"

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=1)
    py_root_line = py_lines[printcp_find_line(py_lines, "Root node error:")]
    assert py_root_line == "Root node error: 1355/60 = 23"

    # Gap fixed: printcp.py's R-equivalent formatting now agrees with R.
    assert py_root_line == r_root_line


# ---------------------------------------------------------------------------
# 4. `digits=15`: a large digits value (well beyond R's own default of ~7,
#    approaching double precision). Unlike digits=1, this does NOT trigger
#    the scientific-notation divergence (both sides have ample precision
#    budget to stay in fixed notation), so the "Root node error"/"n=" lines
#    ARE expected to match exactly here (module gap 6 caveat aside).
# ---------------------------------------------------------------------------

def test_printcp_digits_large(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=15)

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=15)

    _assert_root_and_n_lines_match(py_lines, r_lines, omit_present=False)
    np.testing.assert_allclose(py_retval.to_numpy(dtype=float), r_mat, rtol=1e-10, atol=1e-12)


# ---------------------------------------------------------------------------
# 5. The na.action header's complement: a complete-case subset of
#    cu.summary (all rows with any NA dropped beforehand) has nothing for
#     na.rpart to omit, so the header must read "n=<n>" with no
#    parenthetical, on both sides (gap 6's whitespace caveat still applies
#     to this no-omission branch).
# ---------------------------------------------------------------------------

def test_printcp_no_na_action_header_when_no_missingness(capsys):
    df = cu_summary_df().dropna().reset_index(drop=True)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)
    r_n_line = r_lines[printcp_find_line(r_lines, "n=")]
    assert "deleted due to missingness" not in r_n_line

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)
    py_n_line = py_lines[printcp_find_line(py_lines, "n=")]
    assert "deleted due to missingness" not in py_n_line

    _assert_root_and_n_lines_match(py_lines, r_lines, omit_present=False)
    np.testing.assert_allclose(py_retval.to_numpy(dtype=float), r_mat, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 6. A tree using only one predictor vs. one using several: exercises the
#    variable-name-*set* comparison (gap 2) at both extremes of the
#    "Variables actually used" list's size, on the same underlying
#    dataset/formula (kyphosis), varying only `maxdepth`.
# ---------------------------------------------------------------------------

def test_printcp_single_vs_multiple_variables_used(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)

    ## maxdepth=1 -> only the root split's variable is ever used.
    r_fit_shallow = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(maxdepth=1, xval=0)")
    r_lines_shallow, _, _ = r_printcp_lines_and_result(r_fit_shallow, digits=4)
    py_fit_shallow = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class", control={"maxdepth": 1, "xval": 0}
    )
    py_lines_shallow, _ = capture_printcp_lines_and_result(capsys, py_fit_shallow, digits=4)
    r_vars_shallow = printcp_vars_used_r(r_lines_shallow)
    py_vars_shallow = printcp_vars_used_py(py_lines_shallow)
    assert len(r_vars_shallow) == 1
    assert py_vars_shallow == r_vars_shallow

    ## An unconstrained (small-cp) fit uses several variables.
    r_fit_deep = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(cp=0.001, xval=0)")
    r_lines_deep, _, _ = r_printcp_lines_and_result(r_fit_deep, digits=4)
    py_fit_deep = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class", control={"cp": 0.001, "xval": 0}
    )
    py_lines_deep, _ = capture_printcp_lines_and_result(capsys, py_fit_deep, digits=4)
    r_vars_deep = printcp_vars_used_r(r_lines_deep)
    py_vars_deep = printcp_vars_used_py(py_lines_deep)
    assert len(r_vars_deep) > 1
    assert py_vars_deep == r_vars_deep


# ---------------------------------------------------------------------------
# 7. Exactly one observation deleted due to missingness (singular
#    "observation", not plural "observations"): a complete-case cu.summary
#    subset with exactly one *response* value (Reliability) set back to
#    NaN (na.rpart only drops rows missing the response or missing every
#    predictor -- a single missing *predictor* value alone does not trigger
#    exclusion, confirmed empirically -- so the response is the field to
#    null out here). This branch has no known formatting gap (sep="" on
#    both sides), so the full "n=" line is expected to match exactly.
# ---------------------------------------------------------------------------

def test_printcp_singular_one_observation_deleted(capsys):
    df = cu_summary_df().dropna().reset_index(drop=True)
    df = df.copy()
    df.loc[0, "Reliability"] = np.nan
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines, r_mat, r_cols = r_printcp_lines_and_result(r_fit, digits=5)
    r_n_line = r_lines[printcp_find_line(r_lines, "n=")]
    assert r_n_line == "n=48 (1 observation deleted due to missingness)"

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    assert py_fit["na.action"]["indices"] == [1]
    py_lines, py_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=5)
    py_n_line = py_lines[printcp_find_line(py_lines, "n=")]

    assert py_n_line == r_n_line == "n=48 (1 observation deleted due to missingness)"
    np.testing.assert_allclose(py_retval.to_numpy(dtype=float), r_mat, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 8. The ndarray-cptable fallback branch on a 5-column (xval>0) cptable,
#    complementing test_printcp_positive.py's 3-column (xval=0) fallback
#    coverage: mutating `x['cptable']` to `.to_numpy()` on a fit whose
#    cptable includes xerror/xstd columns must still reproduce identical
#    output (and equal returned values) to the DataFrame-backed path.
# ---------------------------------------------------------------------------

def test_printcp_ndarray_cptable_fallback_five_columns(capsys):
    df = kyphosis_df()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 5})
    assert py_fit["cptable"].shape[1] == 5

    df_lines, df_retval = capture_printcp_lines_and_result(capsys, py_fit, digits=4)

    ndarray_fit = dict(py_fit)
    ndarray_fit["cptable"] = py_fit["cptable"].to_numpy()
    nd_lines, nd_retval = capture_printcp_lines_and_result(capsys, ndarray_fit, digits=4)

    assert nd_lines == df_lines
    assert isinstance(nd_retval, np.ndarray)
    np.testing.assert_allclose(nd_retval, df_retval.to_numpy(dtype=float))

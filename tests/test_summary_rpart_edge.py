"""Boundary/edge-case parity tests for r2py_rpart.summary_rpart vs. R's
summary.rpart (rpart:::summary.rpart / summary(), via capture.output() --
see tests/_r_rpart_helpers.py's summary.rpart-specific plumbing, and
test_summary_rpart_positive.py's module docstring for the three permanent,
purely-cosmetic formatting gaps (Call echo / cp-table print format /
Variable-importance layout) that every test below sidesteps the same way
the positive-path tests do: numeric cross-checks via `extract_r_fit`, and
`assert_summary_node_blocks_match` for the per-node "Node number ..."
blocks (which matches modulo `normalize_summary_line`'s cosmetic
normalization).

These focus on the functional extremes: a root-only (no-split) tree, `cp=`
values that prune everything or nothing, minimal/maximal `digits=`, a `cp=`
value sitting exactly on a real internal node's complexity boundary (the
`parent.cp > cp` comparison is strict), a fit with no surrogate splits at
all, the na.action header's absent-parenthetical complement, and the
`file=` argument combined with non-default `cp=`/`digits=`.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.summary_rpart import summary_rpart

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
    summary_rpart_find_n_line,
    summary_rpart_node_blocks,
    summary_rpart_variable_importance_dict_py,
    summary_rpart_variable_importance_dict_r,
)


def _assert_cptable_values_match(py_fit: dict, r_fit) -> None:
    r_extracted = extract_r_fit(r_fit)
    py_cptable = py_fit["cptable"]
    assert list(py_cptable.columns) == r_extracted["cptable_cols"]
    np.testing.assert_allclose(
        py_cptable.to_numpy(dtype=float), r_extracted["cptable"], rtol=1e-5, atol=1e-8
    )


# ---------------------------------------------------------------------------
# 1. Root-only tree (a single leaf node, forced via a huge minsplit so no
#    split ever happens): `x$variable.importance`/`x['variable_importance']`
#    is genuinely NULL/None on both sides for a root-only fit (not just
#    "all zero"), so the entire "Variable importance" block is skipped by
#    both R and python -- confirmed empirically before writing this test.
#    Also exercises the `if not np.all(is_leaf):`/`if (!all(is.leaf))`
#    "skip splits entirely" branch (no `x$splits`/`x['splits']` access at
#    all), and the single "Node number 1: ... observations" block with no
#    complexity-param suffix, no Primary/Surrogate splits sections.
# ---------------------------------------------------------------------------

def test_summary_rpart_root_only_tree_matches_r(capsys):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(minsplit=1000, xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)
    assert "Variable importance" not in r_lines

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"minsplit": 1000, "xval": 0})
    assert len(py_fit["frame"]) == 1  # sanity: really is root-only
    assert py_fit.get("variable.importance") is None
    py_lines, py_retval = capture_summary_rpart_lines(capsys, py_fit)

    assert py_retval is py_fit
    assert "Variable importance" not in py_lines
    _assert_cptable_values_match(py_fit, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)
    blocks = summary_rpart_node_blocks(py_lines)
    assert list(blocks.keys()) == [1]
    assert "complexity param" not in blocks[1][0]


# ---------------------------------------------------------------------------
# 2. `cp=` large enough to prune every split back to the root (cp=999), on
#    a fit that *did* originally have real splits (so `variable.importance`
#    is genuinely non-empty going in, unlike test 1 above) -- confirms the
#    "Variable importance" block still reflects the *whole original tree*
#    (it is computed once from `x$variable.importance`/
#    `x['variable_importance']`, independent of the `cp=`-driven `rows`
#    filter applied only to the node listing below it), while the node
#    listing itself collapses to just the root.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_prunes_everything_to_root(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, cp=999)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, cp=999)

    r_vi = summary_rpart_variable_importance_dict_r(r_lines)
    py_vi = summary_rpart_variable_importance_dict_py(py_lines)
    assert r_vi is not None and py_vi is not None and py_vi == r_vi

    assert_summary_node_blocks_match(py_lines, r_lines)
    blocks = summary_rpart_node_blocks(py_lines)
    assert list(blocks.keys()) == [1]
    assert "complexity param" not in blocks[1][0]


# ---------------------------------------------------------------------------
# 3. `cp=` negative: complexity is never <= a negative cp (complexity is
#    always >= 0 in a valid cptable), so *no* pruning happens beyond the
#    default `cp=0` behavior, on both sides -- confirmed via an explicit
#    sanity check against each side's own `cp=0`/omitted-cp output before
#    cross-comparing the two sides against each other.
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_negative_prunes_nothing(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines_default = r_summary_rpart_lines(r_fit)
    r_lines_neg = r_summary_rpart_lines(r_fit, cp=-1)
    assert r_lines_neg == r_lines_default  # sanity: R itself does no extra pruning

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines_default, _ = capture_summary_rpart_lines(capsys, py_fit)
    py_lines_neg, _ = capture_summary_rpart_lines(capsys, py_fit, cp=-1)
    assert py_lines_neg == py_lines_default  # sanity: python itself does no extra pruning either

    assert_summary_node_blocks_match(py_lines_neg, r_lines_neg)


# ---------------------------------------------------------------------------
# 4. `digits=1`: the smallest digits value R accepts without raising (see
#    test_summary_rpart_negative.py's digits=0 KNOWN GAP, where R *does*
#    raise). Confirms the node-block comparison still holds even at this
#    minimal precision, since `normalize_summary_line` re-parses every
#    formatted number back to a float rather than comparing formatted text
#    directly.
# ---------------------------------------------------------------------------

def test_summary_rpart_digits_minimal(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, digits=1)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, digits=1)

    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 5. `digits=15`: a large digits value (well beyond the R default of 7,
#    approaching double precision).
#
#    KNOWN, PERMANENT NUMERICAL-PRECISION GAP (distinct from the purely
#    cosmetic formatting gaps documented elsewhere): at this precision, the
#    "improve="/"agree="/"adj=" statistics themselves (not just how they are
#    *formatted*) disagree between R and python starting around the 8th
#    significant digit -- e.g. node 2's "Age" split improve is
#    0.68486352... in R's `fit$splits` vs 0.684863523573203 in python's,
#    a ~3e-9 relative difference -- confirmed empirically via Rscript.
#    This is far too small to matter at the default digits=7 (both round to
#    the same 7-sig-fig value, as test_summary_rpart_positive.py's tests
#    confirm), but digits=15 requests more precision than the two
#    independent split-evaluation implementations actually agree on, most
#    likely due to accumulated floating-point differences in summation
#    order between R's original Fortran/C routines and their python port.
#    So: the *structure* (node ids, split variable order/text) is asserted
#    exactly, while the numeric values themselves are compared with a
#    generous relative tolerance instead of `assert_summary_node_blocks_match`'s
#    exact (post-normalization) text equality.
# ---------------------------------------------------------------------------

_EDGE_NUM_RE = re.compile(r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?")


def _assert_node_blocks_match_with_numeric_tolerance(
    py_lines: list[str], r_lines: list[str], *, rtol: float = 1e-5
) -> None:
    """Like `assert_summary_node_blocks_match`, but tolerates small relative
    differences in the numeric tokens themselves (rather than requiring the
    rounded values to agree exactly) -- see the KNOWN GAP note above."""
    py_blocks = summary_rpart_node_blocks(py_lines)
    r_blocks = summary_rpart_node_blocks(r_lines)
    assert set(py_blocks.keys()) == set(r_blocks.keys())
    for node_id in r_blocks:
        py_block = py_blocks[node_id]
        r_block = r_blocks[node_id]
        assert len(py_block) == len(r_block)
        for py_line, r_line in zip(py_block, r_block):
            py_text = _EDGE_NUM_RE.sub("#", py_line.strip())
            r_text = _EDGE_NUM_RE.sub("#", r_line.strip())
            assert py_text.split() == r_text.split(), f"node {node_id}: {py_line!r} vs {r_line!r}"
            py_nums = [float(t) for t in _EDGE_NUM_RE.findall(py_line)]
            r_nums = [float(t) for t in _EDGE_NUM_RE.findall(r_line)]
            assert len(py_nums) == len(r_nums)
            np.testing.assert_allclose(py_nums, r_nums, rtol=rtol, atol=1e-6)


def test_summary_rpart_digits_large(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit, digits=15)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, digits=15)

    _assert_node_blocks_match_with_numeric_tolerance(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 6. `cp=` set exactly equal to a *real* internal node's own complexity
#    value: the `parent.cp > cp`/`parent_cp > cp` filter is a strict
#    inequality on both sides, so a node whose parent's complexity exactly
#    equals `cp` must be excluded, not included -- an off-by-one-prone
#    boundary. Node 2 of the default kyphosis classification tree has
#    complexity 0.01960784 (pulled directly off the python fit, not
#    hand-coded, so this stays correct even if upstream splitting logic
#    changes); using that value as `cp` should keep the root and its two
#    immediate children (whose parent is the root, complexity 0.1764706 >
#    cp) but drop every deeper node (whose parent's complexity, 0.01960784,
#    is not > cp).
# ---------------------------------------------------------------------------

def test_summary_rpart_cp_exactly_on_node_boundary(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    boundary_cp = float(py_fit["frame"].loc[2, "complexity"])
    assert boundary_cp == pytest.approx(0.01960784, abs=1e-6)

    r_lines = r_summary_rpart_lines(r_fit, cp=boundary_cp)
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit, cp=boundary_cp)

    assert_summary_node_blocks_match(py_lines, r_lines)
    blocks = summary_rpart_node_blocks(py_lines)
    assert set(blocks.keys()) == {1, 2, 3}


# ---------------------------------------------------------------------------
# 7. `maxsurrogate=0`: no surrogate splits are ever computed, so the
#    "Surrogate splits:" section must be entirely absent from every node
#    block on both sides (rather than merely empty) -- confirmed
#    empirically in R before writing this test.
# ---------------------------------------------------------------------------

def test_summary_rpart_no_surrogate_splits_section_when_maxsurrogate_zero(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, maxsurrogate=0)")
    r_lines = r_summary_rpart_lines(r_fit)
    assert not any("Surrogate splits" in line for line in r_lines)

    py_fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "maxsurrogate": 0}
    )
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)
    assert not any("Surrogate splits" in line for line in py_lines)

    _assert_cptable_values_match(py_fit, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 8. The na.action header's *complement*: a complete-case subset of
#    cu.summary (all rows with any NA dropped beforehand) has nothing for
#    na.rpart to omit, so the header must read "n=<n>" (no parenthetical)
#    rather than "n=<n> (<k> observations deleted ...)" -- the mirror image
#    of test_summary_rpart_positive.py's na.action test.
# ---------------------------------------------------------------------------

def test_summary_rpart_no_na_action_header_when_no_missingness(capsys):
    df = cu_summary_df().dropna().reset_index(drop=True)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)
    r_n_line = summary_rpart_find_n_line(r_lines)
    assert "deleted due to missingness" not in r_n_line

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 0}
    )
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)
    py_n_line = summary_rpart_find_n_line(py_lines)

    assert "deleted due to missingness" not in py_n_line
    # KNOWN, cosmetic-only gap (see test_printcp_positive.py's analogous gap
    # 6): R's cat(...) default sep=" " leaves "n= <k> " (extra spaces) in
    # this no-omission branch; summary_rpart.py's f-string has none.
    assert py_n_line.replace(" ", "") == r_n_line.replace(" ", "")
    _assert_cptable_values_match(py_fit, r_fit)
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 9. A tree deep enough to produce double-digit node ids (the default
#    kyphosis classification tree already reaches ids up to 23): a sanity
#    check that `summary_rpart_node_blocks`'s id-parsing/block-splitting
#    scales correctly to more than a handful of nodes, and that every one
#    of them agrees between the two sides.
# ---------------------------------------------------------------------------

def test_summary_rpart_many_nodes_double_digit_ids(capsys):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines = r_summary_rpart_lines(r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines, _ = capture_summary_rpart_lines(capsys, py_fit)

    r_blocks = summary_rpart_node_blocks(r_lines)
    assert len(r_blocks) >= 8
    assert max(r_blocks.keys()) >= 10  # a genuine double-digit node id is present
    assert_summary_node_blocks_match(py_lines, r_lines)


# ---------------------------------------------------------------------------
# 10. `file=` combined with non-default `cp=`/`digits=` (rather than the
#     defaults exercised in test_summary_rpart_positive.py's own file=
#     test): confirms the file-writing code path (python's
#     `contextlib.redirect_stdout`; R's `sink(file)`) threads those
#     parameters through identically to the stdout path, and that writing
#     to an *already-existing* file overwrites it rather than appending.
# ---------------------------------------------------------------------------

def test_summary_rpart_file_argument_with_non_default_cp_and_digits(capsys, tmp_path):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_lines_stdout = r_summary_rpart_lines(r_fit, cp=0.02, digits=3)
    r_file = tmp_path / "r_summary_edge.txt"
    r_file.write_text("PRE-EXISTING CONTENT THAT MUST BE OVERWRITTEN\n")
    run_r(f'summary(summary_fit_tmp, cp=0.02, digits=3, file="{r_file.as_posix()}")')
    r_lines_file = r_file.read_text().splitlines()
    assert r_lines_file == r_lines_stdout
    assert "PRE-EXISTING CONTENT" not in r_file.read_text()

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    py_lines_stdout, _ = capture_summary_rpart_lines(capsys, py_fit, cp=0.02, digits=3)
    py_file = tmp_path / "py_summary_edge.txt"
    py_file.write_text("PRE-EXISTING CONTENT THAT MUST BE OVERWRITTEN\n")
    retval = summary_rpart(py_fit, cp=0.02, digits=3, file=str(py_file))
    assert retval is py_fit
    py_lines_file = py_file.read_text().splitlines()
    assert py_lines_file == py_lines_stdout
    assert "PRE-EXISTING CONTENT" not in py_file.read_text()

    assert_summary_node_blocks_match(py_lines_file, r_lines_file)

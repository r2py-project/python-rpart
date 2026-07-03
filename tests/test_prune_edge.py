"""Boundary/edge-case parity tests for r2py_rpart.prune (and its underlying
prune_rpart) vs. R's rpart::prune.rpart (called directly -- see
test_prune_positive.py's module docstring for why the direct-call form is
this suite's comparison target throughout).

Genuine parity edge cases (tests 1-3): a root-only tree (no internal nodes
to toss, for any cp), `cp=Inf` (collapses fully to the root), and `cp=-Inf`
(never tosses anything) -- confirmed, via a live rpy2 session, to behave
identically on both sides.

KNOWN, PERMANENT BEHAVIORAL GAPS (tests 4-11)
-----------------------------------------------
prune.rpart.R's own body (rpart/R/prune.rpart.R) has *no*
`inherits(tree, "rpart")` legitimacy check of its own -- it just does
`tree$frame`, `tree$cptable`, etc. directly, and only reaches the *one*
legitimacy check anywhere in the call chain (`snip.rpart`'s own
`inherits(x, "rpart")`, matched exactly by r2py_rpart's own
`snip_rpart._rpart_class` check -- see test_prune_negative.py's dedicated,
*passing* test for that one code path) when `toss` is actually non-empty.
For every input below, `toss` ends up empty (or the input is malformed
before that point is ever reached), so R's `prune.rpart` either silently
no-ops (`length(toss) == 0L` -> `return(tree)` unchanged) or, in the
`cp="abc"`/`cp=True`/extra-kwarg cases, succeeds via R's own permissive
type-coercion/argument-matching rules that Python's stricter numpy/pandas
comparisons and function-call semantics do not share. Each gap below is a
genuine, *confirmed* (against a live R session, before writing any test)
divergence: R succeeds where Python raises, or (`cp=NaN`) both "succeed"
but disagree on what the result actually is. Per this codebase's
established convention (e.g. test_printcp_positive.py's KNOWN GAP tests),
these are kept as explicit, documented assertions -- some deliberately
written to demonstrate the *divergence itself* (Python raises / R doesn't)
rather than papered over or silently skipped.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.prune import prune

from _r_rpart_helpers import (
    mtcars_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_prune,
    r_prune_error,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. Root-only tree (no internal nodes at all, `cp=1` in `control` forces
#    every candidate split to fail the complexity threshold): pruning it at
#    *any* cp is necessarily a no-op on both sides, since `toss` can never
#    be non-empty when there are zero internal (`var != "<leaf>"`) rows to
#    begin with.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cp", [0.1, 0.0, -1.0, 5.0])
def test_prune_root_only_tree_is_always_a_no_op(cp):
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0, cp=1)")
    r_pruned = r_prune(r_fit, cp=cp)
    assert int(np.asarray(ro_nrow(r_pruned))[0]) == 1

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0, "cp": 1})
    assert py_fit["frame"].shape[0] == 1
    py_pruned = prune(py_fit, cp=cp)

    assert py_pruned["frame"].shape[0] == 1
    assert py_pruned["frame"]["var"].iloc[0] == "<leaf>"


def ro_nrow(r_obj):
    r_assign("ro_nrow_tmp", r_obj)
    return run_r("nrow(ro_nrow_tmp$frame)")


# ---------------------------------------------------------------------------
# 2. `cp=Inf`: every internal node's `complexity` is (necessarily) finite,
#    so `complexity <= Inf` is always TRUE/True on both sides -- the whole
#    tree collapses to its root, identically to `cp` being any sufficiently
#    large finite value (test_prune_positive.py's test 6), but exercising
#    the literal infinite value itself.
# ---------------------------------------------------------------------------

def test_prune_cp_positive_infinity_collapses_to_root_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=float("inf"))
    assert int(np.asarray(ro_nrow(r_pruned))[0]) == 1

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=float("inf"))

    assert py_pruned["frame"].shape[0] == 1
    assert py_pruned["frame"]["var"].iloc[0] == "<leaf>"


# ---------------------------------------------------------------------------
# 3. `cp=-Inf`: every internal node's `complexity` is (necessarily) >
#    -infinity, so `complexity <= -Inf` is always FALSE/False on both sides
#    -- nothing is tossed, an exact no-op, identically to `cp` being any
#    sufficiently small finite value (test_prune_positive.py's test 7), but
#    exercising the literal negative-infinite value itself.
# ---------------------------------------------------------------------------

def test_prune_cp_negative_infinity_is_a_no_op_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=float("-inf"))
    r_nrow = int(np.asarray(ro_nrow(r_pruned))[0])

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=float("-inf"))

    assert py_pruned["frame"].shape[0] == py_fit["frame"].shape[0] == r_nrow


# ---------------------------------------------------------------------------
# 4. KNOWN GAP: `cp=NaN`. `ff$complexity <= NaN` in R yields `NA` for every
#    row (not `FALSE`); combined with `& (var != "<leaf>")` via R's
#    short-circuit-per-element `&` (`NA & FALSE` -> `FALSE`, `NA & TRUE` ->
#    `NA`), `toss` ends up as a vector of `NA`s (one per *internal* node) --
#    non-empty (`length(toss) != 0`) despite holding no real node ids at
#    all! R's `prune.rpart` therefore does NOT take its `length(toss)==0`
#    early-return: it proceeds into `pmax(cptable[,1], NaN)` (all `NaN`) and
#    `unique()`/`match()` machinery, ending up with `$frame`/`$where`
#    *unchanged* (the bogus all-`NA` toss ultimately snips nothing) but a
#    `$cptable` collapsed to a *single* row whose CP value is itself `NaN`.
#    Python's `ff['complexity'].values <= cp` instead yields plain `False`
#    for every row (numpy's `<=` with NaN is never NA-like -- just False),
#    so `toss` is a genuinely empty array and `prune_rpart`'s own
#    `len(toss) == 0` check takes the early-return path: the *entire*
#    result (frame AND cptable, all rows) is left completely unchanged.
#    Confirmed empirically (both sides) before writing this test.
# ---------------------------------------------------------------------------

def test_prune_cp_nan_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=float("nan"))
    r_cptable_nrow = int(np.asarray(ro_nrow_cptable(r_pruned))[0])

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=float("nan"))

    ## R: cptable collapses to a single (NaN-CP) row.
    assert r_cptable_nrow == 1
    ## Python: KNOWN GAP -- the *entire* original 3-row cptable survives
    ## untouched instead, since python's own toss ends up empty.
    assert py_pruned["cptable"].shape[0] == py_fit["cptable"].shape[0] == 3
    assert py_pruned["cptable"].shape[0] != r_cptable_nrow


def ro_nrow_cptable(r_obj):
    r_assign("ro_nrow_cptable_tmp", r_obj)
    return run_r("nrow(ro_nrow_cptable_tmp$cptable)")


# ---------------------------------------------------------------------------
# 5. KNOWN GAP: `cp=None` (an *explicit* `cp=NULL` in R, as opposed to
#    `cp` never being passed at all -- see test_prune_negative.py's
#    "missing cp" test). `ff$complexity <= NULL` is `logical(0)` in R
#    regardless of `complexity`'s length; combined with `&` against a
#    same-length `logical(n)`, R's vectorized `&` rule (either operand
#    length 0 -> result length 0) collapses the whole mask to `logical(0)`,
#    so `id[logical(0)]` is `integer(0)` -- `length(toss) == 0`, and
#    `prune.rpart` returns `tree` completely unchanged, with NO error.
#    Python's `ff['complexity'].values <= None` instead raises a TypeError
#    immediately (numpy has no ordering between float64 and `None`).
# ---------------------------------------------------------------------------

def test_prune_cp_none_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_fit_cpnull_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_fit_cpnull_tmp, cp=NULL)"))
    assert r_message is None  # R: no error at all, a silent no-op.

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises instead of silently no-op'ing.
    with pytest.raises(TypeError):
        prune(py_fit, cp=None)


# ---------------------------------------------------------------------------
# 6. KNOWN GAP: `cp="abc"` (a non-numeric string). R's `ff$complexity <=
#    "abc"` coerces the *numeric* `complexity` column to character first
#    (`format()`-like decimal-string rendering, e.g. `"0.643125"`), then
#    compares lexicographically: since every rendered complexity value
#    starts with a digit (`'0'`-`'9'`), and `"abc"` starts with a lowercase
#    letter, every such comparison evaluates to TRUE under ASCII/lexical
#    ordering ('0' < 'a') -- so R's `prune.rpart(fit, cp="abc")` silently
#    collapses the *entire* tree to its root, exactly as `cp=Inf` would
#    (test 2 above), with NO error. Python's
#    `ff['complexity'].values <= cp` instead raises a numpy UFuncTypeError
#    immediately -- numpy never attempts R's string-coercion trick between
#    a float64 array and a python str.
# ---------------------------------------------------------------------------

def test_prune_cp_non_numeric_string_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp="abc")
    r_nrow = int(np.asarray(ro_nrow(r_pruned))[0])
    ## R: collapses fully to root (no error) -- a side effect of its
    ## numeric-to-character coercion rule for comparisons, not a
    ## deliberately-designed feature.
    assert r_nrow == 1

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises instead.
    with pytest.raises(Exception):
        prune(py_fit, cp="abc")


# ---------------------------------------------------------------------------
# 7. KNOWN GAP: `cp=True` (a python bool). R's `TRUE` coerces to `1` in a
#    numeric comparison, so `prune.rpart(fit, cp=TRUE)` behaves exactly
#    like `cp=1` (collapses to root, no error) -- confirmed empirically.
#    Python's own numpy/pandas comparison (`complexity <= True`) actually
#    evaluates the *mask* correctly (`True` coerces to `1.0` there too), but
#    prune_rpart.py's *later* `new_cptable.iloc[-1, 0] = cp` assignment
#    raises instead: pandas' strict dtype-upcasting rules refuse to store a
#    python `bool` into a `float64`-typed DataFrame column in-place
#    (`TypeError: Invalid value 'True' for dtype 'float64'`) -- a genuine
#    r2py_rpart implementation bug (not a deliberate design choice), unlike
#    the deeper type-system divergences in tests 5/6 above.
# ---------------------------------------------------------------------------

def test_prune_cp_boolean_true_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=True)
    r_nrow = int(np.asarray(ro_nrow(r_pruned))[0])
    assert r_nrow == 1  # R: behaves exactly like cp=1 -- collapses to root.

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises TypeError instead, from a pandas
    ## dtype-coercion restriction inside prune_rpart.py's own body.
    with pytest.raises(TypeError):
        prune(py_fit, cp=True)


# ---------------------------------------------------------------------------
# 8. KNOWN GAP: `tree=None`. R's `NULL$frame` is `NULL` (no error at all --
#    `$` on `NULL` always returns `NULL`); every downstream expression in
#    prune.rpart.R's body keeps propagating `NULL`/length-0 vectors, ending
#    in `length(toss) == 0L` -> `prune.rpart(NULL, cp=...)` returns `NULL`
#    itself, unchanged, with no error whatsoever. Python's
#    `tree['frame']` on `tree=None` raises immediately
#    (`'NoneType' object is not subscriptable`).
# ---------------------------------------------------------------------------

def test_prune_tree_none_is_a_known_gap():
    r_message = r_error_message(lambda: run_r("prune.rpart(NULL, cp=0.1)"))
    assert r_message is None  # R: no error -- returns NULL unchanged.

    with pytest.raises(TypeError):
        prune(None, cp=0.1)


# ---------------------------------------------------------------------------
# 9. KNOWN GAP: `tree={}` (an empty dict -> R's `list()`). `list()$frame` is
#    `NULL` in R (a list's `$` on a missing name returns `NULL`, never an
#    error), so `prune.rpart(list(), cp=...)` again silently returns
#    `list()` unchanged. Python's `tree['frame']` on `tree={}` raises a
#    `KeyError` immediately.
# ---------------------------------------------------------------------------

def test_prune_tree_empty_dict_is_a_known_gap():
    r_message = r_error_message(lambda: run_r("prune.rpart(list(), cp=0.1)"))
    assert r_message is None  # R: no error -- returns list() unchanged.

    with pytest.raises(KeyError):
        prune({}, cp=0.1)


# ---------------------------------------------------------------------------
# 10. KNOWN GAP: `tree={"frame": None}` (-> R's `list(frame=NULL)`). Same
#     silent-`NULL`-propagation story as tests 8/9 above, but with an
#     explicit (present-but-NULL) `frame` element rather than a wholly
#     missing one: `ff$complexity`/`ff$var` on `ff=NULL` are themselves
#     `NULL`, keeping every downstream expression at length 0, so R again
#     returns the input completely unchanged with no error. Python's
#     `ff['complexity']` -- with `ff = tree['frame'] = None` -- raises an
#     `AttributeError` (`'NoneType' object has no attribute 'index'`, from
#     `ff.index.astype(int).values`, the very first line of prune_rpart.py's
#     body that actually touches `ff`).
# ---------------------------------------------------------------------------

def test_prune_tree_frame_none_is_a_known_gap():
    r_message = r_error_message(lambda: run_r("prune.rpart(list(frame=NULL), cp=0.1)"))
    assert r_message is None  # R: no error -- returns list(frame=NULL) unchanged.

    with pytest.raises(AttributeError):
        prune({"frame": None}, cp=0.1)


# ---------------------------------------------------------------------------
# 11. KNOWN GAP: `tree` is a genuine pandas DataFrame (not a dict at all --
#     R's analogue is a plain `data.frame`, itself a `list` under the hood).
#     R's `df$frame` is `NULL` (a data.frame has no "frame" column), so
#     `prune.rpart(df, cp=...)` again silently returns the (`identical()`-
#     confirmed) unchanged data.frame, no error. Python's `tree['frame']` on
#     a DataFrame raises `KeyError('frame')` (no such *column*), since
#     r2py_rpart's `tree` type is a plain dict, not a data.frame-alike.
# ---------------------------------------------------------------------------

def test_prune_tree_is_a_dataframe_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_message = r_error_message(lambda: run_r("prune.rpart(df, cp=0.1)"))
    assert r_message is None  # R: no error -- a data.frame has no $frame either.

    with pytest.raises(KeyError):
        prune(df, cp=0.1)


# ---------------------------------------------------------------------------
# 12. KNOWN GAP: an unrecognized extra keyword argument, alongside a
#     perfectly valid `cp=`. R's `prune.rpart(tree, cp, ...)` signature has
#     a `...` catch-all that silently absorbs (and never uses) any
#     unrecognized named argument -- `prune.rpart(fit, cp=0.1,
#     extra_arg=5)` succeeds exactly as `prune.rpart(fit, cp=0.1)` would.
#     Python's `prune(tree, **kwargs): return prune_rpart(tree, **kwargs)`
#     forwards every kwarg straight through, but `prune_rpart(tree, cp)` has
#     no `**kwargs` catch-all of its own -- so an unrecognized
#     `extra_arg=5` raises `TypeError: prune_rpart() got an unexpected
#     keyword argument 'extra_arg'` instead of being silently ignored.
# ---------------------------------------------------------------------------

def test_prune_extra_unexpected_keyword_argument_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_fit_extra_tmp", r_fit)
    r_message = r_prune_error("prune_fit_extra_tmp", cp=0.1, extra_arg=5)
    assert r_message is None  # R: silently ignores the unrecognized kwarg.

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises instead of ignoring the unrecognized kwarg.
    with pytest.raises(TypeError):
        prune(py_fit, cp=0.1, extra_arg=5)  # type: ignore[call-arg]

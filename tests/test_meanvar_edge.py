"""Boundary/edge-case parity tests for r2py_rpart.meanvar vs. R's `meanvar`
(dispatching to `meanvar.rpart`).

These probe the functional limits of meanvar.rpart's transformation:

    frame <- frame[frame$var == "<leaf>", ]
    x <- frame$yval
    y <- frame$dev/frame$n
    label <- row.names(frame)
    plot(x, y, xlab = xlab, ylab = ylab, type = "n", ...)
    text(x, y, label)
    invisible(list(x = x, y = y, label = label))

-- an empty leaf set, a single leaf, `n == 0` (division by zero), `dev == 0`
(a "pure"/zero-deviance leaf), NaN/Inf values, very large/small magnitudes,
and duplicate `yval`s across leaves.

*** KNOWN GAP (python raises, R does not) ***
Confirmed empirically (see tests/_r_rpart_helpers.py's meanvar-specific
plumbing module docstring): whenever the derived `x` (`yval`) or `y`
(`dev/n`) contains a non-finite value (NaN from a `0/0` node, or +-Inf),
R's `plot(x, y, ..., type = "n")` still succeeds -- R's `plot.window` computes
the axis range tolerating non-finite values mixed in with finite ones -- and
meanvar.rpart returns its full `list(x=, y=, label=)` normally. r2py_rpart's
`ax.set_xlim(x.min(), x.max())`/`ax.set_ylim(y.min(), y.max())` calls,
however, raise `ValueError: Axis limits cannot be NaN or Inf` (matplotlib
validates its limits strictly) whenever *any* value fed to `.min()`/`.max()`
is non-finite (`numpy`'s `min`/`max` propagate NaN, and `Inf` is itself a
valid-but-degenerate axis bound only for finite `min`/`max` calls, not when
paired with a NaN elsewhere in the same array) -- so r2py_rpart.meanvar()
raises before ever returning, in several of the cases below. Each such test
is marked "KNOWN GAP" explicitly and asserts the *actual, divergent*
behavior on each side, rather than papering over the difference.

An analogous, but *unconditional* KNOWN GAP applies to a genuinely empty
leaf set (`x`/`y` both length 0): both sides raise there (R's `min(x)`/
`max(x)` on a length-0 vector emit a warning and return +-Inf, so `plot()`'s
own xlim ends up `[Inf, -Inf]`, itself non-finite, triggering R's *own*
"need finite 'xlim' values" error; python's `x.min()` on an empty array
raises `ValueError` directly) -- so that one test passes without a
warning, both sides simply raise (for related, though not identically
worded, reasons).
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.meanvar_rpart import meanvar

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    build_meanvar_tree,
    call_meanvar_and_extract,
    r_meanvar_error,
    r_meanvar_like_expr,
    r_meanvar_result,
    r_meanvar_runs_without_error,
)


# ---------------------------------------------------------------------------
# 1. Empty leaf set (no "<leaf>" rows at all, e.g. a frame consisting
#    entirely of internal-node rows) -- both sides raise.
# ---------------------------------------------------------------------------

def test_meanvar_no_leaf_rows_raises_on_both_sides():
    var, yval, dev, n, index = ["x1", "x2"], [10.0, 5.0], [50.0, 20.0], [10.0, 5.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    with pytest.raises(ValueError):
        call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_msg = r_meanvar_error(r_expr, generic=True)
    assert r_msg is not None  # R: min(numeric(0))/max(numeric(0)) -> +-Inf -> "need finite 'xlim' values"


# ---------------------------------------------------------------------------
# 2. Singleton leaf (root-only tree, `nsplit == 0`) -- the minimal
#    non-degenerate, non-erroring case.
# ---------------------------------------------------------------------------

def test_meanvar_singleton_leaf_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [20.0], [50.0], [10.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"] == ["1"]
    # a singleton point still gets valid, finite xlim/ylim -- matplotlib
    # auto-expands an identical low/high pair with its own small margin
    # (emitting a UserWarning) rather than leaving it exactly zero-width, so
    # only containment (not exact equality) is asserted here.
    assert py_out["xlim"][0] <= 20.0 <= py_out["xlim"][1]
    assert py_out["ylim"][0] <= 5.0 <= py_out["ylim"][1]


# ---------------------------------------------------------------------------
# 3. `n == 0` for one leaf, with `dev == 0` too (a `0/0` node) -- `y` for
#    that leaf is NaN. *** KNOWN GAP: R succeeds, python raises. ***
# ---------------------------------------------------------------------------

def test_meanvar_n_zero_dev_zero_produces_nan_known_gap():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [1.0, 2.0], [0.0, 5.0], [0.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)  # R's real meanvar() succeeds despite the NaN
    r_out = r_meanvar_result(r_expr)
    assert_allclose(r_out["x"], [1.0, 2.0])
    assert np.isnan(r_out["y"][0])
    assert_allclose(r_out["y"][1], 2.5)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # numpy's own NaN-in-min/max warning
        with pytest.raises(ValueError, match="NaN or Inf"):
            call_meanvar_and_extract(tree)  # KNOWN GAP: matplotlib rejects the NaN-valued ylim


# ---------------------------------------------------------------------------
# 4. `n == 0` with a nonzero `dev` (finite division-by-zero: `dev/0`
#    produces +Inf) -- for a leaf with a *positive* `dev`.
#    *** KNOWN GAP: R succeeds, python raises. ***
# ---------------------------------------------------------------------------

def test_meanvar_n_zero_nonzero_dev_produces_inf_known_gap():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [1.0, 2.0], [5.0, 5.0], [0.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)
    r_out = r_meanvar_result(r_expr)
    assert np.isposinf(r_out["y"][0])
    assert_allclose(r_out["y"][1], 2.5)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        with pytest.raises(ValueError, match="NaN or Inf"):
            call_meanvar_and_extract(tree)


# ---------------------------------------------------------------------------
# 5. `yval == Inf` for one leaf, paired with a NaN `dev` elsewhere --
#    exercises non-finite *x* values (as opposed to non-finite *y*).
#    *** KNOWN GAP: R succeeds, python raises. ***
# ---------------------------------------------------------------------------

def test_meanvar_inf_yval_and_nan_dev_known_gap():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [np.inf, 2.0], [1.0, np.nan], [1.0, 1.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)
    r_out = r_meanvar_result(r_expr)
    assert np.isposinf(r_out["x"][0])
    assert_allclose(r_out["x"][1], 2.0)
    assert_allclose(r_out["y"][0], 1.0)
    assert np.isnan(r_out["y"][1])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        with pytest.raises(ValueError, match="NaN or Inf"):
            call_meanvar_and_extract(tree)


# ---------------------------------------------------------------------------
# 6. All leaves share the exact same `yval` (a degenerate, zero-width `x`
#    range) -- both sides must tolerate `xlim`/`ylim` collapsing to a single
#    point on the x-axis while y varies.
# ---------------------------------------------------------------------------

def test_meanvar_duplicate_yval_across_leaves_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [7.0, 7.0, 7.0], [2.0, 4.0, 6.0], [2.0, 2.0, 2.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    # matplotlib auto-expands the degenerate (identical low/high) xlim with
    # its own small margin rather than leaving it exactly zero-width.
    assert py_out["xlim"][0] <= 7.0 <= py_out["xlim"][1]


# ---------------------------------------------------------------------------
# 7. Very large magnitude values (near float64's practical range for this
#    kind of quantity) -- confirms no overflow/precision-loss divergence.
# ---------------------------------------------------------------------------

def test_meanvar_very_large_magnitude_values_matches_r():
    var, yval, dev, n = ["<leaf>", "<leaf>"], [1e300, -1e300], [1e300, 1e150], [1.0, 1.0]
    index = [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-12)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-12)


# ---------------------------------------------------------------------------
# 8. Very small (near-zero, subnormal-adjacent) magnitude values --
#    confirms no underflow divergence at the opposite numeric extreme.
# ---------------------------------------------------------------------------

def test_meanvar_very_small_magnitude_values_matches_r():
    var, yval, dev, n = ["<leaf>", "<leaf>"], [1e-300, 2e-300], [1e-310, 5e-320], [1.0, 1.0]
    index = [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-8, atol=1e-320)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8, atol=1e-320)


# ---------------------------------------------------------------------------
# 9. `n` a fractional (non-integer) weight sum -- rpart frames carry `n` as
#    an observation *count* in the ordinary case, but weighted fits can
#    produce a fractional effective `n`; the `dev/n` division must still
#    match exactly.
# ---------------------------------------------------------------------------

def test_meanvar_fractional_n_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [4.0, 9.0], [3.0, 6.0], [2.5, 3.75], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-12)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-12)


# ---------------------------------------------------------------------------
# 10. `dev == 0` for every leaf, with nonzero `n` (a set of "pure"
#     zero-deviance leaves, e.g. every observation at that node identical)
#     -- `y` is exactly 0.0 throughout, a legitimate non-error boundary
#     distinct from the `n == 0` division-by-zero cases above.
# ---------------------------------------------------------------------------

def test_meanvar_all_zero_deviance_leaves_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [1.0, 2.0, 3.0], [0.0, 0.0, 0.0], [4.0, 5.0, 6.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["y"], [0.0, 0.0, 0.0])
    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    # matplotlib auto-expands the degenerate (identical low/high, here both
    # exactly 0.0) ylim with its own small margin rather than leaving it
    # exactly zero-width.
    assert py_out["ylim"][0] <= 0.0 <= py_out["ylim"][1]


# ---------------------------------------------------------------------------
# 11. A large node index (label) value -- node numbers grow as powers of 2
#     with tree depth, so a deep tree can have 3+ digit node ids; confirms
#     the string-labeling (`row.names(frame)` / `frame.index.astype(str)`)
#     matches for large indices too, not just small ones.
# ---------------------------------------------------------------------------

def test_meanvar_large_node_index_label_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [1.0, 2.0], [1.0, 2.0], [1.0, 1.0], [1024, 2047]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert py_out["label"] == r_out["label"] == ["1024", "2047"]


# ---------------------------------------------------------------------------
# 12. `xlab`/`ylab` given as empty strings -- a boundary on the *label*
#     parameters themselves (as opposed to the numeric frame contents).
# ---------------------------------------------------------------------------

def test_meanvar_empty_string_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [1.0], [1.0], [1.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree, xlab="", ylab="")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, xlab="", ylab="")
    r_out = r_meanvar_result(r_expr, xlab="", ylab="")

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == ""
    assert py_out["ylabel"] == ""

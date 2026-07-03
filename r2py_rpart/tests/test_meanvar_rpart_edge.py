"""Boundary/edge-case parity tests for r2py_rpart's `meanvar_rpart` function
itself, called *directly*, vs. R's `meanvar.rpart`.

The functional edges of meanvar.rpart's own data transformation (empty leaf
sets, `n == 0`, NaN/Inf, duplicate yvals, very large/small magnitudes, large
node indices, empty-string labels, ...) are already exhaustively covered in
test_meanvar_edge.py via the public `meanvar()` entry point -- since
`meanvar(tree, **kwargs)` is a pure one-line pass-through to
`meanvar_rpart(tree, **kwargs)`, that coverage applies to meanvar_rpart's
transformation logic identically. This file does not re-derive those cases;
it targets edges that are specific to meanvar_rpart's own *concrete
signature* -- `(tree, xlab="ave(y)", ylab="ave(deviance)", **kwargs)`, with
real positional-or-keyword xlab/ylab parameters that meanvar()'s own `(tree,
**kwargs)` signature cannot expose at all -- combined with a couple of the
transformation-level edges above, to confirm the positional-argument path
itself doesn't introduce any *additional* divergence beyond what's already
documented.

See tests/_r_rpart_helpers.py's `call_meanvar_rpart_and_extract()` (added
alongside this task) for the direct meanvar_rpart-calling, positional-arg-
forwarding counterpart to the pre-existing `call_meanvar_and_extract()`.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart.meanvar_rpart import meanvar_rpart

from _r_rpart_helpers import (
    build_meanvar_tree,
    call_meanvar_rpart_and_extract,
    r_meanvar_like_expr,
    r_meanvar_result,
    r_meanvar_runs_without_error,
)


# ---------------------------------------------------------------------------
# 1. Non-string (numeric) xlab/ylab, supplied *positionally* -- neither
#    meanvar_rpart.py nor R's plot()/text() machinery validates that
#    xlab/ylab are actually strings; both sides accept a bare number and
#    stringify it for display (python via matplotlib's Text objects, R via
#    its own title()/mtext() coercion).
# ---------------------------------------------------------------------------

def test_meanvar_rpart_numeric_positional_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, 42, 99)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, xlab=42, ylab=99, generic=False)
    r_out = r_meanvar_result(r_expr, xlab=42, ylab=99, generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == "42"
    assert py_out["ylabel"] == "99"


# ---------------------------------------------------------------------------
# 2. Boolean xlab/ylab (Python `bool`/R `TRUE`/`FALSE`), positionally --
#    another non-string-label boundary, distinct from the plain-numeric case
#    above (Python's `bool` is a subtype of `int`, so this also exercises
#    `isinstance`/formatting edge behavior that a plain int wouldn't).
# ---------------------------------------------------------------------------

def test_meanvar_rpart_boolean_positional_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, True, False)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, xlab=True, ylab=False, generic=False)
    r_out = r_meanvar_result(r_expr, xlab=True, ylab=False, generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == "True"
    assert py_out["ylabel"] == "False"


# ---------------------------------------------------------------------------
# 3. Exactly 3 positional arguments (tree, xlab, ylab) -- the maximum
#    meanvar_rpart's signature accepts positionally (a 4th raises TypeError,
#    see test_meanvar_rpart_negative.py) -- confirms this upper boundary
#    itself is accepted cleanly, not just "fewer than 4".
# ---------------------------------------------------------------------------

def test_meanvar_rpart_exactly_three_positional_arguments_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "x3", "y3")  # 3 total positional args to meanvar_rpart

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="x3", ylab="y3", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == "x3"
    assert py_out["ylabel"] == "y3"


# ---------------------------------------------------------------------------
# 4. Empty-string labels, supplied positionally rather than by keyword (the
#    keyword-only form of this boundary is already covered in
#    test_meanvar_edge.py via meanvar()).
# ---------------------------------------------------------------------------

def test_meanvar_rpart_empty_string_positional_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [1.0], [1.0], [1.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "", "")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, xlab="", ylab="", generic=False)
    r_out = r_meanvar_result(r_expr, xlab="", ylab="", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == ""
    assert py_out["ylabel"] == ""


# ---------------------------------------------------------------------------
# 5. Singleton leaf (root-only tree), positional labels -- the minimal
#    non-degenerate frame, combined with the positional-argument path.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_singleton_leaf_positional_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [20.0], [50.0], [10.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "single x", "single y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="single x", ylab="single y", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"] == ["1"]
    assert py_out["xlim"][0] <= 20.0 <= py_out["xlim"][1]


# ---------------------------------------------------------------------------
# 6. Large node-index labels, positionally-supplied xlab/ylab -- confirms
#    the string-labeling path (`frame.index.astype(str)`) is unaffected by
#    which argument-binding route xlab/ylab took to get there.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_large_node_index_positional_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [1.0, 2.0], [1.0, 2.0], [1.0, 1.0], [1024, 2047]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "deep x", "deep y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="deep x", ylab="deep y", generic=False)

    assert py_out["label"] == r_out["label"] == ["1024", "2047"]
    assert py_out["xlabel"] == "deep x"
    assert py_out["ylabel"] == "deep y"


# ---------------------------------------------------------------------------
# 7. `n == 0`/NaN-producing leaf (the `dev/n == 0/0` KNOWN GAP already
#    documented in test_meanvar_edge.py for the meanvar() wrapper),
#    re-exercised through meanvar_rpart's direct positional-argument call --
#    confirms the positional-argument-binding path doesn't itself change
#    which side raises for this pre-existing, documented divergence.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_positional_labels_nan_dev_known_gap():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [1.0, 2.0], [0.0, 5.0], [0.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, xlab="nan x", ylab="nan y", generic=False)
    r_out = r_meanvar_result(r_expr, xlab="nan x", ylab="nan y", generic=False)
    assert np.isnan(r_out["y"][0])
    assert_allclose(r_out["y"][1], 2.5)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        with pytest.raises(ValueError, match="NaN or Inf"):
            call_meanvar_rpart_and_extract(tree, "nan x", "nan y")  # KNOWN GAP: matplotlib rejects NaN ylim


# ---------------------------------------------------------------------------
# 8. `xlab`/`ylab` passed positionally as `None` -- note this is distinct
#    from *omitting* xlab/ylab (which uses meanvar_rpart's own string
#    defaults): explicitly supplying `None`/R `NULL` overrides those
#    defaults with an actual null value, which both plot()/title() (R) and
#    matplotlib's Axes (python) tolerate as "no label" rather than erroring.
#    `r_meanvar_call_code()`'s own `xlab=None` means "omit the argument
#    entirely" (so its usual `r_meanvar_result(..., xlab=None, ...)` helper
#    call is unusable here, since it would omit xlab rather than pass NULL);
#    R's explicit-`NULL` call is therefore built directly below instead.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_positional_none_labels_matches_r():
    from _r_rpart_helpers import _r_meanvar_in_null_device, run_r

    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, None, None)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    call_code = f"rpart:::meanvar.rpart({r_expr}, xlab=NULL, ylab=NULL)"
    _r_meanvar_in_null_device(f"meanvar_rpart_none_tmp <- {call_code}")  # confirms R does not raise
    result = run_r("meanvar_rpart_none_tmp")
    r_x = np.asarray(result.rx2("x"), dtype=float)
    r_y = np.asarray(result.rx2("y"), dtype=float)

    assert_allclose(py_out["x"], r_x)
    assert_allclose(py_out["y"], r_y)
    assert py_out["xlabel"] == ""  # matplotlib renders a None label as an empty string
    assert py_out["ylabel"] == ""

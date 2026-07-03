"""Boundary/edge-case parity tests for r2py_rpart.plot_rpart vs. R's
`plot.rpart`.

See test_plot_rpart_positive.py's module docstring for the general
comparison strategy (`_r_rpart_helpers.r_plot_rpart_derived()` as the R-side
oracle, `_r_rpart_helpers.call_plot_rpart_and_extract()` as the python-side
extractor) and test_plot_rpart_negative.py's for the two explicit `stop()`/
`raise` guards in plot.rpart.R/plot_rpart.py.

KNOWN, GENUINE BUG (not a permanent/documented divergence) FOUND WHILE
WRITING THESE TESTS
--------------------------------------------------------------------------
`test_plot_rpart_compress_deep_asymmetric_tree_known_bug` below demonstrates
a real correctness bug in `r2py_rpart/rpartco.py`'s `compress()` helper (used
whenever `plot_rpart(..., compress=True)`), independent of plot_rpart.py
itself. In rpartco.R's own `compress()`, the branch taken when the *right*
subtree is at least as deep as the left one is:

    } else {
        templ <- right$left  - slide
        tempr <- right$right - slide
        templ[1L:mind] <- pmin(templ[1L:mind], left$left)
    }

but rpartco.py's `compress()` (the else branch of `if left["depth"] >
right["depth"]:`) instead reads:

    else:
        templ = left["left"].copy() - slide
        tempr = right["right"].copy() - slide
        templ[0:mind] = np.minimum(templ[0:mind], left["left"])

i.e. `templ` is built from `left["left"]` instead of `right["left"]`. For
small/shallow/symmetric trees this substitution happens to not be observed
(every `mind` computed along the recursion stays at 1, so only the
always-correctly-computed index-0 entry of each boundary vector is ever
read) -- which is why `test_plot_rpart_positive.py`'s own
`test_plot_rpart_compress_default_nspace`/`..._explicit_nspace_overrides_default`
tests (on a shallow, 9-row kyphosis tree) pass cleanly despite exercising
this same code path. But for a deeper, more asymmetric tree (below: 33 rows,
up to depth 5), the substitution corrupts the *length* of the boundary
vectors threaded back up the recursion, ultimately causing a numpy
broadcasting `ValueError` inside `compress()` -- confirmed below to NOT
happen on the R side, where R's own `compress()` computes a valid, finite
result for the exact same tree. This is filed here as a regression-anchor:
once rpartco.py's `compress()` is corrected, this test should start passing
without any other changes.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart
from r2py_rpart.plot_rpart import plot_rpart

from _r_rpart_helpers import (
    call_plot_rpart_and_extract,
    extract_frame_arrays,
    kyphosis_df,
    r_plot_rpart_derived,
    r_plot_rpart_error,
    r_plot_rpart_runs_without_error,
    r_rpart_like_expr_for_plot,
)


def _assert_matches_derivation(py_out: dict, r_out: dict) -> None:
    np.testing.assert_allclose(py_out["retval"]["x"], r_out["x"], atol=1e-9)
    np.testing.assert_allclose(py_out["retval"]["y"], r_out["y"], atol=1e-9)
    np.testing.assert_allclose(py_out["xlim"], r_out["xlim"], atol=1e-9)
    np.testing.assert_allclose(py_out["ylim"], r_out["ylim"], atol=1e-9)
    np.testing.assert_allclose(py_out["line_x"], r_out["branch_x"], equal_nan=True, atol=1e-9)
    np.testing.assert_allclose(py_out["line_y"], r_out["branch_y"], equal_nan=True, atol=1e-9)


# ---------------------------------------------------------------------------
# 1. The smallest possible *legitimate* (non-root-only) tree: exactly 3
#    frame rows (one split, both children leaves) -- one node above the
#    `nrow(x$frame) <= 1L` boundary tested in test_plot_rpart_negative.py.
# ---------------------------------------------------------------------------

def test_plot_rpart_minimal_legitimate_tree_three_rows():
    frame = pd.DataFrame(
        {"var": ["Start", "<leaf>", "<leaf>"], "dev": [8.0, 0.0, 0.0]}, index=[1, 2, 3]
    )
    fit = {"frame": frame}
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(fit)
    r_out = r_plot_rpart_derived(node, var, dev)
    _assert_matches_derivation(py_out, r_out)
    assert len(py_out["retval"]["x"]) == 3

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr)


# ---------------------------------------------------------------------------
# 2. branch=0 exactly is the documented lower boundary ("Any number from 0
#    to 1 is allowed. A value of 1 gives square shouldered branches, a value
#    of 0 give V shaped branches"). Confirms rpart.branch.R's `temp <-
#    (x[sibling] - x[is.left]) * (1 - branch)/2` collapses to the full
#    sibling-to-self gap (a pure V, no horizontal shoulder) and that no root
#    "|" glyph is drawn (`if (branch > 0)`), matching test_plot_rpart_
#    positive.py's dedicated branch=0 test but phrased as a boundary check.
# ---------------------------------------------------------------------------

def test_plot_rpart_branch_lower_boundary_zero():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(fit, branch=0)
    r_out = r_plot_rpart_derived(node, var, dev, branch=0)
    _assert_matches_derivation(py_out, r_out)
    assert len(py_out["texts"]) == 0

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, branch=0)


# ---------------------------------------------------------------------------
# 3. branch=1 is the documented *upper* boundary ("A value of 1 gives square
#    shouldered branches"). Confirms the branch temp offset collapses to 0
#    (pure square shoulders) on both sides, and the root "|" glyph IS drawn.
# ---------------------------------------------------------------------------

def test_plot_rpart_branch_upper_boundary_one():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(fit, branch=1)
    r_out = r_plot_rpart_derived(node, var, dev, branch=1)
    _assert_matches_derivation(py_out, r_out)
    assert len(py_out["texts"]) == 1

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, branch=1)


# ---------------------------------------------------------------------------
# 4. branch values *outside* the documented [0, 1] range (1.5 and -0.5) are
#    not validated/rejected by either side (plot.rpart.Rd only *documents*
#    the 0-1 range; neither plot.rpart.R nor plot_rpart.py actually enforce
#    it) -- both sides silently compute an (unusual but well-defined,
#    non-crashing) geometry for values outside that range, and still agree
#    with each other numerically.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch", [1.5, -0.5])
def test_plot_rpart_branch_outside_documented_range_still_matches(branch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(fit, branch=branch)
    r_out = r_plot_rpart_derived(node, var, dev, branch=branch)
    _assert_matches_derivation(py_out, r_out)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, branch=branch)


# ---------------------------------------------------------------------------
# 5. uniform=True documents that minbranch "is ignored if uniform=TRUE".
#    Confirms varying minbranch across its own extremes (0.0 vs 1.0) leaves
#    the y-coordinates completely unchanged once uniform=True, on both
#    sides -- the fudge-factor computation is dev-based and only reachable
#    from the non-uniform branch of rpartco.R/rpartco.py.
# ---------------------------------------------------------------------------

def test_plot_rpart_minbranch_ignored_when_uniform():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_low = call_plot_rpart_and_extract(fit, uniform=True, minbranch=0.0)
    py_high = call_plot_rpart_and_extract(fit, uniform=True, minbranch=1.0)
    np.testing.assert_allclose(py_low["retval"]["y"], py_high["retval"]["y"])

    r_low = r_plot_rpart_derived(node, var, dev, uniform=True, minbranch=0.0)
    r_high = r_plot_rpart_derived(node, var, dev, uniform=True, minbranch=1.0)
    np.testing.assert_allclose(r_low["y"], r_high["y"])
    np.testing.assert_allclose(py_low["retval"]["y"], r_low["y"])


# ---------------------------------------------------------------------------
# 6. Passing an explicit `nspace` while `compress=False` (the default) is
#    silently *ignored* on both sides -- plot.rpart.R's own
#    `if (!compress) nspace <- -1L` (and plot_rpart.py's identical
#    `if not compress: nspace = -1`) unconditionally overwrite whatever
#    `nspace` the caller passed once `compress` is falsy.
# ---------------------------------------------------------------------------

def test_plot_rpart_nspace_ignored_when_compress_false():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_with_nspace = call_plot_rpart_and_extract(fit, compress=False, nspace=5.0)
    py_without_nspace = call_plot_rpart_and_extract(fit, compress=False)
    np.testing.assert_allclose(py_with_nspace["retval"]["x"], py_without_nspace["retval"]["x"])

    r_out = r_plot_rpart_derived(node, var, dev, compress=False, nspace=5.0)
    np.testing.assert_allclose(py_with_nspace["retval"]["x"], r_out["x"])

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, compress=False, nspace=5.0)


# ---------------------------------------------------------------------------
# 7. margin=0 exactly is the documented default/lower boundary ("an extra
#    fraction of white space ... to leave"): with no padding at all, xlim/
#    ylim must equal the tight min/max range of the node coordinates
#    exactly, on both sides.
# ---------------------------------------------------------------------------

def test_plot_rpart_margin_zero_gives_tight_bounding_box():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(fit, margin=0)
    r_out = r_plot_rpart_derived(node, var, dev, margin=0)
    _assert_matches_derivation(py_out, r_out)

    xs = py_out["retval"]["x"]
    ys = py_out["retval"]["y"]
    assert py_out["xlim"] == pytest.approx((xs.min(), xs.max()))
    assert py_out["ylim"] == pytest.approx((ys.min(), ys.max()))


# ---------------------------------------------------------------------------
# 8. A degenerate, hand-built frame where every node's `dev` is identical
#    (0.0 throughout) drives rpartco's non-uniform y-computation to a
#    literal 0/0 in `y <- y / max(y)` (`max(y)` is exactly 0.0) -- both R's
#    and python's floating point arithmetic produce NaN (not an exception)
#    for 0.0/0.0, so this NaN must propagate identically into `y`, then into
#    `range(yy)`/`diff(range(yy))` for ylim, on both sides. R and numpy
#    disagree about whether this warrants a warning (R: "NaNs produced";
#    numpy: RuntimeWarning), but the *numeric* result (all-NaN) is identical
#    -- confirmed here directly (not routed through
#    call_plot_rpart_and_extract()/matplotlib, since NaN axis limits are
#    themselves rejected further downstream -- see the next test).
# ---------------------------------------------------------------------------

def test_plot_rpart_degenerate_zero_deviance_frame_produces_matching_nan():
    node = np.array([1.0, 2.0, 3.0])
    var = np.array(["X", "<leaf>", "<leaf>"])
    dev = np.array([0.0, 0.0, 0.0])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        r_out = r_plot_rpart_derived(node, var, dev)

    assert np.all(np.isnan(r_out["y"]))
    assert np.all(np.isnan(r_out["ylim"]))
    # x is unaffected (leaf x-positions are assigned independently of dev)
    np.testing.assert_allclose(r_out["x"], [1.5, 1.0, 2.0])


# ---------------------------------------------------------------------------
# 9. Continuing directly from the previous test: matplotlib itself refuses a
#    NaN axis limit (`ax.set_ylim(nan, nan)` raises `ValueError: Axis limits
#    cannot be NaN or Inf`), and R's own `plot.default(..., type="n")`
#    likewise refuses ("need finite 'ylim' values") for the exact same
#    degenerate frame -- both sides raise for this input (message wording
#    differs, exactly the "warn, don't fail" case from
#    test_plot_rpart_negative.py's protocol), even though this is not one of
#    plot.rpart's own two explicit legitimacy `stop()`s (it originates
#    inside the underlying plotting primitives on both sides instead).
# ---------------------------------------------------------------------------

def test_plot_rpart_degenerate_zero_deviance_frame_raises_on_both_sides():
    frame = pd.DataFrame({"var": ["X", "<leaf>", "<leaf>"], "dev": [0.0, 0.0, 0.0]}, index=[1, 2, 3])
    fit = {"frame": frame}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(Exception) as exc_info:
            plot_rpart(fit)

    x_expr = r_rpart_like_expr_for_plot(
        np.array([1.0, 2.0, 3.0]), np.array(["X", "<leaf>", "<leaf>"]), np.array([0.0, 0.0, 0.0])
    )
    r_msg = r_plot_rpart_error(x_expr, generic=False)
    assert r_msg is not None
    assert "finite" in r_msg.lower() or "nan" in r_msg.lower() or "inf" in r_msg.lower()


# ---------------------------------------------------------------------------
# 10. KNOWN, GENUINE BUG in rpartco.py's compress() (see module docstring
#     above): a deep, asymmetric tree (33 rows, up to depth 5, obtained by
#     over-fitting the kyphosis classification tree via a very small
#     `minsplit`/`cp`) with compress=True crashes r2py_rpart.plot_rpart()
#     with a numpy broadcasting ValueError, while R's own compress()
#     computes a valid, finite result for the identical tree (confirmed via
#     r_plot_rpart_derived() below, and via r_plot_rpart_runs_without_error()
#     against R's actual exported plot.rpart()). This test currently FAILS
#     (as an error, not an assertion failure) -- it is intentionally left
#     as a plain (non-xfail) assertion so it starts passing automatically
#     once rpartco.py's compress() is corrected.
# ---------------------------------------------------------------------------

def test_plot_rpart_compress_deep_asymmetric_tree_known_bug():
    df = kyphosis_df()
    fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class",
        control={"cp": 0.001, "minsplit": 2},
    )
    node, var, dev = extract_frame_arrays(fit)
    assert fit["frame"].shape[0] > 20  # a genuinely deep, asymmetric tree

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, compress=True)  # R: no crash
    r_out = r_plot_rpart_derived(node, var, dev, compress=True)
    assert np.all(np.isfinite(r_out["x"]))  # R's result is fully finite/valid

    # python currently raises inside rpartco.py's compress() for this exact
    # tree -- see the module docstring's root-cause analysis.
    py_out = call_plot_rpart_and_extract(fit, compress=True)
    _assert_matches_derivation(py_out, r_out)

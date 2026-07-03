"""Positive-path parity tests for r2py_rpart.plot_rpart vs. R's
`plot.rpart` (an S3 method for the `plot` generic, `S3method(plot, rpart)`
in rpart's NAMESPACE).

Unlike plotcp (a pure side-effect function that returns None on both
sides), plot.rpart *does* return a meaningful value on both sides:
R's `invisible(list(x = xx, y = yy))` vs. r2py_rpart.plot_rpart()'s own
`{"x": xx, "y": yy}` -- the node coordinates. So these tests compare:

  - r2py_rpart.plot_rpart()'s *returned* `{"x", "y"}` dict, plus everything
    it additionally plots, pulled back out of the `matplotlib.axes.Axes` it
    draws on via `_r_rpart_helpers.call_plot_rpart_and_extract()` (xlim/
    ylim, whether the axis frame was turned off, the single branch-line
    `ax.plot(...)` call's x/y data plus its color/linestyle/linewidth, and
    the root "|" glyph `ax.text(...)`); against

  - `_r_rpart_helpers.r_plot_rpart_derived()`, an R replica of
    rpartco.R + rpart.branch.R + plot.rpart.R's own derivation logic
    (copied line-for-line, omitting only the graphics calls themselves),
    run on the *same* `(node, var, dev)` triple extracted directly from a
    genuine r2py_rpart.rpart() fit's `frame` via `extract_frame_arrays()`.

Feeding the identical `(node, var, dev)` triple into both sides is
deliberate: R's and python's rpart() can pick different splits for the same
formula/data in general, so comparing plot.rpart()'s *coordinate-derivation*
logic is only meaningful when both sides start from the same tree structure
-- exactly analogous to test_plotcp_positive.py's cptable-feeding strategy.
Several tests additionally confirm, via `r_plot_rpart_runs_without_error()`/
`r_plot_rpart_retval()`, that R's *actual* exported `plot.rpart()` (reached
either through the `plot(fit, ...)` generic for genuine "rpart"-classed
objects, or directly via `rpart:::plot.rpart(...)` for the minimal
synthetic object built by `r_rpart_like_expr_for_plot()`) accepts the same
input/kwargs combination and returns the same node coordinates -- not just
that the hand-copied derivation replica agrees.

All parameters plot_rpart(x, uniform=, branch=, compress=, nspace=,
margin=, minbranch=, branch_col=, branch_lty=, branch_lwd=, ax=) are
exercised, individually and in combination, across the tests below.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.plot_rpart import plot_rpart
from r2py_rpart.zzz import rpart_env

from _r_rpart_helpers import (
    call_plot_rpart_and_extract,
    extract_frame_arrays,
    from_r_dataframe,
    kyphosis_df,
    r_plot_rpart_derived,
    r_plot_rpart_retval,
    r_plot_rpart_runs_without_error,
    r_rpart_like_expr_for_plot,
    run_r,
    stagec_df,
)


def _assert_matches_derivation(py_out: dict, r_out: dict) -> None:
    """The core comparison used throughout this file: everything
    plot_rpart.py returns/plots, pulled out of its return dict and the Axes
    via call_plot_rpart_and_extract(), against the R replica's derivation of
    the same (node, var, dev) triple."""
    np.testing.assert_allclose(py_out["retval"]["x"], r_out["x"], atol=1e-9)
    np.testing.assert_allclose(py_out["retval"]["y"], r_out["y"], atol=1e-9)
    np.testing.assert_allclose(py_out["xlim"], r_out["xlim"], atol=1e-9)
    np.testing.assert_allclose(py_out["ylim"], r_out["ylim"], atol=1e-9)
    np.testing.assert_allclose(py_out["line_x"], r_out["branch_x"], equal_nan=True, atol=1e-9)
    np.testing.assert_allclose(py_out["line_y"], r_out["branch_y"], equal_nan=True, atol=1e-9)
    assert py_out["axis_off"] is True
    assert py_out["n_lines"] == 1


# ---------------------------------------------------------------------------
# 1. A genuine classification fit (kyphosis), every argument left at its
#    documented default (uniform=False, branch=1, compress=False,
#    margin=0, minbranch=0.3, branch_col=1, branch_lty=1, branch_lwd=1).
#    Also cross-checks against R's *actual* plot(fit) return value (via a
#    minimal synthetic "rpart" object carrying the same frame), and confirms
#    the root "|" glyph is drawn (branch=1 > 0).
# ---------------------------------------------------------------------------

def test_plot_rpart_classification_kyphosis_all_defaults():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit)
    r_out = r_plot_rpart_derived(node, var, dev)
    _assert_matches_derivation(py_out, r_out)

    assert len(py_out["texts"]) == 1
    (tx, ty), text, ha, va = py_out["texts"][0]
    assert text == "|"
    assert ha == "center" and va == "center"
    assert tx == pytest.approx(py_out["retval"]["x"][0])
    assert ty == pytest.approx(py_out["retval"]["y"][0])

    assert py_out["line_color"] == "black"
    assert py_out["line_style"] == "-"
    assert py_out["line_width"] == 1.0

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr)
    r_retval = r_plot_rpart_retval(x_expr)
    np.testing.assert_allclose(py_out["retval"]["x"], r_retval["x"], atol=1e-9)
    np.testing.assert_allclose(py_out["retval"]["y"], r_retval["y"], atol=1e-9)


# ---------------------------------------------------------------------------
# 2. uniform=True on a regression (anova) fit (car.test.frame, Mileage ~
#    Weight) -- exercises rpartco.R's uniform-spacing branch, which ignores
#    `dev`/`minbranch` entirely and instead spaces nodes purely by depth.
# ---------------------------------------------------------------------------

def test_plot_rpart_uniform_spacing_anova_car_test_frame():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    assert fit["frame"].shape[0] > 1

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit, uniform=True)
    r_out = r_plot_rpart_derived(node, var, dev, uniform=True)
    _assert_matches_derivation(py_out, r_out)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, uniform=True)


# ---------------------------------------------------------------------------
# 3. branch=0 (V-shaped branches): plot.rpart.R's `if (branch > 0) text(...)`
#    guard means the root "|" glyph must be entirely absent, unlike the
#    branch=1 default case above.
# ---------------------------------------------------------------------------

def test_plot_rpart_branch_zero_omits_root_glyph():
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
# 4. An intermediate branch value (0.4, "other values being intermediate"
#    per plot.rpart.Rd) combined with margin=0.1 -- exercises both the
#    branch-shape interpolation in rpart.branch.R and plot.rpart.R's own
#    margin-padded xlim/ylim computation simultaneously.
# ---------------------------------------------------------------------------

def test_plot_rpart_intermediate_branch_with_margin():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit, branch=0.4, margin=0.1)
    r_out = r_plot_rpart_derived(node, var, dev, branch=0.4, margin=0.1)
    _assert_matches_derivation(py_out, r_out)

    # margin > 0 must actually widen the plot region relative to margin=0.
    py_out_no_margin = call_plot_rpart_and_extract(fit, branch=0.4, margin=0)
    assert py_out["xlim"][0] < py_out_no_margin["xlim"][0]
    assert py_out["xlim"][1] > py_out_no_margin["xlim"][1]

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, branch=0.4, margin=0.1)


# ---------------------------------------------------------------------------
# 5. compress=True with the default nspace (missing -> nspace <- branch,
#    per plot.rpart.R's `if (compress & missing(nspace)) nspace <- branch`)
#    on the same kyphosis fit -- this tree's shape happens to keep every
#    `compress()` recursion's `mind` at 1, so it does not trip the
#    rpartco.py `compress()` length bug documented/exercised in
#    test_plot_rpart_edge.py's `test_plot_rpart_compress_deep_asymmetric_tree_known_bug`.
# ---------------------------------------------------------------------------

def test_plot_rpart_compress_default_nspace():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit, compress=True)
    r_out = r_plot_rpart_derived(node, var, dev, compress=True)
    _assert_matches_derivation(py_out, r_out)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, compress=True)


# ---------------------------------------------------------------------------
# 6. compress=True with an *explicit* nspace different from branch --
#    confirms the override actually changes the output relative to the
#    default-nspace case above (nspace=0.5 vs. the default branch=1).
# ---------------------------------------------------------------------------

def test_plot_rpart_compress_explicit_nspace_overrides_default():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit, compress=True, nspace=0.5)
    r_out = r_plot_rpart_derived(node, var, dev, compress=True, nspace=0.5)
    _assert_matches_derivation(py_out, r_out)

    default_out = call_plot_rpart_and_extract(fit, compress=True)
    assert not np.allclose(py_out["retval"]["x"], default_out["retval"]["x"])

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, compress=True, nspace=0.5)


# ---------------------------------------------------------------------------
# 7. minbranch varied away from its 0.3 default (0.0 and 0.6) on the same
#    classification fit -- rpartco.R's "fudge factor" branch. Confirms both
#    that each value matches its own R derivation, and that the two
#    minbranch values actually produce *different* y-coordinates from one
#    another (i.e. the parameter is not silently ignored).
# ---------------------------------------------------------------------------

def test_plot_rpart_minbranch_varied():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_low = call_plot_rpart_and_extract(fit, minbranch=0.0)
    r_low = r_plot_rpart_derived(node, var, dev, minbranch=0.0)
    _assert_matches_derivation(py_low, r_low)

    py_high = call_plot_rpart_and_extract(fit, minbranch=0.6)
    r_high = r_plot_rpart_derived(node, var, dev, minbranch=0.6)
    _assert_matches_derivation(py_high, r_high)

    assert not np.allclose(py_low["retval"]["y"], py_high["retval"]["y"])

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr, minbranch=0.0)
    assert r_plot_rpart_runs_without_error(x_expr, minbranch=0.6)


# ---------------------------------------------------------------------------
# 8. branch_col/branch_lty/branch_lwd combinations that ARE covered by
#    plot_rpart.py's own col_map ({0:white,1:black,2:red,3:'#00CD00',
#    4:blue}, matching R's default palette entries 0-4) and lty_map
#    ({1:'-',2:'--',3:':',4:'-.'}) -- confirms these purely cosmetic
#    parameters (a) take effect on the drawn Line2D, and (b) never perturb
#    the underlying coordinate data.
#
#    Note branch_col/branch_lty are handled *asymmetrically* in
#    plot_rpart.py: `color = col_map.get(branch_col, branch_col) if
#    isinstance(branch_col, int) else branch_col` passes non-int colors
#    (e.g. a matplotlib-native string like "purple") straight through
#    unchanged, but `linestyle = lty_map.get(branch_lty, '-')` has no such
#    isinstance guard -- *any* branch_lty not in {1,2,3,4} (including a
#    matplotlib-native string like "dashed") silently falls back to '-'
#    (solid). The last parametrized case below pins this asymmetry exactly
#    (branch_col="purple" passes through, branch_lty="dashed" does not).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "branch_col,branch_lty,branch_lwd,expected_color,expected_style",
    [
        (2, 2, 2.5, "red", "--"),
        (3, 3, 0.5, "#00CD00", ":"),
        (4, 4, 1.0, "blue", "-."),
        ("purple", "dashed", 3.0, "purple", "-"),
    ],
)
def test_plot_rpart_branch_styling_combinations(
    branch_col, branch_lty, branch_lwd, expected_color, expected_style
):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    py_out = call_plot_rpart_and_extract(
        fit, branch_col=branch_col, branch_lty=branch_lty, branch_lwd=branch_lwd
    )
    r_out = r_plot_rpart_derived(node, var, dev)  # styling never affects coordinates
    _assert_matches_derivation(py_out, r_out)

    assert py_out["line_color"] == expected_color
    assert py_out["line_style"] == expected_style
    assert py_out["line_width"] == pytest.approx(branch_lwd)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(
        x_expr, branch_col=branch_col if isinstance(branch_col, int) else str(branch_col),
        branch_lty=branch_lty if isinstance(branch_lty, int) else str(branch_lty),
        branch_lwd=branch_lwd,
    )


# ---------------------------------------------------------------------------
# 9. A caller-supplied `ax=` (pre-created, e.g. one subplot in a larger
#    figure) produces identical coordinates/plotted data to letting
#    plot_rpart() create its own fresh Axes (ax=None) -- the `ax is None`
#    branch in plot_rpart.py only affects *where* the plot lands.
# ---------------------------------------------------------------------------

def test_plot_rpart_explicit_ax_matches_default_ax_creation():
    import matplotlib.pyplot as plt

    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    default_out = call_plot_rpart_and_extract(fit)

    fig, (ax1, ax2) = plt.subplots(1, 2)
    try:
        retval = plot_rpart(fit, ax=ax2)
        np.testing.assert_allclose(retval["x"], default_out["retval"]["x"])
        np.testing.assert_allclose(retval["y"], default_out["retval"]["y"])
        assert len(ax1.lines) == 0  # the untouched sibling axes stays empty
        assert len(ax2.lines) == 1
        np.testing.assert_allclose(ax2.lines[0].get_xdata(), default_out["line_x"], equal_nan=True)
        np.testing.assert_allclose(ax2.get_xlim(), default_out["xlim"])
        np.testing.assert_allclose(ax2.get_ylim(), default_out["ylim"])
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# 10. A method="poisson" (Surv()-style) fit on stagec, mirroring the
#     pre-built model-frame pattern test_printcp_positive.py/
#     test_plotcp_positive.py use for poisson/Surv fits -- broadens method
#     coverage beyond anova/class.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df, predictors):
    import pandas as pd

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


def test_plot_rpart_poisson_method_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]
    m = _stagec_prebuilt_model_frame(df, predictors)
    fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"maxsurrogate": 0, "cp": 0.02},
    )
    assert fit["frame"].shape[0] > 1

    node, var, dev = extract_frame_arrays(fit)
    py_out = call_plot_rpart_and_extract(fit)
    r_out = r_plot_rpart_derived(node, var, dev)
    _assert_matches_derivation(py_out, r_out)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    assert r_plot_rpart_runs_without_error(x_expr)


# ---------------------------------------------------------------------------
# 11. plot_rpart() records its resolved `parms` dict into the module-level
#     `rpart_env["device1"]` (mirroring R's own
#     `assign(paste0("device", dev.cur()), parms, envir = rpart_env)`) --
#     this is the mechanism rpartco()/rpart_branch() (and, in R, text.rpart/
#     rpart.branch) rely on when *not* given an explicit `parms`/`branch`.
# ---------------------------------------------------------------------------

def test_plot_rpart_records_parms_into_rpart_env():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    call_plot_rpart_and_extract(fit, uniform=True, branch=0.7, minbranch=0.1)
    parms = rpart_env["device1"]
    assert parms["uniform"] is True
    assert parms["branch"] == 0.7
    assert parms["minbranch"] == 0.1
    assert parms["nspace"] == -1  # compress=False (default) -> nspace forced to -1

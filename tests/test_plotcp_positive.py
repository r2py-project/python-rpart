"""Positive-path parity tests for r2py_rpart.plotcp vs. R's rpart::plotcp.

plotcp(x, minline=, lty=, col=, upper=, ...) is a pure side-effect plotting
function on *both* sides: R's own plotcp.R ends with `invisible()` (NULL),
and r2py_rpart.plotcp() returns None too -- see plotcp.py's `-> None`
signature. So there is no "return value" to directly diff. Instead, per this
test-generation task's own guidance ("focus comparisons on the underlying
numeric data it derives/plots ... rather than pixel-level graphical output"),
these tests compare:

  - r2py_rpart.plotcp()'s plotted data, pulled back out of the
    `matplotlib.axes.Axes` it draws on, via
    `_r_rpart_helpers.call_plotcp_and_extract()` (main line's (ns, xerror),
    ylim, bottom-axis cp tick labels, vlines error-bar segments, top-axis
    (twiny) tick labels, and the minline horizontal-line height); against

  - `_r_rpart_helpers.r_plotcp_derived_from_cptable()`, an R replica of
    plotcp.R's own derivation logic (copied line-for-line from
    rpart/R/plotcp.R, omitting only the graphics calls themselves), run on
    the *exact same* `cptable` matrix.

Feeding the identical `cptable` into both sides is deliberate: R's and
python's rpart() draw independent cross-validation folds for the same
formula/data (already noted as an incomparable, RNG-driven quantity in
test_printcp_positive.py), so comparing plotcp()'s *derivation logic* is
only meaningful when both sides start from the same numeric cptable -- which
is exactly what plotcp() is documented to operate on (see plotcp.Rd: "The
cptable in the fit contains the mean and standard deviation of the errors in
the cross-validated prediction ... and these are plotted by this
function"). Several tests below additionally confirm, via
`r_plotcp_runs_without_error()`, that R's *actual* exported `plotcp()`
function (not just the derivation replica) accepts the same `x`/kwargs
combination without raising -- i.e. that the synthetic inputs used are
genuinely within plotcp()'s documented domain, not just accepted by the
hand-copied replica.

KNOWN, PERMANENT FORMATTING-PARITY GAP
---------------------------------------
The bottom-axis `cp` tick labels (`as.character(signif(cp, 2))` in R;
plotcp.py's own `_signif()` + `str(v)`) are numerically identical on both
sides (confirmed via `r_plotcp_derived_from_cptable`/`call_plotcp_and_extract`
during this test suite's development), but their *string* rendering diverges
in two cases:
  (a) `Inf` (R) vs `inf` (python) -- always present for the very first cp
      value (`cp[0]` is always `sqrt(cp0[0] * Inf)` per plotcp.R's own
      `c(Inf, cp0[-length(cp0)])` construction, so this affects *every* test
      below with >= 1 row).
  (b) A whole-number rounded result, e.g. cp0 == 0 exactly: R's
      `as.character(0)` is `"0"`; python's `str(round(0.0, ...))` is
      `"0.0"` (a trailing ".0" Python's float-to-str always keeps for
      whole-valued floats, which R's character coercion does not).
Both are demonstrated/handled via `plotcp_cp_labels_match_modulo_known_gap()`
in tests/_r_rpart_helpers.py, used throughout this file (and
test_plotcp_edge.py) instead of raw list equality.

See tests/_r_rpart_helpers.py's "plotcp-specific plumbing" sections (both R-
and python-side) for all the shared machinery used below.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.plotcp import plotcp

from _r_rpart_helpers import (
    call_plotcp_and_extract,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    plotcp_cp_labels_match_modulo_known_gap,
    r_dataframe_assign,
    r_fit_rpart,
    r_plotcp_derived_from_cptable,
    r_plotcp_runs_without_error,
    r_rpart_like_expr,
    run_r,
    stagec_df,
)


def _assert_matches_derivation(py_out: dict, r_out: dict, *, check_top: bool, check_minline: bool) -> None:
    """The core comparison used throughout this file: everything
    plotcp.py plots, pulled out of the Axes via call_plotcp_and_extract(),
    against the R-formula replica's derivation of the same cptable."""
    assert py_out["retval"] is None  # mirrors R's own invisible()/NULL return
    np.testing.assert_allclose(py_out["ns"], r_out["ns"])
    np.testing.assert_allclose(py_out["xerror"], r_out["xerror"])
    np.testing.assert_allclose(py_out["ylim"], r_out["ylim"], rtol=1e-9, atol=1e-9)
    assert plotcp_cp_labels_match_modulo_known_gap(py_out["cp_labels"], r_out["cp_labels"])
    np.testing.assert_allclose(py_out["xerror_minus_std"], r_out["xerror"] - r_out["xstd"])
    np.testing.assert_allclose(py_out["xerror_plus_std"], r_out["xerror"] + r_out["xstd"])
    assert py_out["bottom_xlabel"] == "cp"
    assert py_out["bottom_ylabel"] == "X-val Relative Error"
    if check_top:
        assert py_out["top_labels"] == r_out["size_labels"] or py_out["top_labels"] == r_out["splits_labels"]
    else:
        assert py_out["top_labels"] is None
    if check_minline:
        assert py_out["minline_y"] == pytest.approx(r_out["minline_y"])
    else:
        assert py_out["minline_y"] is None


# ---------------------------------------------------------------------------
# 1. A genuine anova (regression) fit, built via r2py_rpart.rpart() on
#    car.test.frame (Mileage ~ Weight), xval=5 so the cptable carries real
#    xerror/xstd columns. Default plotcp() args throughout (minline=True,
#    lty=3, col=1, upper="size"). Also sanity-checks that R's *actual*
#    plotcp() accepts the equivalent fit object without raising.
# ---------------------------------------------------------------------------

def test_plotcp_anova_car_test_frame_default_args():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    np.random.seed(1)
    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 5})
    assert py_fit["cptable"].shape[1] == 5

    py_out = call_plotcp_and_extract(py_fit)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_plotcp_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)

    # Sanity: R's own *actual* plotcp() accepts this exact numeric cptable
    # (via a minimal synthetic "rpart" object) without raising.
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable_np))


# ---------------------------------------------------------------------------
# 2. A classification fit (kyphosis), upper="splits" instead of the default
#    "size" -- exercises the "number of splits" top-axis branch.
# ---------------------------------------------------------------------------

def test_plotcp_classification_kyphosis_upper_splits():
    df = kyphosis_df()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 5})
    assert py_fit["cptable"].shape[1] == 5

    py_out = call_plotcp_and_extract(py_fit, upper="splits")
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_plotcp_derived_from_cptable(cptable_np)

    assert py_out["top_labels"] == r_out["splits_labels"]
    assert py_out["top_xlabel"] == "number of splits"
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable_np), upper="splits")


# ---------------------------------------------------------------------------
# 3. A method="poisson" (Surv()-style) fit on stagec, mirroring the
#    pre-built model-frame pattern test_printcp_positive.py uses for
#    poisson/Surv fits. Default args again.
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


def test_plotcp_poisson_method_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]
    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 5, "maxsurrogate": 0, "cp": 0.02},
    )
    assert py_fit["cptable"].shape[1] == 5

    py_out = call_plotcp_and_extract(py_fit)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_plotcp_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)


# ---------------------------------------------------------------------------
# 4. minline=False: the 1SE horizontal line must be entirely absent (only
#    the main plotted line remains in ax.lines), everything else unchanged.
# ---------------------------------------------------------------------------

def test_plotcp_minline_false_omits_horizontal_line():
    df = cu_summary_df().dropna().reset_index(drop=True)
    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 5}
    )
    py_out = call_plotcp_and_extract(py_fit, minline=False)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_plotcp_derived_from_cptable(cptable_np)

    assert py_out["n_lines"] == 1  # only the main ns/xerror line
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=False)


# ---------------------------------------------------------------------------
# 5. upper="none": no top (twiny) axis is created at all -- the figure has
#    exactly one Axes.
# ---------------------------------------------------------------------------

def test_plotcp_upper_none_omits_top_axis():
    import matplotlib.pyplot as plt

    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.05, 2, 0.4, 0.55, 0.07],
            [0.01, 3, 0.3, 0.50, 0.06],
        ]
    )
    fig, ax = plt.subplots()
    try:
        retval = plotcp({"cptable": cptable}, ax=ax, upper="none")
        assert retval is None
        assert len(fig.axes) == 1  # no twiny() top axis was created
    finally:
        plt.close(fig)

    r_out = r_plotcp_derived_from_cptable(cptable)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable), upper="none")
    py_out = call_plotcp_and_extract({"cptable": cptable}, upper="none")
    _assert_matches_derivation(py_out, r_out, check_top=False, check_minline=True)


# ---------------------------------------------------------------------------
# 6. An explicit `ylim=` kwarg overrides the default -0.1/+0.1-padded
#    min/max computation entirely -- plotcp.py's own `if 'ylim' not in
#    kwargs` branch, mirroring R's `if (!"ylim" %in% names(dots))`.
# ---------------------------------------------------------------------------

def test_plotcp_explicit_ylim_overrides_default():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.05, 1, 0.6, 0.70, 0.08],
        ]
    )
    custom_ylim = (0.0, 2.0)
    py_out = call_plotcp_and_extract({"cptable": cptable}, ylim=custom_ylim)
    assert py_out["ylim"] == pytest.approx(custom_ylim)

    r_out = r_plotcp_derived_from_cptable(cptable)
    # The *default* R-computed ylim would have differed from our override --
    # confirming the override actually took effect (not silently ignored).
    assert r_out["ylim"] != pytest.approx(custom_ylim)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable), ylim=list(custom_ylim))


# ---------------------------------------------------------------------------
# 7. `lty`/`col` as strings (matplotlib-native spellings, e.g. "dashed"/
#    "purple") rather than R-style small integers -- plotcp.py's
#    `isinstance(lty, int)`/`isinstance(col, int)` guards pass these
#    through unchanged. R's `lty`/`col` also accept strings, but not the
#    same *matplotlib* spellings (e.g. R's dashed spelling is "dashed" too
#    for lty, so this happens to overlap for lty; R col names are also
#    mostly shared with matplotlib's X11-derived names like "purple").
#    This test focuses on: passing strings doesn't crash and doesn't
#    perturb any of the numeric derivations under test.
# ---------------------------------------------------------------------------

def test_plotcp_lty_and_col_as_strings():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.01, 2, 0.4, 0.55, 0.07],
        ]
    )
    py_out = call_plotcp_and_extract({"cptable": cptable}, lty="dashed", col="purple")
    r_out = r_plotcp_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable), lty="dashed", col="purple")


# ---------------------------------------------------------------------------
# 8. Non-default, but still-mapped, integer `lty`/`col` (lty=2 -> "--",
#    col=3 -> "green" per plotcp.py's own `_lty_map`/`_col_map`) -- confirms
#    changing these away from their defaults doesn't alter any of the
#    numeric derivations (they only affect drawing style/color).
# ---------------------------------------------------------------------------

def test_plotcp_non_default_mapped_lty_and_col():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.01, 2, 0.4, 0.55, 0.07],
        ]
    )
    py_out = call_plotcp_and_extract({"cptable": cptable}, lty=2, col=3)
    r_out = r_plotcp_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable), lty=2, col=3)


# ---------------------------------------------------------------------------
# 9. A caller-supplied `ax=` (pre-created, e.g. one subplot in a larger
#    figure) produces identical derived output to letting plotcp() create
#    its own fresh Axes (ax=None) -- the `ax is None` branch in plotcp.py
#    only affects *where* the plot lands, never the data plotted.
# ---------------------------------------------------------------------------

def test_plotcp_explicit_ax_matches_default_ax_creation():
    import matplotlib.pyplot as plt

    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.05, 2, 0.4, 0.55, 0.07],
            [0.01, 3, 0.3, 0.50, 0.06],
        ]
    )
    fit = {"cptable": cptable}

    default_out = call_plotcp_and_extract(fit)

    fig, (ax1, ax2) = plt.subplots(1, 2)
    try:
        retval = plotcp(fit, ax=ax2)
        assert retval is None
        assert len(ax1.lines) == 0  # the untouched sibling axes stays empty
        assert len(ax2.lines) >= 1
        np.testing.assert_allclose(ax2.lines[0].get_ydata(), default_out["xerror"])
        np.testing.assert_allclose(ax2.get_ylim(), default_out["ylim"])
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# 10. `x['cptable']` as a plain numpy.ndarray directly (rather than a
#     pandas.DataFrame -- plotcp.py's `hasattr(p_rpart, 'to_numpy')` branch
#     is simply skipped in this case) vs. as a pandas.DataFrame with the
#     genuine rpart()-style column labels: both must produce identical
#     plotted output for the same underlying numeric data.
# ---------------------------------------------------------------------------

def test_plotcp_ndarray_cptable_matches_dataframe_cptable():
    import pandas as pd

    cptable_np = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.05, 2, 0.4, 0.55, 0.07],
            [0.01, 3, 0.3, 0.50, 0.06],
        ]
    )
    cptable_df = pd.DataFrame(cptable_np, columns=["CP", "nsplit", "rel error", "xerror", "xstd"])

    nd_out = call_plotcp_and_extract({"cptable": cptable_np})
    df_out = call_plotcp_and_extract({"cptable": cptable_df})

    np.testing.assert_allclose(nd_out["ns"], df_out["ns"])
    np.testing.assert_allclose(nd_out["xerror"], df_out["xerror"])
    np.testing.assert_allclose(nd_out["ylim"], df_out["ylim"])
    assert nd_out["cp_labels"] == df_out["cp_labels"]
    assert nd_out["top_labels"] == df_out["top_labels"]
    assert nd_out["minline_y"] == pytest.approx(df_out["minline_y"])

    r_out = r_plotcp_derived_from_cptable(cptable_np)
    _assert_matches_derivation(nd_out, r_out, check_top=True, check_minline=True)


# ---------------------------------------------------------------------------
# 11. Larger `xval` (10 folds instead of 5) on a multi-predictor anova fit --
#     exercises a bigger/more finely-grained cptable (more rows) than the
#     other tests, still matching the R replica row-for-row.
# ---------------------------------------------------------------------------

def test_plotcp_larger_xval_more_cptable_rows():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    np.random.seed(7)
    py_fit = rpart(
        "Mileage ~ Weight + Price + Country + Disp.", data=df, method="anova", control={"xval": 10, "cp": 0.001}
    )
    assert py_fit["cptable"].shape[0] >= 3

    py_out = call_plotcp_and_extract(py_fit)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_plotcp_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out, check_top=True, check_minline=True)

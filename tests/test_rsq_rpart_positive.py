"""Positive-path parity tests for r2py_rpart.rsq_rpart vs. R's
rpart::rsq.rpart.

rsq.rpart(x) (see rpart/man/rsq.rpart.Rd, `usage{rsq.rpart(x)}`) is a plain,
exported R function taking only `x` (a fitted "rpart" object) and producing
2 diagnostic plots as a pure side effect -- it returns `invisible()` (NULL)
on both sides (r2py_rpart.rsq_rpart() is annotated `-> None`). So, exactly
like the existing test_plotcp_positive.py/test_plot_rpart_positive.py in
this same directory, these tests compare:

  - r2py_rpart.rsq_rpart()'s plotted data, pulled back out of the
    `matplotlib.axes.Axes` it draws on via
    `_r_rpart_helpers.call_rsq_rpart_and_extract()` (panel 1's "Apparent"/
    "X Relative" R-square lines, its fixed (0, 1) ylim and legend labels;
    panel 2's X-relative-error line, its computed ylim, and the
    `ax2.vlines(...)` +/- 1-SE error-bar segments); against

  - `_r_rpart_helpers.r_rsq_rpart_derived_from_cptable()`, an R replica of
    rsq.rpart.R's own derivation logic (copied line-for-line from the point
    `p.rpart <- printcp(x)` returns onward -- printcp(x)'s own
    `invisible(x$cptable)` return value is exactly `x$cptable` unrounded, so
    the replica operates directly on the same numeric `cptable` -- omitting
    only the graphics calls themselves), run on the *exact same* `cptable`
    matrix.

Feeding the identical `cptable` into both sides is deliberate: R's and
python's rpart() draw independent cross-validation folds for the same
formula/data (an inherently RNG-driven, incomparable quantity -- see
test_printcp_positive.py's/test_plotcp_positive.py's own notes on this same
point), so comparing rsq.rpart()'s *derivation logic* is only meaningful
when both sides start from the same numeric cptable. Several tests below
additionally confirm, via `r_rsq_rpart_runs_without_error()`, that R's
*actual* exported `rsq.rpart()` function (not just the derivation replica)
accepts the same `x` (a minimal synthetic object carrying only `cptable` +
`method`, built via `r_rsq_rpart_like_expr()`) without raising -- i.e. that
the synthetic inputs used are genuinely within rsq.rpart()'s documented
domain, not just accepted by the hand-copied replica.

rsq.rpart(x) takes no parameters besides `x` on the R side; r2py_rpart's
rsq_rpart(x, fig=None, ax=None) additionally accepts optional `fig`/`ax`
kwargs purely to control *where* the two panels are drawn (a python-only
convenience, with no R analogue) -- exercised in tests 6-7 below.

See tests/_r_rpart_helpers.py's "rsq.rpart-specific plumbing" section (both
R- and python-side) for all the shared machinery used below.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.rsq_rpart import rsq_rpart

from _r_rpart_helpers import (
    call_rsq_rpart_and_extract,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_rsq_rpart_derived_from_cptable,
    r_rsq_rpart_like_expr,
    r_rsq_rpart_runs_without_error,
    r_rsq_rpart_warning,
    run_r,
    stagec_df,
)


def _assert_matches_derivation(py_out: dict, r_out: dict) -> None:
    """The core comparison used throughout this file: everything
    rsq_rpart.py plots, pulled out of the Axes via
    call_rsq_rpart_and_extract(), against the R replica's derivation of the
    same cptable."""
    assert py_out["retval"] is None  # mirrors R's own invisible()/NULL return
    np.testing.assert_allclose(py_out["apparent_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["apparent_y"], r_out["rsq_apparent"])
    np.testing.assert_allclose(py_out["xrel_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["xrel_y"], r_out["rsq_xrel"])
    assert py_out["panel1_ylim"] == pytest.approx((0.0, 1.0))
    assert py_out["legend_labels"] == ["Apparent", "X Relative"]
    assert py_out["panel1_xlabel"] == "Number of Splits"
    assert py_out["panel1_ylabel"] == "R-square"
    np.testing.assert_allclose(py_out["xerror_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["xerror_y"], r_out["xerror"])
    np.testing.assert_allclose(py_out["panel2_ylim"], r_out["ylim"], rtol=1e-9, atol=1e-9)
    assert py_out["panel2_xlabel"] == "Number of Splits"
    assert py_out["panel2_ylabel"] == "X Relative Error"
    np.testing.assert_allclose(py_out["xerror_minus_std"], r_out["xerror"] - r_out["xstd"])
    np.testing.assert_allclose(py_out["xerror_plus_std"], r_out["xerror"] + r_out["xstd"])
    np.testing.assert_allclose(py_out["vlines_x"], r_out["nsplit"])


# ---------------------------------------------------------------------------
# 1. A genuine anova (regression) fit, built via r2py_rpart.rpart() on
#    car.test.frame (Mileage ~ Weight), xval=5 so the cptable carries real
#    xerror/xstd columns. Default rsq_rpart(x) call (fig=None, ax=None: its
#    own default two-subplot creation path). Also sanity-checks that R's
#    *actual* rsq.rpart() accepts the equivalent minimal object without
#    raising or warning (method="anova").
# ---------------------------------------------------------------------------

def test_rsq_rpart_anova_car_test_frame_default_args():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    np.random.seed(1)
    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 5})
    assert py_fit["cptable"].shape[1] == 5

    py_out = call_rsq_rpart_and_extract(py_fit)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out)

    expr = r_rsq_rpart_like_expr(cptable_np, method="anova")
    assert r_rsq_rpart_runs_without_error(expr)
    assert r_rsq_rpart_warning(expr) is None


# ---------------------------------------------------------------------------
# 2. A classification fit (kyphosis), method="class" -- rsq.rpart.Rd's own
#    \note{} says "The labels are only appropriate for the anova method",
#    and rsq.rpart.R's `if (!method == "anova") warning(...)` fires for any
#    other method. Confirms the warning text matches (mirrored near-
#    verbatim by rsq_rpart.py's own `warnings.warn(...)` call) on both
#    sides, in addition to the usual derivation-match checks (the plotted
#    *data* itself is unaffected by the warning).
# ---------------------------------------------------------------------------

def test_rsq_rpart_classification_kyphosis_warns_non_anova_method():
    df = kyphosis_df()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 5})
    assert py_fit["cptable"].shape[1] == 5

    with pytest.warns(UserWarning, match="may not be applicable for this method"):
        py_out = call_rsq_rpart_and_extract(py_fit)

    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out)

    expr = r_rsq_rpart_like_expr(cptable_np, method="class")
    r_warning = r_rsq_rpart_warning(expr)
    assert r_warning is not None and "may not be applicable for this method" in r_warning


# ---------------------------------------------------------------------------
# 3. A method="poisson" (Surv()-style) fit on stagec, mirroring the
#    pre-built model-frame pattern test_printcp_positive.py/
#    test_plotcp_positive.py use for poisson/Surv fits. Also a non-"anova"
#    method, so the same warning fires.
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


def test_rsq_rpart_poisson_method_stagec_warns():
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

    with pytest.warns(UserWarning, match="may not be applicable for this method"):
        py_out = call_rsq_rpart_and_extract(py_fit)

    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out)


# ---------------------------------------------------------------------------
# 4. A multi-predictor anova fit with a larger `xval` (10 folds) and a
#    smaller `cp` threshold -- exercises a bigger/more finely-grained
#    cptable (more rows) than the single-predictor test above, still
#    matching the R replica row-for-row.
# ---------------------------------------------------------------------------

def test_rsq_rpart_larger_xval_more_cptable_rows():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    np.random.seed(7)
    py_fit = rpart(
        "Mileage ~ Weight + Price + Country + Disp.", data=df, method="anova", control={"xval": 10, "cp": 0.001}
    )
    assert py_fit["cptable"].shape[0] >= 3

    py_out = call_rsq_rpart_and_extract(py_fit)
    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out)

    expr = r_rsq_rpart_like_expr(cptable_np, method="anova")
    assert r_rsq_rpart_runs_without_error(expr)


# ---------------------------------------------------------------------------
# 5. `x['cptable']` as a plain numpy.ndarray directly (rather than a
#    pandas.DataFrame -- rsq_rpart.py's `hasattr(p_rpart, 'to_numpy')`
#    branch is simply skipped in this case) vs. as a pandas.DataFrame with
#    the genuine rpart()-style column labels: both must produce identical
#    plotted output for the same underlying numeric data.
# ---------------------------------------------------------------------------

def test_rsq_rpart_ndarray_cptable_matches_dataframe_cptable():
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

    nd_fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable_np}
    df_fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable_df}

    nd_out = call_rsq_rpart_and_extract(nd_fit)
    df_out = call_rsq_rpart_and_extract(df_fit)

    np.testing.assert_allclose(nd_out["apparent_y"], df_out["apparent_y"])
    np.testing.assert_allclose(nd_out["xrel_y"], df_out["xrel_y"])
    np.testing.assert_allclose(nd_out["xerror_y"], df_out["xerror_y"])
    np.testing.assert_allclose(nd_out["panel2_ylim"], df_out["panel2_ylim"])

    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(nd_out, r_out)


# ---------------------------------------------------------------------------
# 6. An explicit, caller-supplied `fig=`/`ax=` pair (both non-None) routes
#    rsq_rpart.py through its shared-single-Axes branch (`ax1 = ax2 = ax`):
#    both panels' lines (3 total: apparent, x-relative, xerror) and the
#    vlines error bars all land on the *one* Axes given, rather than a
#    freshly created 2-subplot figure. Confirms the plotted *data* is
#    identical to the default (fig=None, ax=None) 2-subplot case, even
#    though this is a python-only knob with no R analogue.
# ---------------------------------------------------------------------------

def test_rsq_rpart_explicit_shared_fig_and_ax_matches_default():
    import matplotlib.pyplot as plt

    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.01, 2, 0.4, 0.55, 0.07],
        ]
    )
    fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable}

    default_out = call_rsq_rpart_and_extract(fit)
    assert default_out["n_axes"] == 2

    fig, ax = plt.subplots()
    try:
        shared_out = call_rsq_rpart_and_extract(fit, fig=fig, ax=ax)
    finally:
        plt.close(fig)

    assert shared_out["n_axes"] == 1
    assert shared_out["ax1_n_lines"] == 3
    np.testing.assert_allclose(shared_out["apparent_y"], default_out["apparent_y"])
    np.testing.assert_allclose(shared_out["xrel_y"], default_out["xrel_y"])
    np.testing.assert_allclose(shared_out["xerror_y"], default_out["xerror_y"])
    np.testing.assert_allclose(shared_out["panel2_ylim"], default_out["panel2_ylim"])

    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(default_out, r_out)


# ---------------------------------------------------------------------------
# 7. Supplying only ONE of `fig`/`ax` (not both) is, per rsq_rpart.py's own
#    `if fig is None or ax is None:` condition, treated identically to
#    supplying *neither* -- a fresh 2-subplot figure is created regardless,
#    and the caller-supplied `fig`/`ax` is silently ignored (left
#    completely untouched: 0 Axes). Confirms this quirk explicitly, for
#    both the "only fig" and "only ax" cases.
# ---------------------------------------------------------------------------

def test_rsq_rpart_only_one_of_fig_or_ax_falls_back_to_default():
    import matplotlib.pyplot as plt

    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
            [0.01, 2, 0.4, 0.55, 0.07],
        ]
    )
    fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable}

    # Only `fig=` supplied: ignored, untouched (0 axes); a fresh figure
    # (with 2 subplots) is created instead.
    plt.close("all")
    supplied_fig = plt.figure()
    try:
        retval = rsq_rpart(fit, fig=supplied_fig)
        assert retval is None
        assert len(supplied_fig.axes) == 0
        assert len(plt.get_fignums()) == 2  # the untouched one + the fresh one
    finally:
        plt.close("all")

    # Only `ax=` supplied: same story -- the caller's own single Axes is
    # never drawn on; a fresh 2-subplot figure is created instead.
    plt.close("all")
    other_fig, supplied_ax = plt.subplots()
    try:
        retval = rsq_rpart(fit, ax=supplied_ax)
        assert retval is None
        assert len(supplied_ax.lines) == 0
        assert len(other_fig.axes) == 1  # still just the one Axes on this figure
        assert len(plt.get_fignums()) == 2
    finally:
        plt.close("all")


# ---------------------------------------------------------------------------
# 8. A large number of cptable rows (25), stress-testing the derivation
#    match at a bigger scale than the other tests, with a wide range of
#    xerror/xstd magnitudes.
# ---------------------------------------------------------------------------

def test_rsq_rpart_many_rows_large_cptable():
    n = 25
    cp0 = 0.5 * (0.6 ** np.arange(n))
    nsplit = np.arange(n)
    rel_error = np.linspace(1.0, 0.05, n)
    xerror = rel_error + 0.05
    xstd = np.full(n, 0.03)
    cptable = np.column_stack([cp0, nsplit, rel_error, xerror, xstd])
    fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable}

    py_out = call_rsq_rpart_and_extract(fit)
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert len(py_out["apparent_x"]) == n

    expr = r_rsq_rpart_like_expr(cptable, method="anova")
    assert r_rsq_rpart_runs_without_error(expr)


# ---------------------------------------------------------------------------
# 9. A classification fit (cu.summary), a second, independent method="class"
#    dataset/formula from the one used in test 2, further exercising the
#    non-"anova" warning path together with the full derivation match on a
#    genuine multi-predictor fit.
# ---------------------------------------------------------------------------

def test_rsq_rpart_classification_cu_summary_warns_non_anova_method():
    df = cu_summary_df().dropna().reset_index(drop=True)
    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class", control={"xval": 5}
    )
    assert py_fit["cptable"].shape[1] == 5

    with pytest.warns(UserWarning, match="may not be applicable for this method"):
        py_out = call_rsq_rpart_and_extract(py_fit)

    cptable_np = py_fit["cptable"].to_numpy()
    r_out = r_rsq_rpart_derived_from_cptable(cptable_np)
    _assert_matches_derivation(py_out, r_out)


# ---------------------------------------------------------------------------
# 10. Panel 1's ylim is fixed to (0, 1) by both R (`ylim = c(0, 1)` in both
#     of rsq.rpart.R's first two `plot()` calls) and rsq_rpart.py
#     (`ax1.set_ylim(0, 1)`) *regardless* of the underlying data -- confirms
#     this holds even for a cptable whose apparent/cross-validated R-square
#     values are well inside (0, 1) (the ordinary case), complementing
#     test_rsq_rpart_edge.py's out-of-range variant.
# ---------------------------------------------------------------------------

def test_rsq_rpart_panel1_ylim_always_fixed_zero_one():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05],
            [0.2, 1, 0.6, 0.65, 0.04],
            [0.05, 2, 0.3, 0.40, 0.03],
        ]
    )
    fit = {"_rpart_class": "rpart", "method": "anova", "cptable": cptable}
    py_out = call_rsq_rpart_and_extract(fit)
    assert py_out["panel1_ylim"] == pytest.approx((0.0, 1.0))

    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))

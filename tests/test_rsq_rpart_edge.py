"""Boundary/edge-case parity tests for r2py_rpart.rsq_rpart vs. R's
rpart::rsq.rpart.

See test_rsq_rpart_positive.py's module docstring for the overall
comparison strategy (rsq.rpart has no return value on either side, so these
tests compare r2py_rpart.rsq_rpart()'s plotted data -- pulled back out of
the `matplotlib.axes.Axes` via `_r_rpart_helpers.call_rsq_rpart_and_extract()`
-- against `_r_rpart_helpers.r_rsq_rpart_derived_from_cptable()`, a
line-for-line R replica of rsq.rpart.R's own derivation logic, run on the
*same* synthetic `cptable`).

These focus on functional extremes: a root-only (single-row) cptable, a
completely empty (zero-row) cptable, `NaN`/`Inf` inside `xerror` (both sides
must reject these -- confirmed to raise on both R's *actual* `rsq.rpart()`
and python's, via matplotlib's own finite-axis-limits requirement mirroring
R's `plot.window()`), zero cross-validation variance (`xstd == 0`,
degenerate zero-length error bars), `rel_error`/`xerror` values outside
[0, 1] (panel 1's `ylim` stays pinned at `(0, 1)` on both sides regardless),
very large `xstd` (a very wide panel-2 `ylim`), a `cptable` with more than 5
columns (both sides only ever read columns 2/3/4/5, 1-indexed -- column 1,
CP, is *never* read by rsq.rpart, unlike plotcp/printcp), a large number of
rows, and the ndarray-vs-DataFrame `cptable` equivalence at that larger
scale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart.rsq_rpart import rsq_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    call_rsq_rpart_and_extract,
    r_rsq_rpart_derived_from_cptable,
    r_rsq_rpart_error,
    r_rsq_rpart_like_expr,
    r_rsq_rpart_runs_without_error,
)


def _assert_matches_derivation(py_out: dict, r_out: dict) -> None:
    assert py_out["retval"] is None
    np.testing.assert_allclose(py_out["apparent_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["apparent_y"], r_out["rsq_apparent"])
    np.testing.assert_allclose(py_out["xrel_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["xrel_y"], r_out["rsq_xrel"])
    assert py_out["panel1_ylim"] == pytest.approx((0.0, 1.0))
    np.testing.assert_allclose(py_out["xerror_x"], r_out["nsplit"])
    np.testing.assert_allclose(py_out["xerror_y"], r_out["xerror"])
    np.testing.assert_allclose(py_out["panel2_ylim"], r_out["ylim"], rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(py_out["xerror_minus_std"], r_out["xerror"] - r_out["xstd"])
    np.testing.assert_allclose(py_out["xerror_plus_std"], r_out["xerror"] + r_out["xstd"])


def _fit(cptable: np.ndarray, method: str = "anova") -> dict:
    return {"_rpart_class": "rpart", "method": method, "cptable": cptable}


# ---------------------------------------------------------------------------
# 1. Root-only tree: a single-row cptable (as would come from a real fit
#    forced never to split, e.g. a huge minsplit). Every quantity degenerates
#    to a single data point (a single-element "vlines" segment, ylim from a
#    single value's own +/- 0.1 padding); confirms these still agree, and
#    that R's *actual* rsq.rpart() accepts a single-row cptable without
#    raising.
# ---------------------------------------------------------------------------

def test_rsq_rpart_single_row_root_only_cptable():
    cptable = np.array([[0.5, 0, 1.0, 1.0, 0.05]])
    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 2. A completely empty (zero-row) cptable: R's `min(xerror - xstd)` on a
#    zero-length vector raises R's own "no non-missing arguments to min;
#    returning Inf" *warning* first, then `plot.window()` raises "need
#    finite 'xlim' values" (since `nsplit` is also empty). Python's
#    `np.min(xerror - xstd)` on a zero-size array raises its own "zero-size
#    array to reduction operation minimum which has no identity" ValueError,
#    at the exact same computational step (rsq_rpart.py's own
#    `ylim_lo = float(np.min(xerror - xstd)) - 0.1` line, mirroring R's
#    `ylim <- c(min(xerror - xstd) - 0.1, ...)`). Both raise, for related
#    but differently-worded reasons (confirmed empirically first).
#
#    NOTE: `r_rsq_rpart_like_expr()`/`r_matrix_literal()` cannot be used to
#    build the zero-row R object here -- `r_matrix_literal()` renders an
#    empty array's flattened values as literal `c()` (R's zero-length
#    NULL), and `matrix(c(), nrow=0, ncol=5)` itself raises an unrelated
#    "'data' must be of a vector type, was 'NULL'" error in R *before*
#    rsq.rpart is ever reached -- so the zero-row R object is instead built
#    directly here via `matrix(numeric(0), nrow=0, ncol=5)` (R's own
#    canonical empty-numeric-matrix literal).
# ---------------------------------------------------------------------------

def test_rsq_rpart_zero_row_cptable_raises_on_both_sides():
    cptable = np.empty((0, 5))
    expr = 'structure(list(cptable = matrix(numeric(0), nrow=0, ncol=5), method = "anova"), class = "rpart")'
    r_message = r_rsq_rpart_error(expr)
    assert r_message is not None and "finite" in r_message

    with pytest.raises(Exception) as exc_info:
        rsq_rpart(_fit(cptable))

    assert isinstance(exc_info.value, ValueError)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="zero-row cptable")


# ---------------------------------------------------------------------------
# 3. `NaN` inside `xerror`: R's *actual* rsq.rpart() (not just the
#    derivation replica, which has no plotting call to fail) raises "need
#    finite 'ylim' values" from `plot.window()` (panel 2's `ylim` becomes
#    NaN); matplotlib raises its own "Axis limits cannot be NaN or Inf" from
#    `ax2.set_ylim()` for the identical underlying reason. Both sides raise
#    (differently worded, same root cause).
# ---------------------------------------------------------------------------

def test_rsq_rpart_nan_in_xerror_raises_on_both_sides():
    cptable = np.array(
        [
            [0.5, 0, 1.0, np.nan, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_message = r_rsq_rpart_error(r_rsq_rpart_like_expr(cptable, method="anova"))
    assert r_message is not None and "finite" in r_message

    with pytest.raises(Exception) as exc_info:
        rsq_rpart(_fit(cptable))

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="NaN in xerror")


# ---------------------------------------------------------------------------
# 4. `Inf` inside `xerror`: same underlying "non-finite axis limit" failure
#    mode as the NaN case above, on both sides.
# ---------------------------------------------------------------------------

def test_rsq_rpart_inf_in_xerror_raises_on_both_sides():
    cptable = np.array(
        [
            [0.5, 0, 1.0, np.inf, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_message = r_rsq_rpart_error(r_rsq_rpart_like_expr(cptable, method="anova"))
    assert r_message is not None and "finite" in r_message

    with pytest.raises(Exception) as exc_info:
        rsq_rpart(_fit(cptable))

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="Inf in xerror")


# ---------------------------------------------------------------------------
# 5. Zero cross-validation variance (`xstd == 0` for every row) -- a
#    legitimate degenerate case (e.g. a fit whose cross-validated error
#    happened to be identical across every fold). The `ax2.vlines(...)`
#    error bars degenerate to zero-length segments (`ymin == ymax ==
#    xerror`); confirms both sides handle this without raising and agree on
#    every derived quantity.
# ---------------------------------------------------------------------------

def test_rsq_rpart_zero_xstd_degenerate_error_bars():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.0],
            [0.2, 1, 0.6, 0.70, 0.0],
            [0.01, 2, 0.4, 0.55, 0.0],
        ]
    )
    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    np.testing.assert_allclose(py_out["xerror_minus_std"], py_out["xerror_plus_std"])
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 6. `rel_error`/`xerror` values outside the ordinary [0, 1] range (e.g. a
#    tree that performs *worse* than the root node, `rel.error > 1`, which
#    is a real, if unusual, possibility for cross-validated error) --
#    panel 1's `ylim` is unconditionally pinned to `(0, 1)` on both sides
#    (R's own two `plot(..., ylim = c(0, 1))` calls; rsq_rpart.py's
#    `ax1.set_ylim(0, 1)`) regardless of the underlying `1 - rel_error`/
#    `1 - xerror` values actually falling outside that range -- confirmed
#    here that the *data* itself (the lines' unclipped y-values) still
#    matches the (now negative) derived quantities exactly, even though the
#    axis limits themselves do not expand to fit them.
# ---------------------------------------------------------------------------

def test_rsq_rpart_rel_error_greater_than_one_ylim_still_pinned():
    cptable = np.array(
        [
            [0.5, 0, 1.5, 1.6, 0.10],
            [0.2, 1, 0.9, 1.0, 0.08],
        ]
    )
    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)

    assert np.any(r_out["rsq_apparent"] < 0)  # sanity: genuinely out-of-range data
    _assert_matches_derivation(py_out, r_out)
    assert py_out["panel1_ylim"] == pytest.approx((0.0, 1.0))
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 7. Very large `xstd` values (much larger than `xerror` itself, e.g. from a
#    tiny/unstable cross-validation sample) -- produces a very wide,
#    strongly negative-to-positive panel-2 `ylim`; confirms the `ylim`
#    computation (`min(xerror - xstd) - 0.1`/`max(xerror + xstd) + 0.1`)
#    and the vlines segment endpoints still agree exactly at this
#    magnitude.
# ---------------------------------------------------------------------------

def test_rsq_rpart_very_large_xstd_wide_ylim():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 50.0],
            [0.2, 1, 0.6, 0.70, 80.0],
            [0.01, 2, 0.4, 0.55, 30.0],
        ]
    )
    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert py_out["panel2_ylim"][0] < -50
    assert py_out["panel2_ylim"][1] > 50
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 8. `cptable` with *more* than 5 columns (e.g. 7): both R's `p.rpart[,
#     2L]`/`[, 3L]`/`[, 4L]`/`[, 5L]` and rsq_rpart.py's `p_rpart[:, 1]`/
#     `[:, 2]`/`[:, 3]`/`[:, 4]` read strictly positionally, ignoring any
#     trailing extra columns (and, notably, column 1/index 0 -- the `CP`
#     column itself -- is *never* read by rsq.rpart either, unlike
#     plotcp/printcp) -- confirms neither side is thrown off by (nor
#     accidentally reads from) the CP column or columns 6/7.
# ---------------------------------------------------------------------------

def test_rsq_rpart_extra_trailing_columns_are_ignored():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05, 999.0, -1.0],
            [0.05, 1, 0.6, 0.9, 0.04, 999.0, -1.0],
            [0.001, 2, 0.4, 0.8, 0.03, 999.0, -1.0],
        ]
    )
    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 9. A large number of rows (25) -- stress-tests the per-row plotting/vlines
#    construction at a larger scale than the other tests, with a wide range
#    of xerror/xstd magnitudes (geometric decay of `rel_error`/`xerror`).
# ---------------------------------------------------------------------------

def test_rsq_rpart_many_rows_large_cptable():
    n = 25
    cp0 = 0.5 * (0.6 ** np.arange(n))
    nsplit = np.arange(n)
    rel_error = np.linspace(1.0, 0.05, n)
    xerror = rel_error + 0.05
    xstd = np.full(n, 0.03)
    cptable = np.column_stack([cp0, nsplit, rel_error, xerror, xstd])

    py_out = call_rsq_rpart_and_extract(_fit(cptable))
    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)
    assert len(py_out["apparent_x"]) == n
    assert r_rsq_rpart_runs_without_error(r_rsq_rpart_like_expr(cptable, method="anova"))


# ---------------------------------------------------------------------------
# 10. The ndarray-vs-DataFrame `cptable` equivalence (rsq_rpart.py's
#     `hasattr(p_rpart, 'to_numpy')` branch) at the larger 25-row scale from
#     test 9 above, complementing test_rsq_rpart_positive.py's smaller-scale
#     version of the same check.
# ---------------------------------------------------------------------------

def test_rsq_rpart_ndarray_vs_dataframe_cptable_large_scale():
    n = 25
    cp0 = 0.5 * (0.6 ** np.arange(n))
    nsplit = np.arange(n)
    rel_error = np.linspace(1.0, 0.05, n)
    xerror = rel_error + 0.05
    xstd = np.full(n, 0.03)
    cptable_np = np.column_stack([cp0, nsplit, rel_error, xerror, xstd])
    cptable_df = pd.DataFrame(cptable_np, columns=["CP", "nsplit", "rel error", "xerror", "xstd"])

    nd_out = call_rsq_rpart_and_extract(_fit(cptable_np))
    df_out = call_rsq_rpart_and_extract(_fit(cptable_df))

    np.testing.assert_allclose(nd_out["apparent_y"], df_out["apparent_y"])
    np.testing.assert_allclose(nd_out["xrel_y"], df_out["xrel_y"])
    np.testing.assert_allclose(nd_out["xerror_y"], df_out["xerror_y"])
    np.testing.assert_allclose(nd_out["panel2_ylim"], df_out["panel2_ylim"])
    np.testing.assert_allclose(nd_out["xerror_minus_std"], df_out["xerror_minus_std"])
    np.testing.assert_allclose(nd_out["xerror_plus_std"], df_out["xerror_plus_std"])


# ---------------------------------------------------------------------------
# 11. `method` present but not the string `"anova"` and not any other
#     rpart-recognized method name either (a nonsense string) -- rsq.rpart's
#     own check is a simple inequality (`!method == "anova"` in R;
#     `method != 'anova'` in python), not a `match.arg()`-style whitelist,
#     so *any* non-"anova" value -- garbage or not -- merely triggers the
#     same warning rather than a distinct error on either side.
# ---------------------------------------------------------------------------

def test_rsq_rpart_nonsense_method_string_only_warns():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.05, 0.10],
            [0.2, 1, 0.6, 0.70, 0.08],
        ]
    )
    with pytest.warns(UserWarning, match="may not be applicable for this method"):
        py_out = call_rsq_rpart_and_extract(_fit(cptable, method="totally-not-a-method"))

    r_out = r_rsq_rpart_derived_from_cptable(cptable)
    _assert_matches_derivation(py_out, r_out)

    expr = r_rsq_rpart_like_expr(cptable, method="totally-not-a-method")
    assert r_rsq_rpart_runs_without_error(expr)

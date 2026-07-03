"""Boundary/edge-case parity tests for r2py_rpart.plotcp vs. R's
rpart::plotcp.

See test_plotcp_positive.py's module docstring for the overall comparison
strategy (plotcp has no return value on either side, so these tests compare
r2py_rpart.plotcp()'s plotted data -- pulled back out of the
`matplotlib.axes.Axes` via `_r_rpart_helpers.call_plotcp_and_extract()` --
against `_r_rpart_helpers.r_plotcp_derived_from_cptable()`, a line-for-line R
replica of plotcp.R's own derivation logic, run on the *same* synthetic
`cptable`), and for the known `cp`-label formatting gaps
(`plotcp_cp_labels_match_modulo_known_gap()`: "Inf"/"inf" and "0"/"0.0").

These focus on functional extremes: a root-only (single-row) cptable, tied
minima in `xerror` (does `minpos` pick the *first* tie, as R's `min(...)`
does?), very small/very large `cp` magnitudes (scientific-notation label
formatting), a `cp0 == 0` row, `NaN`/`Inf` inside `xerror`/`xstd` (both sides
must reject these -- confirmed to raise on both R's *actual* `plotcp()` and
python's, via matplotlib's own finite-axis-limits requirement mirroring R's
`plot.window()`), a `cptable` with more than 5 columns (both sides only ever
read columns 1/2/4/5 positionally), a large number of rows, and the
ndarray-vs-DataFrame `cptable` equivalence at this larger scale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from r2py_rpart.plotcp import plotcp

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    call_plotcp_and_extract,
    plotcp_cp_labels_match_modulo_known_gap,
    plotcp_cp_labels_numerically_close,
    r_error_message,
    r_plotcp_derived_from_cptable,
    r_plotcp_error,
    r_plotcp_runs_without_error,
    r_rpart_like_expr,
)


def _assert_matches_derivation(py_out: dict, r_out: dict, *, label_check: str = "strict") -> None:
    """``label_check="strict"`` uses plotcp_cp_labels_match_modulo_known_gap
    (tolerating only the "Inf"/"inf" and "0"/"0.0" gaps); ``"numeric"``
    instead uses plotcp_cp_labels_numerically_close (tolerating *any*
    string-rendering difference, including the scientific-notation
    threshold gap demonstrated in
    test_plotcp_cp_label_scientific_notation_threshold_known_gap below) --
    used for tests whose focus is elsewhere (e.g. stress-testing many rows)
    and which may incidentally land on a `cp` value that triggers that
    separate, already-documented gap."""
    assert py_out["retval"] is None
    np.testing.assert_allclose(py_out["ns"], r_out["ns"])
    np.testing.assert_allclose(py_out["xerror"], r_out["xerror"])
    np.testing.assert_allclose(py_out["ylim"], r_out["ylim"], rtol=1e-9, atol=1e-9)
    if label_check == "strict":
        assert plotcp_cp_labels_match_modulo_known_gap(py_out["cp_labels"], r_out["cp_labels"])
    else:
        assert plotcp_cp_labels_numerically_close(py_out["cp_labels"], r_out["cp_labels"])
    np.testing.assert_allclose(py_out["xerror_minus_std"], r_out["xerror"] - r_out["xstd"])
    np.testing.assert_allclose(py_out["xerror_plus_std"], r_out["xerror"] + r_out["xstd"])
    assert py_out["minline_y"] == pytest.approx(r_out["minline_y"])


# ---------------------------------------------------------------------------
# 1. Root-only tree: a single-row cptable (as would come from a real fit
#    forced never to split, e.g. a huge minsplit). ylim/minline/minpos all
#    degenerate to a single data point; confirm they still agree, and that
#    R's *actual* plotcp() accepts a single-row cptable without raising.
# ---------------------------------------------------------------------------

def test_plotcp_single_row_root_only_cptable():
    cptable = np.array([[0.5, 0, 1.0, 1.0, 0.05]])
    py_out = call_plotcp_and_extract({"cptable": cptable})
    r_out = r_plotcp_derived_from_cptable(cptable)

    assert r_out["minpos"] == 1
    _assert_matches_derivation(py_out, r_out)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable))


# ---------------------------------------------------------------------------
# 2. Tied minimum `xerror` across multiple rows: R's `min(seq_along(xerror)
#    [xerror == min(xerror)])` picks the *first* (smallest-index) tied
#    position -- confirm plotcp.py's `int(np.min(np.where(xerror ==
#    np.min(xerror))))` does the same, and that the resulting minline height
#    agrees between both sides.
# ---------------------------------------------------------------------------

def test_plotcp_tied_minimum_xerror_picks_first_occurrence():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05],
            [0.05, 1, 0.6, 0.90, 0.04],  # tied minimum xerror (row index 1)
            [0.0005, 2, 0.4, 0.90, 0.04],  # tied minimum xerror (row index 2)
            [0.00001, 3, 0.3, 1.10, 0.03],
        ]
    )
    r_out = r_plotcp_derived_from_cptable(cptable)
    assert r_out["minpos"] == 2  # 1-indexed: the *first* of the two tied rows

    py_out = call_plotcp_and_extract({"cptable": cptable})
    _assert_matches_derivation(py_out, r_out)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable))


# ---------------------------------------------------------------------------
# 3. Very small `cp` magnitudes (down to 1e-5), producing scientific-notation
#    axis labels on both sides (e.g. "7.1e-05") -- confirms `signif(cp, 2)`
#    (R) and plotcp.py's own `_signif()` helper agree on rounding *and* that
#    python's `str()` renders the scientific-notation case identically to R
#    (unlike the whole-number/"Inf" cases, this is NOT a known gap).
# ---------------------------------------------------------------------------

def test_plotcp_very_small_cp_magnitudes_scientific_notation_labels():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
            [0.0005, 2, 0.4, 0.9, 0.04],
            [0.00001, 3, 0.3, 1.1, 0.03],
        ]
    )
    r_out = r_plotcp_derived_from_cptable(cptable)
    py_out = call_plotcp_and_extract({"cptable": cptable})

    assert any("e-" in lbl for lbl in r_out["cp_labels"])
    assert r_out["cp_labels"][-1] == "7.1e-05"
    assert py_out["cp_labels"][-1] == "7.1e-05"  # exact match: not part of the known gap
    _assert_matches_derivation(py_out, r_out)


# ---------------------------------------------------------------------------
# 4. `cp0 == 0` exactly in the last row (a legitimate rpart cptable can have
#    a final CP of 0 when `control$cp` is set to 0): the *known* cp-label
#    formatting gap (R's `as.character(0)` == "0"; python's
#    `str(round(0.0, ...))` == "0.0") is demonstrated explicitly here
#    (rather than just silently tolerated via
#    plotcp_cp_labels_match_modulo_known_gap), in addition to confirming
#    every other derived quantity still agrees.
# ---------------------------------------------------------------------------

def test_plotcp_exact_zero_cp_known_label_formatting_gap():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05],
            [0.0, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_out = r_plotcp_derived_from_cptable(cptable)
    py_out = call_plotcp_and_extract({"cptable": cptable})

    assert r_out["cp_labels"][-1] == "0"
    # KNOWN GAP: python's float-to-str always keeps a trailing ".0" for a
    # whole-valued float, where R's character coercion does not.
    assert py_out["cp_labels"][-1] == "0.0"
    assert plotcp_cp_labels_match_modulo_known_gap(py_out["cp_labels"], r_out["cp_labels"])
    _assert_matches_derivation(py_out, r_out)


# ---------------------------------------------------------------------------
# 5. `NaN` inside `xerror`: R's *actual* plotcp() (not just the derivation
#    replica, which has no plotting call to fail) raises
#    "need finite 'ylim' values" from `plot.window()`, because `ylim`
#    becomes NaN; matplotlib raises its own "Axis limits cannot be NaN or
#    Inf" from `ax.set_ylim()` for the identical underlying reason. Both
#    sides raise (differently worded, same root cause), so this is not a
#    KNOWN GAP.
# ---------------------------------------------------------------------------

def test_plotcp_nan_in_xerror_raises_on_both_sides():
    cptable = np.array(
        [
            [0.5, 0, 1.0, np.nan, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_message = r_plotcp_error(r_rpart_like_expr(cptable))
    assert r_message is not None and "finite" in r_message

    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": cptable})

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="NaN in xerror")


# ---------------------------------------------------------------------------
# 6. `Inf` inside `xerror` (a genuine +Inf value in the data itself, as
#    distinct from `cp[0]`'s *always*-present +Inf, which never reaches
#    `ylim`): same underlying "non-finite axis limit" failure mode as the
#    NaN case, on both sides.
# ---------------------------------------------------------------------------

def test_plotcp_inf_in_xerror_raises_on_both_sides():
    cptable = np.array(
        [
            [0.5, 0, 1.0, np.inf, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_message = r_plotcp_error(r_rpart_like_expr(cptable))
    assert r_message is not None and "finite" in r_message

    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": cptable})

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="Inf in xerror")


# ---------------------------------------------------------------------------
# 7. `cptable` with *more* than 5 columns (e.g. 7): both R's `p.rpart[,
#    1L]`/`[, 2L]`/`[, 4L]`/`[, 5L]` and plotcp.py's `p_rpart[:, 0]`/`[:,
#    1]`/`[:, 3]`/`[:, 4]` read strictly positionally, ignoring any trailing
#    extra columns -- confirms neither side is thrown off by (nor
#    accidentally reads from) columns 6/7.
# ---------------------------------------------------------------------------

def test_plotcp_extra_trailing_columns_are_ignored():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05, 999.0, -1.0],
            [0.05, 1, 0.6, 0.9, 0.04, 999.0, -1.0],
            [0.001, 2, 0.4, 0.8, 0.03, 999.0, -1.0],
        ]
    )
    r_out = r_plotcp_derived_from_cptable(cptable)
    py_out = call_plotcp_and_extract({"cptable": cptable})
    _assert_matches_derivation(py_out, r_out)
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable))


# ---------------------------------------------------------------------------
# 8. A large number of rows (25) -- stress-tests the per-row `_signif()`/
#    label-building loop (plotcp.py builds `cp_labels` via a python-level
#    list comprehension over each row) at a larger scale than the other
#    tests, with a wide range of CP magnitudes (geometric decay from 0.5
#    down to ~1e-6). Uses the looser numeric label comparison
#    (label_check="numeric") because, at this many rows/magnitudes, one row
#    happens to land exactly on the scientific-notation-threshold gap
#    demonstrated explicitly in the next test below (python's "0.0003" vs
#    R's "3e-04" for the same signif(cp, 2)-rounded value) -- this test's
#    own focus is the *volume* of rows, not that specific formatting nuance.
# ---------------------------------------------------------------------------

def test_plotcp_many_rows_large_cptable():
    n = 25
    cp0 = 0.5 * (0.6 ** np.arange(n))
    nsplit = np.arange(n)
    rel_error = np.linspace(1.0, 0.05, n)
    xerror = rel_error + 0.05
    xstd = np.full(n, 0.03)
    cptable = np.column_stack([cp0, nsplit, rel_error, xerror, xstd])

    r_out = r_plotcp_derived_from_cptable(cptable)
    py_out = call_plotcp_and_extract({"cptable": cptable})
    _assert_matches_derivation(py_out, r_out, label_check="numeric")
    assert len(py_out["cp_labels"]) == n
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable))


# ---------------------------------------------------------------------------
# 9. KNOWN GAP: the `cp`-label scientific-notation *threshold* itself
#    differs between R's `as.character()` and python's `str()`, even when
#    both start from the exact same `signif(cp, 2)`-rounded double value.
#    R's `as.character(3e-04)` is `"3e-04"`; python's `str(round(0.0003,
#    ...))` (== `str(0.0003)`) is `"0.0003"` -- both represent the identical
#    number, but R switches to scientific notation at a smaller-magnitude
#    threshold than python's default float formatting does. Discovered
#    while developing test 8 above (a 25-row cptable incidentally produced
#    a `cp` value landing exactly on this threshold). This is a third,
#    distinct cp-label formatting gap beyond the two documented in
#    test_plotcp_positive.py ("Inf"/"inf" and "0"/"0.0") -- kept as its own
#    explicit, expected-to-fail assertion per this suite's KNOWN GAP
#    convention, rather than silently folded into
#    plotcp_cp_labels_match_modulo_known_gap()'s tolerance.
# ---------------------------------------------------------------------------

def test_plotcp_cp_label_scientific_notation_threshold_known_gap():
    # cp0 identical on both rows -> cp[1] = sqrt(cp0[1] * cp0[0]) == cp0
    # exactly (0.0003), landing precisely on the threshold where R's
    # as.character() switches to scientific notation but python's str()
    # does not.
    t = 0.0003
    cptable = np.array(
        [
            [t, 0, 1.0, 1.0, 0.05],
            [t, 1, 0.6, 0.9, 0.04],
        ]
    )
    r_out = r_plotcp_derived_from_cptable(cptable)
    py_out = call_plotcp_and_extract({"cptable": cptable})

    assert r_out["cp_labels"][-1] == "3e-04"
    assert py_out["cp_labels"][-1] == "0.0003"
    # The underlying rounded *value* is identical either way...
    assert plotcp_cp_labels_numerically_close(py_out["cp_labels"], r_out["cp_labels"])
    # ...but the raw text is not, and is not covered by
    # plotcp_cp_labels_match_modulo_known_gap()'s narrower tolerance.
    # KNOWN GAP: expected to fail.
    assert plotcp_cp_labels_match_modulo_known_gap(py_out["cp_labels"], r_out["cp_labels"])


# ---------------------------------------------------------------------------
# 9. The ndarray-vs-DataFrame `cptable` equivalence (plotcp.py's
#    `hasattr(p_rpart, 'to_numpy')` branch) at the larger 25-row scale from
#    test 8, complementing test_plotcp_positive.py's smaller-scale version
#    of the same check.
# ---------------------------------------------------------------------------

def test_plotcp_ndarray_vs_dataframe_cptable_large_scale():
    n = 25
    cp0 = 0.5 * (0.6 ** np.arange(n))
    nsplit = np.arange(n)
    rel_error = np.linspace(1.0, 0.05, n)
    xerror = rel_error + 0.05
    xstd = np.full(n, 0.03)
    cptable_np = np.column_stack([cp0, nsplit, rel_error, xerror, xstd])
    cptable_df = pd.DataFrame(cptable_np, columns=["CP", "nsplit", "rel error", "xerror", "xstd"])

    nd_out = call_plotcp_and_extract({"cptable": cptable_np})
    df_out = call_plotcp_and_extract({"cptable": cptable_df})

    np.testing.assert_allclose(nd_out["xerror"], df_out["xerror"])
    np.testing.assert_allclose(nd_out["ylim"], df_out["ylim"])
    assert nd_out["cp_labels"] == df_out["cp_labels"]
    assert nd_out["minline_y"] == pytest.approx(df_out["minline_y"])


# ---------------------------------------------------------------------------
# 10. `col=5`, an integer outside plotcp.py's own `_col_map` (only 1-4 are
#     mapped; `.get(col, 'black')` *silently falls back to 'black'* rather
#     than raising, unlike the analogous `lty=5` case in
#     test_plotcp_negative.py, which *does* raise). R natively interprets
#     `col=5` as its 5th default-palette color (cyan) rather than falling
#     back to black or raising. Neither side raises here -- this is a
#     silent-value divergence (wrong color, not wrong data), out of scope
#     for the numeric-data comparisons this suite focuses on -- but is
#     confirmed here to have *zero* effect on any of the numeric
#     derivations under test (ns/xerror/ylim/labels/minline), demonstrating
#     `col`'s only effect is cosmetic.
# ---------------------------------------------------------------------------

def test_plotcp_unmapped_integer_col_falls_back_silently_no_numeric_effect():
    cptable = np.array(
        [
            [0.5, 0, 1.0, 1.0, 0.05],
            [0.05, 1, 0.6, 0.9, 0.04],
        ]
    )
    default_out = call_plotcp_and_extract({"cptable": cptable})
    col5_out = call_plotcp_and_extract({"cptable": cptable}, col=5)

    np.testing.assert_allclose(col5_out["ns"], default_out["ns"])
    np.testing.assert_allclose(col5_out["xerror"], default_out["xerror"])
    np.testing.assert_allclose(col5_out["ylim"], default_out["ylim"])
    assert col5_out["cp_labels"] == default_out["cp_labels"]
    assert col5_out["minline_y"] == pytest.approx(default_out["minline_y"])
    assert r_plotcp_runs_without_error(r_rpart_like_expr(cptable), col=5)

"""Boundary/edge-case parity tests for r2py_rpart.labels_rpart vs. R's
`labels.rpart`.

See test_labels_rpart_positive.py's module docstring for the shared
comparison strategy (calling the documented `labels(fit, ...)` R generic
and r2py_rpart's `labels_rpart(fit, ...)` directly on the *same* fitted
model, built once via each implementation's own `rpart(...)`) and
test_labels_rpart_negative.py's for the malformed-object convention
(`rpart:::labels.rpart(..., generic=False)`, bypassing the `labels()`
generic's own class-based dispatch).

This file targets genuine boundary conditions of labels.rpart's own
documented special cases and numeric limits:

  - the `n == 1L` root-only-tree special case (labels.rpart.R's own
    `if (n == 1L) return("root")` comment: "special case of no splits"),
    for both `collapse=TRUE`/`FALSE`;
  - the smallest possible non-root-only tree (exactly 3 frame rows);
  - `digits=0`;
  - `minlength=` at/above every level name's own natural length (no
    abbreviation is actually needed);
  - the exact `ncat > 52L` threshold boundary (52 = no warning, 53 = the
    "more than 52 levels" warning) via a synthetic categorical fixture,
    impractical to reach through a genuine data-driven fit;
  - both continuous split directions (`ncat == 1` vs `ncat == -1`,
    i.e. `">= "` vs `"< "` on the *left* branch) in a single fit.

It also documents three **permanent, confirmed** gaps in `digits=`'s
extreme/malformed-value handling -- `formatg()`'s naive
`f"%.{digits}g"` format-string construction has no validation of its own,
unlike R's `sprintf()`, which tolerates non-numeric-looking `digits`
values by way of its own (unrelated-to-rpart) idiosyncratic format-string
parsing -- mirroring this test suite's established convention for other
functions' known, permanent parity gaps.
"""
from __future__ import annotations

import warnings

from r2py_rpart import rpart
from r2py_rpart.labels_rpart import labels_rpart

from _r_rpart_helpers import (
    kyphosis_df,
    make_synthetic_categorical_fit,
    r_dataframe_assign,
    r_fit_rpart,
    r_labels,
    r_labels_capturing_warning,
    r_labels_to_python,
)


def _kyphosis_fits(**control):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    fit_kwargs = {"control": control} if control else {}
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", **fit_kwargs)
    ctrl_expr = None
    if control:
        ctrl_items = ", ".join(f"{k}={v}" for k, v in control.items())
        ctrl_expr = f"rpart.control({ctrl_items})"
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", method='"class"',
        **({"control": ctrl_expr} if ctrl_expr else {}),
    )
    return fit, r_fit


# ---------------------------------------------------------------------------
# 1. The `n == 1L` root-only special case, for both `collapse=` values --
#    labels.rpart.R's own comment: "special case of no splits". A
#    `cp=1` control forces rpart to make zero splits at all (frame has
#    exactly 1 row).
# ---------------------------------------------------------------------------

def test_labels_rpart_root_only_tree_collapse_true():
    fit, r_fit = _kyphosis_fits(cp=1)
    assert fit["frame"].shape[0] == 1
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs == ["root"]


def test_labels_rpart_root_only_tree_collapse_false():
    """Even with `collapse=FALSE`, the `n == 1L` guard fires *before* the
    `collapse` branch is ever reached -- both sides return the bare
    `["root"]` vector, not a 1x2 "<leaf>"/"<leaf>" matrix."""
    fit, r_fit = _kyphosis_fits(cp=1)
    r_labs = r_labels_to_python(r_labels(r_fit, collapse=False))
    py_labs = labels_rpart(fit, collapse=False)
    assert py_labs == r_labs == ["root"]


# ---------------------------------------------------------------------------
# 2. The smallest possible *non-root-only* tree: exactly 3 frame rows
#    (root + 2 leaves), forced via maxdepth=1 -- the boundary just above
#    the n == 1L special case above.
# ---------------------------------------------------------------------------

def test_labels_rpart_minimal_three_row_tree_collapse_true():
    fit, r_fit = _kyphosis_fits(maxdepth=1)
    assert fit["frame"].shape[0] == 3
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs
    assert py_labs[0] == "root"


def test_labels_rpart_minimal_three_row_tree_collapse_false():
    fit, r_fit = _kyphosis_fits(maxdepth=1)
    r_mat = r_labels_to_python(r_labels(r_fit, collapse=False))
    py_mat = labels_rpart(fit, collapse=False)
    assert py_mat.shape == (3, 2) == r_mat.shape
    assert (py_mat == r_mat).all()
    # Both leaf rows' own left/right pair must be exactly "<leaf>","<leaf>".
    assert (py_mat[1] == ["<leaf>", "<leaf>"]).all()
    assert (py_mat[2] == ["<leaf>", "<leaf>"]).all()


# ---------------------------------------------------------------------------
# 3. Both continuous split directions (`ncat == 1` vs `ncat == -1`) within
#    a single fit -- confirms the "< "/">= " direction swap
#    (`ifelse(ncat < 0, "< ", ">=")`) is applied per-split, not globally.
# ---------------------------------------------------------------------------

def test_labels_rpart_both_continuous_split_directions_present():
    fit, r_fit = _kyphosis_fits()
    ncat = fit["splits"]["ncat"].to_numpy()
    assert (ncat > 0).any() and (ncat < 0).any(), "fixture must exercise both split directions"
    r_labs = r_labels_to_python(r_labels(r_fit))
    py_labs = labels_rpart(fit)
    assert py_labs == r_labs
    assert any(">=" in lab for lab in py_labs)
    assert any(lab.startswith(("Age< ", "Start< ")) for lab in py_labs)


# ---------------------------------------------------------------------------
# 4. digits=0: the minimum meaningful precision (`formatg`'s own `"%.0g"`).
# ---------------------------------------------------------------------------

def test_labels_rpart_digits_zero():
    fit, r_fit = _kyphosis_fits()
    r_labs = r_labels_to_python(r_labels(r_fit, digits=0))
    py_labs = labels_rpart(fit, digits=0)
    assert py_labs == r_labs


# ---------------------------------------------------------------------------
# 5. minlength= at/above every level name's own natural length: no
#    abbreviation is actually needed, so the level-set labels must equal
#    the full, comma-joined names on both sides regardless of exactly how
#    large minlength is past that point.
# ---------------------------------------------------------------------------

def test_labels_rpart_minlength_exceeding_all_level_lengths():
    from r2py_rpart import rpart as _rpart
    from _r_rpart_helpers import cu_summary_df

    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", method='"class"')
    fit = _rpart("Reliability ~ Price + Country + Mileage + Type", data=df, method="class")

    for minlength in (20, 100):
        r_labs = r_labels_to_python(r_labels(r_fit, minlength=minlength))
        py_labs = labels_rpart(fit, minlength=minlength)
        assert py_labs == r_labs, f"minlength={minlength}"
    # At this size, minlength=20/100 must both agree with minlength=0 (no
    # abbreviation at all is possible once the target exceeds every name).
    py_ml0 = labels_rpart(fit, minlength=0)
    assert labels_rpart(fit, minlength=100) == py_ml0


# ---------------------------------------------------------------------------
# 6. The exact `ncat > 52L` boundary: 52 levels (no warning, letters
#    "a".."z"+"A".."Z" exactly exhausted) vs 53 levels (crosses the
#    threshold, "more than 52 levels..." warning fires and the 53rd level
#    collides onto the same truncated "Z" slot as the 52nd) -- exercised
#    via a synthetic fixture (`make_synthetic_categorical_fit`), since a
#    genuine >52-level factor is impractical to fit identically on both
#    sides through rpart()'s own variable-selection logic.
# ---------------------------------------------------------------------------

def test_labels_rpart_exactly_52_levels_no_warning():
    py_obj, r_expr = make_synthetic_categorical_fit(
        num_levels=52, left_levels=list(range(26))
    )
    r_result, r_warning = r_labels_capturing_warning(r_expr, generic=False)
    assert r_warning is None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_labs = labels_rpart(py_obj)
    assert len(caught) == 0
    assert py_labs == list(r_result) == [
        "root", "X=abcdefghijklmnopqrstuvwxyz", "X=ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ]


def test_labels_rpart_53_levels_crosses_warning_threshold():
    py_obj, r_expr = make_synthetic_categorical_fit(
        num_levels=53, left_levels=list(range(26))
    )
    r_result, r_warning = r_labels_capturing_warning(r_expr, generic=False)
    assert r_warning == "more than 52 levels in a predicting factor, truncated for printout"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_labs = labels_rpart(py_obj)
    assert len(caught) == 1
    assert str(caught[0].message) == r_warning
    assert py_labs == list(r_result)
    # The 53rd level (index 52, right side) collides onto the same
    # truncated "Z" (index 51) slot as the 52nd -- both sides double up.
    assert py_labs[2].endswith("ZZ")


# ---------------------------------------------------------------------------
# KNOWN, PERMANENT GAPS: digits='s malformed/extreme-value handling.
#
# formatg.py's `format = f"%.{digits}g"` builds the C-style format string
# via plain python string interpolation with no validation of `digits`
# itself, then applies it via python's native `%` operator -- which is
# considerably less permissive than R's own `sprintf()` for a handful of
# non-canonical `digits` values. R's `rpart:::labels.rpart` is always
# called with an actual fitted "rpart"-classed object below (so the
# generic `labels(fit, ...)` dispatch route is used throughout, exactly
# as a real caller would).
# ---------------------------------------------------------------------------

def test_labels_rpart_digits_none_is_a_known_gap():
    """KNOWN GAP: `digits=NULL`. R's `sprintf(paste0("%.", NULL, "g"), x)`
    -- `paste0` silently drops the NULL argument, yielding the (still
    valid) format string `"%.g"`, so R happily returns a (low-precision)
    result. Python's `f"%.{None}g"` instead literally embeds the string
    "None" (`"%.Noneg"`), which python's `%` operator cannot parse at
    all, raising ValueError."""
    fit, r_fit = _kyphosis_fits()
    r_labs = r_labels_to_python(r_labels(r_fit, digits=None))
    assert r_labs[1].startswith(("Start", "Age"))  # R: no error

    try:
        labels_rpart(fit, digits=None)
    except ValueError as exc:
        assert "unsupported format character" in str(exc)  # python: raises
    else:
        raise AssertionError("expected python's labels_rpart(..., digits=None) to raise")


def test_labels_rpart_digits_negative_is_a_known_gap():
    """KNOWN GAP: `digits=-1`. R's `sprintf("%.0-1g", x)` -- R's sprintf
    parses "0" as the precision and then apparently treats the stray
    "-1g" as literal trailing text (an R/C-library-specific sprintf
    parsing quirk unrelated to rpart itself), so it does not error, just
    emits a garbled-but-non-erroring string containing the literal
    substring "%.0-1g". Python's `"%.-1g" % v` instead raises ValueError
    (negative precision is not a valid python format-spec token)."""
    fit, r_fit = _kyphosis_fits()
    r_labs = r_labels_to_python(r_labels(r_fit, digits=-1))
    assert any("%.0-1g" in lab for lab in r_labs)  # R: no error, garbled text

    try:
        labels_rpart(fit, digits=-1)
    except ValueError as exc:
        assert "unsupported format character" in str(exc)  # python: raises
    else:
        raise AssertionError("expected python's labels_rpart(..., digits=-1) to raise")


def test_labels_rpart_digits_non_numeric_string_is_a_known_gap():
    """KNOWN GAP: `digits="a"` (a non-numeric string). Both sides happen
    to avoid raising here, but produce entirely different, non-matching
    text: R's `sprintf("%.ag", x)` resolves (via its own idiosyncratic
    parsing of the stray "a") to a hexfloat-flavored string per value
    (e.g. "0x1p+3g"); python's `"%.ag" % v` -- an unrelated, python-
    specific `%`-operator parsing quirk of its own -- discards the value
    entirely and returns the literal string "g" for *every* input,
    collapsing every cutpoint's distinct label down to the same text."""
    fit, r_fit = _kyphosis_fits()
    r_labs = r_labels_to_python(r_labels(r_fit, digits="a"))
    py_labs = labels_rpart(fit, digits="a")
    assert py_labs != r_labs  # neither raises, but the text diverges completely
    assert all(lab.endswith("g") for lab in py_labs[1:])
    assert all(lab in ("Start>=g", "Start< g", "Age>=g", "Age< g") for lab in py_labs[1:])

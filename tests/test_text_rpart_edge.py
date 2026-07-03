"""Boundary/edge-case parity tests for r2py_rpart.text_rpart vs. R's
`text.rpart`.

See test_text_rpart_positive.py's module docstring for the shared
comparison strategy (a `FUN=`-capturing closure substituted on both sides
into the exact same already-fitted model, with R's genuine `par("cxy")`
fed into python's `cxy=` override so both sides use identical label
offsets) and test_text_rpart_negative.py's for the two explicit `stop()`
guards. This file instead targets genuine boundary conditions: the
smallest possible non-root-only tree, the `digits=0` extreme, `fwidth`/
`fheight >= 1` (character-count rather than scaling-factor sizing mode),
a fully-transparent `bg=`, the `srt=90` character-width/height swap, and
one *confirmed, pinned* bug in text_rpart.py's own `fancy=True` split-edge-
label derivation.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.zzz import string_bounding_box

from _r_rpart_helpers import (
    assert_text_rpart_calls_match,
    call_text_rpart_and_extract,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_text_rpart_capture,
)


def _kyphosis_fits(**control):
    df = kyphosis_df()
    fit_kwargs = {"control": control} if control else {}
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", **fit_kwargs)
    r_dataframe_assign("df", df)
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
# 1. The smallest possible *legitimate* (non-root-only) tree: exactly 3
#    frame rows (root + 2 leaves), forced via maxdepth=1 -- the boundary
#    just above the `len(frame) <= 1` guard tested in
#    test_text_rpart_negative.py. Confirms every FUN() call still matches R
#    exactly at this minimal size.
# ---------------------------------------------------------------------------

def test_text_rpart_minimal_three_row_tree():
    fit, r_fit = _kyphosis_fits(maxdepth=1)
    assert fit["frame"].shape[0] == 3

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 2. digits=0: the extreme low end of numeric-label precision (R's
#    `formatg`/python's `formatg` both still produce *some* string, never
#    raising) -- confirmed to match R exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_digits_zero_boundary():
    fit, r_fit = _kyphosis_fits(maxdepth=1)

    r_calls, cxy = r_text_rpart_capture(r_fit, digits=0)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, digits=0)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 3. fwidth/fheight >= 1 switches text.rpart.R's own
#    `if (fwidth < 1) ... else fwidth * cxy[1L]` branch from a *scaling
#    factor* (relative to the string's own bounding box) to an absolute
#    *character-count* -- ovals/rectangles no longer scale with each leaf's
#    own label length. Confirmed here not just structurally (patch count),
#    but that each rectangle's/oval's actual matplotlib bounding-box
#    width/height matches the exact `a_length`/`b_length` (and
#    `sqrt(2)*a_length`/`sqrt(2)*b_length` for ovals) formula from
#    text.rpart.R's own source, computed from the *same* `cxy`/`maxlen`/
#    `maxht` text_rpart.py itself derives.
# ---------------------------------------------------------------------------

def test_text_rpart_fwidth_fheight_character_count_mode():
    fit, r_fit = _kyphosis_fits(maxdepth=1)

    r_calls, cxy = r_text_rpart_capture(r_fit, fancy=True, fwidth=2, fheight=1.5, bg="white")
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, fancy=True, fwidth=2, fheight=1.5, bg="white")
    assert py_out["calls"][-1]["labels"] == r_calls[-1]["labels"]

    stat = py_out["calls"][-1]["labels"]
    bb = string_bounding_box(stat)
    maxlen = int(np.max(bb["columns"])) + 1
    maxht = int(np.max(bb["rows"])) + 1
    assert maxlen > 0 and maxht > 0

    a_length = 2 * cxy[0]      # fwidth=2 >= 1 -> character-count mode
    b_length = 1.5 * cxy[1]    # fheight=1.5 >= 1 -> character-count mode

    rects = [p for p in py_out["ax"].patches if len(p.get_xy()) == 5]
    ovals = [p for p in py_out["ax"].patches if len(p.get_xy()) > 5]
    assert len(rects) == 2  # 2 leaves
    assert len(ovals) == 1  # 1 internal node

    for p in rects:
        xy = p.get_xy()
        w = xy[:, 0].max() - xy[:, 0].min()
        h = xy[:, 1].max() - xy[:, 1].min()
        assert w == pytest.approx(a_length, abs=1e-9)
        assert h == pytest.approx(b_length, abs=1e-9)

    for p in ovals:
        xy = p.get_xy()
        w = xy[:, 0].max() - xy[:, 0].min()
        h = xy[:, 1].max() - xy[:, 1].min()
        assert w == pytest.approx(np.sqrt(2) * a_length, abs=1e-9)
        assert h == pytest.approx(np.sqrt(2) * b_length, abs=1e-9)

    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 4. A fully-transparent `bg=` (alpha channel 0) hits text.rpart.R's own
#    `if (col2rgb(bg, alpha = TRUE)[4L, 1L] < 255) bg <- "white"` fallback
#    (mirrored in text_rpart.py as `if rgba_bg[3] < 1.0: bg = 'white'`) --
#    every patch's facecolor should resolve to opaque white, not to the
#    (invisible) transparent color that was actually passed in.
# ---------------------------------------------------------------------------

def test_text_rpart_transparent_bg_falls_back_to_white():
    import matplotlib.colors as mcolors

    fit, r_fit = _kyphosis_fits(maxdepth=1)
    r_calls, cxy = r_text_rpart_capture(r_fit, fancy=True, bg="#FFFFFF00")
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, fancy=True, bg="#FFFFFF00")

    expected_white = mcolors.to_rgba("white")
    assert len(py_out["ax"].patches) == 3
    for patch in py_out["ax"].patches:
        assert patch.get_facecolor() == pytest.approx(expected_white)

    assert py_out["calls"][-1]["labels"] == r_calls[-1]["labels"]
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 5. srt=90 (a graphical `...` passthrough parameter) triggers text.rpart's
#    own `cxy <- rev(cxy)` swap -- confirmed to change the y-offset of the
#    split-label call relative to the srt-unset default, in exactly the way
#    a swapped (width, height) tuple predicts, on both sides.
# ---------------------------------------------------------------------------

def test_text_rpart_srt_90_swaps_cxy_offset():
    fit, r_fit = _kyphosis_fits(maxdepth=1)

    r_calls_default, cxy = r_text_rpart_capture(r_fit)
    py_default = call_text_rpart_and_extract(fit, cxy=cxy)

    r_calls_srt, _ = r_text_rpart_capture(r_fit, srt=90)
    py_srt = call_text_rpart_and_extract(fit, cxy=cxy, srt=90)
    assert_text_rpart_calls_match(py_srt["calls"], r_calls_srt)

    # the swapped cxy must actually change the offset relative to default
    # (since cxy[0] != cxy[1] for this device)
    assert cxy[0] != pytest.approx(cxy[1])
    assert not np.allclose(py_srt["calls"][0]["y"], py_default["calls"][0]["y"])

    # the split-label y-offset is `xy['y'] + 0.5 * cxy[1]`; with srt=90,
    # cxy is reversed, so the *default* call's own y-values (unshifted)
    # plus 0.5 * cxy[0] (the *swapped* second component) should match the
    # srt=90 call's y-values exactly.
    base_y = py_default["calls"][0]["y"] - 0.5 * cxy[1]
    expected_srt_y = base_y + 0.5 * cxy[0]
    np.testing.assert_allclose(py_srt["calls"][0]["y"], expected_srt_y, atol=1e-9)

    import matplotlib.pyplot as plt
    plt.close(py_default["fig"])
    plt.close(py_srt["fig"])


# ---------------------------------------------------------------------------
# 6. KNOWN BUG (pinned as a regression anchor, per this repository's
#    established "known_bug" convention -- see e.g.
#    test_plot_rpart_edge.py's `compress()`-length bug): text_rpart.py's
#    `fancy=True` branch selects its two split-*edge*-label FUN() calls'
#    labels using `left_child[is_left]`/`right_child[is_left]` (i.e.
#    "the left/right child of each node that is *itself* a left child" --
#    effectively grandchildren), instead of R's own
#    `rows[left.child[!is.na(left.child)]]`/
#    `rows[right.child[!is.na(right.child)]]` ("the left/right child of
#    every node that *has* one", i.e. every internal node, in frame-row
#    order). Both masks happen to have the same cardinality (every
#    internal node contributes exactly one left child and one right child,
#    so `sum(!is.leaf) == sum(is_left)`), so no shape/length error is ever
#    raised -- but the *values* silently differ whenever the tree has more
#    than one internal node. Confirmed here against R's genuine, correct
#    output for the same fit: R returns one edge label per internal node
#    (4, for this fit); python's buggy version returns only however many
#    of those *left-child* nodes themselves happen to have a left/right
#    child of their own (1, for this fit) -- pinned exactly below.
# ---------------------------------------------------------------------------

def test_text_rpart_fancy_split_edge_label_indexing_known_bug():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')

    r_calls, cxy = r_text_rpart_capture(r_fit, fancy=True)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, fancy=True)

    n_internal = int((fit["frame"]["var"] != "<leaf>").sum())
    assert n_internal == 4

    # R's genuine output: one label per internal node, for both edge calls.
    assert r_calls[0]["labels"] == ["Start>=8.5", "Start>=14.5", "Age< 55", "Age>=111"]
    assert r_calls[1]["labels"] == ["Start< 8.5", "Start< 14.5", "Age>=55", "Age< 111"]
    assert len(r_calls[0]["labels"]) == n_internal
    assert len(r_calls[1]["labels"]) == n_internal

    # python's buggy output: far fewer labels, and not a mere reordering of
    # R's -- "Start>=14.5"/"Start< 14.5" are the *only* survivors, because
    # node 4 (whose own left/right child is node 8/9) is the only
    # `is_left`-flagged node that itself has children in this tree.
    assert py_out["calls"][0]["labels"] == ["Start>=14.5"]
    assert py_out["calls"][1]["labels"] == ["Start< 14.5"]
    assert len(py_out["calls"][0]["labels"]) != n_internal
    assert len(py_out["calls"][1]["labels"]) != n_internal

    # the leaf/node stat call (always the *last* capture) is unaffected by
    # this bug and still matches R exactly, regardless of fancy=True.
    assert py_out["calls"][-1]["labels"] == r_calls[-1]["labels"]

    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 7. all=True combined with use_n=True (a boundary *combination*, not
#    exercised individually in test_text_rpart_positive.py) -- every frame
#    row (not just leaves) gets an event-count-annotated stat label,
#    confirmed to match R exactly.
# ---------------------------------------------------------------------------

def test_text_rpart_all_true_use_n_true_combination():
    fit, r_fit = _kyphosis_fits()

    r_calls, cxy = r_text_rpart_capture(r_fit, all=True, use_n=True)
    py_out = call_text_rpart_and_extract(fit, cxy=cxy, all=True, use_n=True)
    assert_text_rpart_calls_match(py_out["calls"], r_calls)
    assert len(py_out["calls"][-1]["labels"]) == fit["frame"].shape[0]
    assert all("/" in lab for lab in py_out["calls"][-1]["labels"])
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])


# ---------------------------------------------------------------------------
# 8. Extra graphical passthrough kwargs (e.g. `color=`) are forwarded to
#    FUN() unchanged and never perturb the underlying label/position
#    derivation -- confirmed by comparing against the no-extra-kwargs
#    capture for identical (x, y, labels).
# ---------------------------------------------------------------------------

def test_text_rpart_extra_passthrough_kwargs_do_not_affect_labels():
    fit, r_fit = _kyphosis_fits(maxdepth=1)

    r_calls, cxy = r_text_rpart_capture(r_fit)
    py_plain = call_text_rpart_and_extract(fit, cxy=cxy)
    py_styled = call_text_rpart_and_extract(fit, cxy=cxy, color="red", cex=0.8)

    assert_text_rpart_calls_match(py_plain["calls"], r_calls)
    for plain_call, styled_call in zip(py_plain["calls"], py_styled["calls"]):
        assert plain_call["labels"] == styled_call["labels"]
        np.testing.assert_allclose(plain_call["x"], styled_call["x"])
        np.testing.assert_allclose(plain_call["y"], styled_call["y"])

    import matplotlib.pyplot as plt
    plt.close(py_plain["fig"])
    plt.close(py_styled["fig"])


# ---------------------------------------------------------------------------
# 9. The default `digits=None` resolves to the same numeric precision as an
#    explicit `digits=4` (text_rpart.py's own documented stand-in for R's
#    `getOption("digits") - 3L`, which is 4 at R's factory-default
#    `options(digits=7)`) -- and both match R's own default (omitting
#    `digits=` entirely, so R's `missing()`-free default expression
#    resolves the same way).
# ---------------------------------------------------------------------------

def test_text_rpart_default_digits_matches_explicit_four():
    fit, r_fit = _kyphosis_fits(maxdepth=1)

    r_calls_default, cxy = r_text_rpart_capture(r_fit)  # digits omitted -> R default
    py_none = call_text_rpart_and_extract(fit, cxy=cxy)  # digits=None -> python default
    py_four = call_text_rpart_and_extract(fit, cxy=cxy, digits=4)

    assert_text_rpart_calls_match(py_none["calls"], r_calls_default)
    assert py_none["calls"][-1]["labels"] == py_four["calls"][-1]["labels"]
    import matplotlib.pyplot as plt
    plt.close(py_none["fig"])
    plt.close(py_four["fig"])


# ---------------------------------------------------------------------------
# 10. Omitting `cxy=` entirely (the python-only auto-resolution fallback --
#     R's own `par("cxy")` has no python equivalent, so text_rpart.py
#     derives its own approximation from matplotlib font metrics) still
#     produces a legitimate, finite, non-degenerate (width, height) pair
#     and a completed, error-free text_rpart() call -- exact numeric
#     agreement with R's device-specific `par("cxy")` is neither expected
#     nor asserted here (see test_text_rpart_positive.py's module
#     docstring); this only pins that the auto-resolved fallback is usable.
# ---------------------------------------------------------------------------

def test_text_rpart_omitted_cxy_auto_resolves_to_finite_values():
    fit, _ = _kyphosis_fits(maxdepth=1)

    py_out = call_text_rpart_and_extract(fit)  # cxy=None -> auto-resolve
    assert len(py_out["calls"]) == 2
    for call in py_out["calls"]:
        assert np.all(np.isfinite(call["x"]))
        assert np.all(np.isfinite(call["y"]))
    import matplotlib.pyplot as plt
    plt.close(py_out["fig"])

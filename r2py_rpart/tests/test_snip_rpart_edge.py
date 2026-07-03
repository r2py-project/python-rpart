"""Boundary/edge-case parity tests for r2py_rpart.snip_rpart vs. R's
rpart::snip.rpart. See test_snip_rpart_positive.py's module docstring for
this suite's shared scope (non-interactive, `toss=` supplied explicitly) and
tests/_r_rpart_helpers.py's `r_snip`/`r_snip_capturing_warning` plumbing.

Tests 1-4 are genuine, confirmed parity (both sides warn-and-continue or
warn-and-no-op identically, at the extremes of `toss`: duplicates, a mix of
valid/invalid node numbers, an entirely-invalid `toss`, and negative/zero
node numbers).

KNOWN, PERMANENT BEHAVIORAL GAPS (tests 5-7)
---------------------------------------------
`snip_rpart`'s `toss` handling (`len(toss)`, then
`np.array(toss, dtype=np.int64)`) is stricter than R's own vectorized
`length(toss)`/implicit-coercion semantics in three confirmed ways:

  - a bare scalar (`toss=2`, not wrapped in a list/array) is valid R usage
    (`snip.rpart(x, toss=2)`, exactly as shown in `snip.rpart.Rd`'s own
    example) but raises `TypeError` on the python side (`len(2)` has no
    meaning);
  - a non-integer float that happens to *round toward* a genuine node id
    (`toss=[2.5]`) is silently truncated by `np.array(..., dtype=np.int64)`
    to `2` -- causing an actual, silent toss of a real node -- where R's
    `match(2.5, id, 0L)` requires an *exact* match against the integer node
    ids and therefore treats `2.5` as "not in this tree" (warn-and-no-op);
  - `NaN` in `toss` raises `ValueError` immediately in
    `np.array(..., dtype=np.int64)`, where R's `match(NaN, id, 0L)` simply
    finds no match (again warn-and-no-op, no error at all).

Each was confirmed empirically, live against R, before writing the
corresponding test below.

Tests 8-9 are pure python-side implementation-invariant checks (no
R-comparison target -- R's own copy-on-modify semantics make an
object-identity notion meaningless there) covering `snip_rpart`'s documented
copy-on-modify contract (see the source comment atop `snip_rpart` itself):
mutating a genuinely-snipped result must never affect the original tree
dict, and even the "nothing selected" mouse-fallback early-out still
produces new, independent `splits`/`csplit`/`where` objects (though not a
new `frame` object, since `frame` is only ever rebound -- never mutated in
place -- once the function proceeds past that early-out).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import importlib
import warnings

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.snip_rpart import snip_rpart

from _r_rpart_helpers import (
    extract_r_fit,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_snip_capturing_warning,
)


def _assert_frame_matches_r(py_fit_like: dict, r_result) -> None:
    """Minimal frame-shape/var/row-id comparison (a lighter-weight sibling
    of test_snip_rpart_positive.py's `_assert_snip_matches_r`, sufficient for
    the no-op/idempotent scenarios this file focuses on, where the interest
    is "did anything change" rather than the full splits/csplit machinery)."""
    r_out = extract_r_fit(r_result)
    py_frame = py_fit_like["frame"]
    assert py_frame["var"].tolist() == r_out["var"]
    assert py_frame.index.astype(int).tolist() == r_out["frame_index"].astype(int).tolist()


# ---------------------------------------------------------------------------
# 1. Duplicate node ids within `toss` (`toss=[2, 2, 2]`): snip_rpart's own
#    `toss = np.unique(toss)` (mirroring R's `toss <- unique(toss)`) must
#    make this behave identically to `toss=[2]` -- a boundary case on the
#    "how many distinct values are actually in toss" axis.
# ---------------------------------------------------------------------------

def test_snip_duplicate_node_ids_in_toss_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    r_result, r_warning = r_snip_capturing_warning(r_fit, [2, 2, 2])
    py_snipped = snip_rpart(py_fit, [2, 2, 2])
    py_snipped_plain = snip_rpart(py_fit, [2])

    assert r_warning is None  # no "not in this tree" warning expected here
    assert py_snipped["frame"]["var"].tolist() == py_snipped_plain["frame"]["var"].tolist()
    _assert_frame_matches_r(py_snipped, r_result)


# ---------------------------------------------------------------------------
# 2. `toss` containing a mix of one genuinely-tossable node and one
#    out-of-range node number (`toss=[2, 999]`, tree has no node 999): both
#    sides must warn about the missing node *and* still carry out the
#    genuine part of the toss (node 2), rather than aborting entirely.
# ---------------------------------------------------------------------------

def test_snip_mixed_valid_and_out_of_range_toss_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    r_result, r_warning = r_snip_capturing_warning(r_fit, [2, 999])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_snipped = snip_rpart(py_fit, [2, 999])

    assert r_warning is not None and "999" in r_warning
    assert len(caught) == 1 and "999" in str(caught[0].message)
    assert py_snipped["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_frame_matches_r(py_snipped, r_result)


# ---------------------------------------------------------------------------
# 3. `toss` entirely out-of-range (`toss=[999]`, no genuinely-tossable node
#    at all): both sides warn, and the result is a complete no-op -- the
#    returned frame is identical (same vars, same row ids, same shape) to
#    the original, unsnipped fit.
# ---------------------------------------------------------------------------

def test_snip_entirely_out_of_range_toss_is_a_no_op_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    r_result, r_warning = r_snip_capturing_warning(r_fit, [999])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_snipped = snip_rpart(py_fit, [999])

    assert r_warning is not None and "999" in r_warning
    assert len(caught) == 1
    assert py_snipped["frame"].shape[0] == py_fit["frame"].shape[0]
    assert py_snipped["frame"]["var"].tolist() == py_fit["frame"]["var"].tolist()
    _assert_frame_matches_r(py_snipped, r_result)


# ---------------------------------------------------------------------------
# 4. Negative and zero node numbers (`toss=[-5, 0]`): node ids in an rpart
#    frame are always strictly positive (1-based, root == 1), so these can
#    never match anything -- both sides must treat this exactly like any
#    other out-of-range `toss`: a warn-and-no-op.
# ---------------------------------------------------------------------------

def test_snip_negative_and_zero_node_numbers_are_a_no_op_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    r_result, r_warning = r_snip_capturing_warning(r_fit, [-5, 0])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_snipped = snip_rpart(py_fit, [-5, 0])

    assert r_warning is not None
    assert len(caught) == 1
    assert py_snipped["frame"].shape[0] == py_fit["frame"].shape[0]
    _assert_frame_matches_r(py_snipped, r_result)


# ---------------------------------------------------------------------------
# 5. KNOWN GAP: `toss` passed as a bare python scalar (`toss=2`), exactly
#    the calling convention shown in `snip.rpart.Rd`'s own worked example
#    (`toss = 2`). R accepts this without complaint (a length-1 numeric
#    vector is indistinguishable from a scalar in R). Python's
#    `len(toss) == 0` guard raises `TypeError: object of type 'int' has no
#    len()` immediately, since `snip_rpart` requires an explicitly
#    list/array-like `toss` -- confirmed empirically before writing this
#    test.
# ---------------------------------------------------------------------------

def test_snip_bare_scalar_toss_is_a_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    ## R: a bare scalar `toss=2` snips node 2 with no error.
    r_result, r_warning = r_snip_capturing_warning(r_fit, 2)
    assert r_warning is None
    r_out = extract_r_fit(r_result)
    assert r_out["frame_index"].astype(int).tolist() == [1, 2, 3]

    ## Python: KNOWN GAP -- raises TypeError instead of accepting the scalar.
    with pytest.raises(TypeError, match="has no len"):
        snip_rpart(py_fit, 2)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. KNOWN GAP: `toss` containing a non-integer float that happens to
#    truncate to a genuine node id (`toss=[2.5]`, and node 2 really exists
#    in this fit). R's `match(2.5, id, 0L)` requires an exact match against
#    the (integer) node ids, so `2.5` is treated as "not in this tree" --
#    warn-and-no-op, confirmed empirically. Python's own
#    `np.array(toss, dtype=np.int64)` truncates `2.5` to `2` *before* any
#    membership test ever runs, so it silently snips the real node 2 with no
#    warning at all -- a genuine, silent value divergence, not just a
#    differently-worded error.
# ---------------------------------------------------------------------------

def test_snip_float_toss_truncating_to_a_real_node_is_a_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    assert 2 in py_fit["frame"].index  # node 2 genuinely exists in this fit

    ## R: 2.5 never exactly matches integer node id 2 -- warn-and-no-op.
    r_result, r_warning = r_snip_capturing_warning(r_fit, [2.5])
    assert r_warning is not None and "2.5" in r_warning
    r_out = extract_r_fit(r_result)
    assert r_out["frame_index"].astype(int).tolist() == py_fit["frame"].index.astype(int).tolist()

    ## Python: KNOWN GAP -- silently truncates 2.5 -> 2 and actually snips
    ## it, with no warning of any kind.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_snipped = snip_rpart(py_fit, [2.5])
    assert len(caught) == 0
    assert py_snipped["frame"].shape[0] < py_fit["frame"].shape[0]
    assert py_snipped["frame"].index.tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# 7. KNOWN GAP: `toss` containing `NaN` (`toss=[float("nan")]`). R's
#    `match(NaN, id, 0L)` simply finds no match (NaN never equals any finite
#    node id) -- warn-and-no-op, confirmed empirically, no error at all.
#    Python's `np.array(toss, dtype=np.int64)` cannot represent NaN as an
#    int64 and raises `ValueError: cannot convert float NaN to integer`
#    immediately, before any membership test runs.
# ---------------------------------------------------------------------------

def test_snip_nan_in_toss_is_a_known_gap():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    ## R: NaN never matches any node id -- warn-and-no-op, no error.
    r_result, r_warning = r_snip_capturing_warning(r_fit, [float("nan")])
    assert r_warning is not None
    r_out = extract_r_fit(r_result)
    assert r_out["frame_index"].astype(int).tolist() == py_fit["frame"].index.astype(int).tolist()

    ## Python: KNOWN GAP -- raises ValueError instead of warning-and-no-op.
    with pytest.raises(ValueError, match="NaN"):
        snip_rpart(py_fit, [float("nan")])


# ---------------------------------------------------------------------------
# 8. Implementation invariant (python-specific, no R-comparison target): a
#    genuine toss (a real subtree actually removed) must leave the
#    *original* tree dict completely untouched -- both the returned,
#    genuinely-smaller fit and the original, full-sized fit coexist
#    afterwards with their own independent `frame`/`splits`/`csplit`/`where`.
#    Mirrors test_prune_rpart_positive.py's analogous copy-safety test for
#    `prune_rpart` (which itself delegates to `snip_rpart` for any genuine
#    toss).
# ---------------------------------------------------------------------------

def test_snip_genuine_toss_leaves_the_original_tree_untouched():
    df = kyphosis_df().copy()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    original_nrow = py_fit["frame"].shape[0]
    original_vars = py_fit["frame"]["var"].tolist()
    original_where = np.asarray(py_fit["where"]).copy()

    py_snipped = snip_rpart(py_fit, [2])

    assert py_snipped is not py_fit
    assert py_snipped["frame"] is not py_fit["frame"]
    assert py_fit["frame"].shape[0] == original_nrow
    assert py_fit["frame"]["var"].tolist() == original_vars
    assert np.array_equal(np.asarray(py_fit["where"]), original_where)
    assert py_snipped["frame"].shape[0] < original_nrow


# ---------------------------------------------------------------------------
# 9. Implementation invariant (python-specific, no R-comparison target): the
#    "nothing selected" mouse-fallback early-out (`toss` omitted/empty, and
#    the interactive picker -- stubbed here via monkeypatching
#    `snip_rpart_mouse` directly, since no live graphics device exists in
#    this headless test session -- returns nothing) still follows
#    `snip_rpart`'s documented copy-on-modify contract for `splits`/
#    `csplit`/`where` (each becomes a new, independent object even though no
#    snip actually occurs) -- see the source comment atop `snip_rpart`
#    itself. `frame` is the one exception: since it is only ever *rebound*
#    (never mutated in place) once the function proceeds past this
#    early-out, sharing the original `frame` object on this particular path
#    is safe and, confirmed empirically, exactly what happens.
# ---------------------------------------------------------------------------

def test_snip_mouse_fallback_no_selection_still_copies_splits_csplit_where():
    df = kyphosis_df().copy()
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})

    snip_rpart_module = importlib.import_module("r2py_rpart.snip_rpart")
    original_mouse = snip_rpart_module.snip_rpart_mouse
    snip_rpart_module.snip_rpart_mouse = lambda tree: None
    try:
        out = snip_rpart_module.snip_rpart(py_fit)
    finally:
        snip_rpart_module.snip_rpart_mouse = original_mouse

    assert out is not py_fit
    assert out["frame"] is py_fit["frame"]
    assert out["splits"] is not py_fit["splits"]
    assert out["where"] is not py_fit["where"]
    ## same values, just independent objects
    assert out["frame"]["var"].tolist() == py_fit["frame"]["var"].tolist()
    assert np.array_equal(np.asarray(out["where"]), np.asarray(py_fit["where"]))

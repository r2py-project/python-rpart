"""Boundary/edge-case parity tests for r2py_rpart.prune_rpart itself
(imported and called *directly*), focused on scenarios specific to its own
concrete call signature (`def prune_rpart(tree, cp)`, no `**kwargs`
catch-all) that `test_prune_edge.py` (which exercises `prune_rpart` only
indirectly, through `prune(tree, **kwargs)`) cannot reach.

Tests 1-2 are genuine, confirmed parity: R's `prune.rpart` method signature
also accepts `cp` positionally and tolerates non-`tree`/`cp` extra keywords
being silently absorbed by its own `...` -- these are true edge-of-signature
checks, not value-level duplicates of test_prune_edge.py.

KNOWN, PERMANENT BEHAVIORAL GAPS (tests 3-4)
---------------------------------------------
`prune_rpart(tree, cp)` has no `**kwargs`/extra-positional catch-all
whatsoever, unlike R's `prune.rpart(tree, cp, ...)` method (whose `...`
silently absorbs *any* additional positional value or unrecognized keyword
with no error). Both scenarios below were confirmed, via a live rpy2
session, before writing this file: R succeeds unchanged; python raises a
`TypeError` immediately, at the call boundary itself (before `prune_rpart`'s
own body ever runs). These are only reachable by calling `prune_rpart`
directly -- `prune(tree, **kwargs)`'s own signature (a single positional
`tree` plus a `**kwargs` catch-all) cannot even accept an extra *positional*
argument to forward in the first place, and would raise at the `prune()`
call boundary instead for the extra-positional case (a distinct, `prune()`-
specific TypeError, not exercised here).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.prune_rpart import prune_rpart

from _r_rpart_helpers import (
    mtcars_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    run_r,
)


def _ro_nrow(r_obj) -> int:
    r_assign("prune_rpart_edge_nrow_tmp", r_obj)
    return int(np.asarray(run_r("nrow(prune_rpart_edge_nrow_tmp$frame)"))[0])


# ---------------------------------------------------------------------------
# 1. `cp` passed positionally at the extreme boundary values `Inf`/`-Inf`
#    (see test_prune_edge.py's tests 2/3 for the same boundary values via
#    keyword `cp=`) -- confirming the positional-call form agrees with R at
#    these extremes too, not just at ordinary mid-range values (already
#    covered in test_prune_rpart_positive.py's positional-call tests).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cp, expected_nrow_relation",
    [(float("inf"), "collapses"), (float("-inf"), "no_op")],
    ids=["positive_infinity", "negative_infinity"],
)
def test_prune_rpart_positional_cp_infinite_boundary_matches_r(cp, expected_nrow_relation):
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_edge_inf_tmp", r_fit)
    cp_literal = "Inf" if cp > 0 else "-Inf"
    r_pruned = run_r(f"prune.rpart(prune_rpart_edge_inf_tmp, {cp_literal})")
    r_nrow = _ro_nrow(r_pruned)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune_rpart(py_fit, cp)

    if expected_nrow_relation == "collapses":
        assert py_pruned["frame"].shape[0] == 1 == r_nrow
    else:
        assert py_pruned["frame"].shape[0] == py_fit["frame"].shape[0] == r_nrow


# ---------------------------------------------------------------------------
# 2. A harmless, *recognized* extra keyword forwarded straight through R's
#    `...` with no effect (R's `prune.rpart` has no parameter besides `tree`/
#    `cp` that changes its return value) -- `bogus=1` -- confirmed to be
#    accepted silently by R. This is the mirror-image genuine-parity check to
#    the known-gaps (tests 3-4 below): included here to make explicit that
#    the *presence* of R's permissive `...` is not itself the problem --
#    only python's total absence of any equivalent catch-all is. (This test
#    intentionally omits the python side entirely, since python's behavior
#    for this exact input is already covered as a KNOWN GAP by test 4 below;
#    it exists solely to document that R's own acceptance is a real,
#    confirmed fact and not an assumption.)
# ---------------------------------------------------------------------------

def test_prune_rpart_r_side_silently_accepts_unrecognized_kwarg_via_dots():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_edge_dots_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r("prune.rpart(prune_rpart_edge_dots_tmp, cp=0.1, bogus=1)")
    )
    assert r_message is None


# ---------------------------------------------------------------------------
# 3. KNOWN GAP: an extra *positional* argument beyond `tree`/`cp`
#    (`prune_rpart(fit, 0.1, 0.2)`). R's `prune.rpart(fit, 0.1, 0.2)` accepts
#    this with no error (the trailing `0.2` is absorbed, unused, by the
#    method's own `...`) -- confirmed empirically, `nrow(...)` matches the
#    ordinary `cp=0.1` call exactly. Python's `prune_rpart(tree, cp)` has
#    exactly two declared parameters and no catch-all, so it raises
#    `TypeError: prune_rpart() takes 2 positional arguments but 3 were given`
#    immediately, before its own body ever runs.
# ---------------------------------------------------------------------------

def test_prune_rpart_extra_positional_argument_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_edge_extrapos_tmp", r_fit)
    r_pruned_with_extra = run_r("prune.rpart(prune_rpart_edge_extrapos_tmp, 0.1, 0.2)")
    r_pruned_plain = run_r("prune.rpart(prune_rpart_edge_extrapos_tmp, 0.1)")
    ## R: the extra positional value changes nothing -- silently absorbed.
    assert _ro_nrow(r_pruned_with_extra) == _ro_nrow(r_pruned_plain)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises TypeError instead of silently ignoring it.
    with pytest.raises(TypeError, match="positional"):
        prune_rpart(py_fit, 0.1, 0.2)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 4. KNOWN GAP: an unrecognized *keyword* argument alongside a valid `cp=`
#    (`prune_rpart(fit, cp=0.1, bogus=1)`) -- the same underlying `...`-vs-
#    no-catch-all asymmetry as test 3 above (and as test_prune_edge.py's
#    test 12 for `prune()`'s own forwarding wrapper), but confirmed here to
#    reproduce identically when `prune_rpart` is called directly rather than
#    through `prune()`.
# ---------------------------------------------------------------------------

def test_prune_rpart_unrecognized_keyword_argument_is_a_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_rpart_edge_bogus_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_rpart_edge_bogus_tmp, cp=0.1, bogus=1)"))
    assert r_message is None  # R: silently ignores the unrecognized kwarg.

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    ## Python: KNOWN GAP -- raises instead of ignoring the unrecognized kwarg.
    with pytest.raises(TypeError, match="bogus"):
        prune_rpart(py_fit, cp=0.1, bogus=1)  # type: ignore[call-arg]

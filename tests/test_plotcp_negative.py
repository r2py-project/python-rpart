"""Negative-path parity tests for r2py_rpart.plotcp vs. R's rpart::plotcp.

plotcp is a plain, exported R function (`export(..., plotcp, ...)` in
NAMESPACE), not an S3 generic -- so a bare `plotcp(x, ...)` call reaches R's
`inherits(x, "rpart")` legitimacy check directly for any `x`, exactly like
printcp (see test_printcp_negative.py's own note on this point). All R-side
calls below run inside a no-op `pdf(NULL)` graphics device (via
`_r_rpart_helpers.r_plotcp_error()`), so they never try to open a real
display in a headless test environment.

plotcp.py's explicit `raise` sites are, in this exact order:
  1. `upper not in ('size', 'splits', 'none')`                -> ValueError
  2. `not isinstance(x, dict) or 'cptable' not in x`            -> TypeError
  3. `p_rpart.ndim < 2 or p_rpart.shape[1] < 5`                  -> ValueError

Notably, unlike printcp.py (`x.get('_rpart_class') != 'rpart'`), plotcp.py's
legitimacy check is *only* `isinstance(x, dict) and 'cptable' in x` -- it
never inspects `_rpart_class` at all. This is a real, structural difference
from R's `inherits(x, "rpart")` (which checks the S3 class attribute, not
merely "does this list happen to have a cptable element") -- see test 8
below, a genuine KNOWN GAP (not just a message-wording difference).

Each test triggers an error condition on both sides and asserts that *both*
raise; if both raise but with differently-worded messages,
`assert_python_and_r_errors_agree` warns rather than fails (error text is
not part of rpart's documented contract) -- see tests/_r_rpart_helpers.py.
KNOWN GAP tests (where one side raises and the other doesn't) are called out
explicitly and kept in place even though they are expected to fail, per this
test-suite family's established convention (see test_printcp_negative.py).
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart.plotcp import plotcp

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    r_error_message,
    r_matrix_literal,
    r_plotcp_error,
    r_plotcp_runs_without_error,
    r_rpart_like_expr,
    run_r,
)


_VALID_CPTABLE = np.array(
    [
        [0.5, 0, 1.0, 1.05, 0.10],
        [0.2, 1, 0.6, 0.70, 0.08],
        [0.01, 2, 0.4, 0.55, 0.07],
    ]
)


# ---------------------------------------------------------------------------
# 1-5. `x` is not a legitimate "rpart" object at all: None, a plain list, a
#      bare string, an empty dict, and a plain int. plotcp.py's own check
#      (`not isinstance(x, dict) or 'cptable' not in x`) raises TypeError for
#      all of these; R's `inherits(x, "rpart")` raises the same
#      "Not a legitimate ..." error for the R-equivalent value in each case.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_x, r_expr",
    [
        (None, "NULL"),
        ([1, 2, 3], "c(1, 2, 3)"),
        ("hello", '"hello"'),
        ({}, "list()"),
        (5, "5"),
    ],
    ids=["none", "list", "string", "empty_dict", "int"],
)
def test_plotcp_invalid_x_raises(bad_x, r_expr):
    with pytest.raises(Exception) as exc_info:
        plotcp(bad_x)

    r_message = r_plotcp_error(r_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid x={bad_x!r}")


# ---------------------------------------------------------------------------
# 6. A non-empty dict that simply has no 'cptable' key at all (as opposed to
#    the totally-empty dict in test 4 above) -- exercises the `'cptable' not
#    in x` half of plotcp.py's boolean check independently of the
#    `not isinstance(x, dict)` half.
# ---------------------------------------------------------------------------

def test_plotcp_dict_missing_cptable_key_raises():
    run_r('x_no_cptable <<- structure(list(frame = 1), class = "rpart")')
    r_message = r_plotcp_error("x_no_cptable")

    with pytest.raises(Exception) as exc_info:
        plotcp({"frame": 1})

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="dict with no 'cptable' key")


# ---------------------------------------------------------------------------
# 7. Invalid `upper=` value ("bogus", not one of "size"/"splits"/"none"):
#    plotcp.py raises ValueError directly; R's `match.arg(upper)` raises its
#    own "'arg' should be one of ..." error.
# ---------------------------------------------------------------------------

def test_plotcp_invalid_upper_raises():
    expr = r_rpart_like_expr(_VALID_CPTABLE)
    r_message = r_plotcp_error(expr, upper="bogus")

    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": _VALID_CPTABLE}, upper="bogus")

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context='upper="bogus"')


# ---------------------------------------------------------------------------
# 8. KNOWN GAP: a dict that "looks like" a legitimate fit -- it carries a
#    perfectly valid 5-column `cptable` -- but was never actually blessed as
#    an "rpart" object (no class marker at all, python-side; R's
#    `inherits()` check fails on a class-less list). plotcp.py's legitimacy
#    check is *only* `isinstance(x, dict) and 'cptable' in x`, with no
#    analogue of printcp.py's `_rpart_class` check -- so it happily proceeds
#    and plots. R's `inherits(x, "rpart")`, by contrast, unconditionally
#    rejects any object lacking the "rpart" S3 class, regardless of which
#    named elements the list happens to contain. This is a genuine,
#    structural divergence (one side raises, the other silently succeeds),
#    not a wording difference -- the assertion below is *expected to fail*
#    and is kept in place to document it (per this suite's established
#    convention; see test_printcp_negative.py's own `_rpart_class`-related
#    tests for the analogous, but successfully-caught, case in printcp).
# ---------------------------------------------------------------------------

def test_plotcp_valid_looking_dict_without_rpart_class_known_gap():
    run_r(f"x_unclassed <<- list(cptable = {r_matrix_literal(_VALID_CPTABLE)})")
    r_message = r_error_message(lambda: run_r("plotcp(x_unclassed)"))
    assert r_message is not None  # sanity: R does reject the class-less list

    py_raised = False
    try:
        plotcp({"cptable": _VALID_CPTABLE})
    except Exception:
        py_raised = True

    # KNOWN GAP: expected to fail -- plotcp.py has no `_rpart_class`-style
    # check at all, so a plain dict with a valid 'cptable' key sails
    # through, unlike R's `inherits(x, "rpart")`.
    assert py_raised, "KNOWN GAP: plotcp.py does not reject a class-less dict with a valid 'cptable'"


# ---------------------------------------------------------------------------
# 9. `cptable` with fewer than 5 columns (only 3: CP/nsplit/rel error, i.e.
#    an `xval=0` fit's cptable) -- plotcp.Rd explicitly documents that
#    plotcp() requires cross-validation results. plotcp.py's
#    `p_rpart.shape[1] < 5` raises ValueError directly; R's `ncol(p.rpart) <
#    5L` raises the same documented "'cptable' does not contain
#    cross-validation results" message (matched near-verbatim by
#    plotcp.py's own error text).
# ---------------------------------------------------------------------------

def test_plotcp_cptable_without_cross_validation_columns_raises():
    cptable_3col = np.array([[0.5, 0, 1.0], [0.01, 1, 0.3]])
    run_r(f'x_3col <<- structure(list(cptable = {r_matrix_literal(cptable_3col)}), class = "rpart")')
    r_message = r_plotcp_error("x_3col")
    assert r_message is not None and "cross-validation" in r_message

    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": cptable_3col})

    assert "cross-validation" in str(exc_info.value)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="3-column (xval=0) cptable")


# ---------------------------------------------------------------------------
# 10. Calling plotcp() with no arguments at all (`x` missing entirely, not
#     just invalid): Python's ordinary missing-required-positional-argument
#     TypeError vs. R's "argument \"x\" is missing, with no default".
# ---------------------------------------------------------------------------

def test_plotcp_missing_required_x_argument_raises():
    r_message = r_error_message(lambda: run_r("plotcp()"))

    with pytest.raises(Exception) as exc_info:
        plotcp()  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="plotcp() with no arguments")


# ---------------------------------------------------------------------------
# 11. KNOWN GAP (check-order divergence): `x` is illegitimate (None) *and*
#     `upper` is invalid ("bogus"), simultaneously. plotcp.py validates
#     `upper` *before* `x`'s legitimacy (see the raise-site ordering in this
#     file's module docstring), so python's error concerns `upper`; R's
#     `plotcp()` checks `inherits(x, "rpart")` *before* `match.arg(upper)`
#     (see rpart/R/plotcp.R), so R's error concerns `x`. Both sides still
#     raise (so this does not violate the "both raise" pass condition, and
#     is not asserted as a hard failure below), but the *reason* differs
#     structurally, not just in wording -- documented explicitly here rather
#     than folded silently into test 7's message-mismatch warning.
# ---------------------------------------------------------------------------

def test_plotcp_invalid_x_and_invalid_upper_together_check_order_differs():
    r_message = r_plotcp_error("NULL", upper="bogus")
    assert r_message is not None and "legitimate" in r_message  # R complains about x first

    with pytest.raises(Exception) as exc_info:
        plotcp(None, upper="bogus")
    py_message = str(exc_info.value)
    assert "upper" in py_message  # python complains about upper first

    # Both sides raise (the documented negative-test pass condition), but
    # for structurally different reasons -- warn rather than silently treat
    # this as an ordinary message-wording mismatch.
    assert_python_and_r_errors_agree(
        py_message, r_message, context="x=None and upper='bogus' simultaneously (check-order divergence)"
    )


# ---------------------------------------------------------------------------
# 12. `cptable` as a 1-D vector (not a 2-D matrix at all) -- e.g. a
#     corrupted/malformed fit whose `cptable` collapsed to a single row.
#     plotcp.py's explicit `p_rpart.ndim < 2` check raises ValueError with
#     the same "'cptable' does not contain cross-validation results" text
#     used for the too-few-columns case; R's `ncol()` on a plain vector
#     returns NULL, and `if (NULL < 5L)` (a zero-length logical) raises R's
#     own distinct "argument is of length zero" error -- both raise, for
#     related but differently-worded reasons.
# ---------------------------------------------------------------------------

def test_plotcp_one_dimensional_cptable_raises():
    vec = np.array([0.5, 0.2, 0.05, 0.01, 0.1])
    run_r("x_vec <<- structure(list(cptable = c(0.5, 0.2, 0.05, 0.01, 0.1)), class = \"rpart\")")
    r_message = r_plotcp_error("x_vec")
    assert r_message is not None

    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": vec})

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="1-D vector cptable")


# ---------------------------------------------------------------------------
# 13. `cptable` as a bare python list-of-lists (neither numpy.ndarray nor
#     pandas.DataFrame) -- plotcp.py's `hasattr(p_rpart, 'to_numpy')` guard
#     is False for a plain list, so it falls straight through to
#     `p_rpart.ndim`, which a python `list` simply does not have, raising an
#     *unrelated* AttributeError rather than the documented
#     TypeError/ValueError -- an internal implementation leak, not one of
#     plotcp.py's own deliberate `raise` sites. R's own equivalent (a plain
#     `list()` of numeric vectors, rather than a `matrix()`) is accepted by
#     `ncol()` no better -- it also returns NULL there (a list has no `dim`
#     attribute either) -- so R raises too (the same "argument is of length
#     zero" error as test 12's 1-D vector case). Both sides raise, so this
#     is not a KNOWN GAP requiring a special assertion, but the *kind* of
#     error differs (AttributeError vs. a `stop()`-raised condition), so is
#     documented explicitly here.
# ---------------------------------------------------------------------------

def test_plotcp_list_of_lists_cptable_raises():
    run_r(
        "x_listcp <<- structure(list(cptable = list(c(0.5, 0, 1.0, 1.0, 0.05), "
        "c(0.05, 1, 0.6, 0.9, 0.04))), class = \"rpart\")"
    )
    r_message = r_plotcp_error("x_listcp")
    assert r_message is not None

    cptable_list = [[0.5, 0, 1.0, 1.0, 0.05], [0.05, 1, 0.6, 0.9, 0.04]]
    with pytest.raises(Exception) as exc_info:
        plotcp({"cptable": cptable_list})
    assert isinstance(exc_info.value, AttributeError)

    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="bare list-of-lists cptable (not ndarray/DataFrame)"
    )


# ---------------------------------------------------------------------------
# 14. KNOWN GAP (the reverse asymmetry from test 8): `lty=5`, an integer
#     outside plotcp.py's own `_lty_map` (only 1-4 are mapped to matplotlib
#     linestyle strings; `.get(lty, lty)` falls back to the *raw integer* 5
#     unchanged, which matplotlib's `Line2D`/`axhline` rejects as an invalid
#     linestyle). R natively supports numeric `lty` values up to 6 (and even
#     cycles beyond that), so R's `abline(..., lty = 5)` succeeds without
#     complaint (confirmed empirically via `r_plotcp_runs_without_error`
#     below). Here python raises but R does not -- the opposite direction of
#     test 8's gap -- kept in place as a documented, expected-to-fail
#     assertion. (minline defaults to True, so the offending `ax.axhline(...,
#     linestyle=linestyle, ...)` call is actually reached.)
# ---------------------------------------------------------------------------

def test_plotcp_unmapped_integer_lty_known_gap():
    expr = r_rpart_like_expr(_VALID_CPTABLE)
    assert r_plotcp_runs_without_error(expr, lty=5)  # sanity: R accepts lty=5 fine

    py_raised = False
    try:
        plotcp({"cptable": _VALID_CPTABLE}, lty=5)
    except Exception:
        py_raised = True

    # KNOWN GAP: expected to fail -- R accepts lty=5; plotcp.py's unmapped
    # int falls through to matplotlib, which rejects it as an invalid
    # linestyle.
    assert not py_raised, "KNOWN GAP: plotcp.py raises for lty=5 (unmapped int), unlike R"

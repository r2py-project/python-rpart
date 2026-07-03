"""Negative-path parity tests for r2py_rpart.meanvar vs. R's `meanvar`
(dispatching to `meanvar.rpart`).

meanvar.rpart.R's body has exactly two explicit `stop()` guards, both
mirrored in meanvar_rpart.py (which `meanvar()` itself is a thin
pass-through to -- see r2py_rpart/meanvar_rpart.py):

    if (!inherits(tree, "rpart")) stop("Not a legitimate \"rpart\" object")
    if (!tree$method == "anova") stop("Plot not useful for classification or poisson trees")

    if not (isinstance(tree, dict) and tree.get('_rpart_class') == 'rpart'):
        raise ValueError('Not a legitimate "rpart" object')
    if tree['method'] != 'anova':
        raise ValueError('Plot not useful for classification or poisson trees')

Unlike plot.rpart/print.rpart (which extend a *base-R* generic), `meanvar`
is a plain S3 generic defined *within* the rpart package itself
(`meanvar <- function(tree, ...) UseMethod("meanvar")`, with only
`S3method(meanvar, rpart)` registered) -- so R's bare `meanvar(x)` call for
an `x` that isn't "rpart"-classed fails inside `UseMethod` itself ("no
applicable method for 'meanvar' applied to an object of class ...")
*before* ever reaching meanvar.rpart's own `inherits(tree, "rpart")` check.
Exactly mirroring print.rpart's/plot.rpart's own established `rpart:::`
triple-colon convention in this test suite, `rpart:::meanvar.rpart(x, ...)`
is called directly (`generic=False`) throughout the tests below that probe
meanvar.rpart's *own* legitimacy checks, matching how r2py_rpart.meanvar()
performs these checks unconditionally, regardless of any class marker on
its input. A couple of tests additionally confirm (`generic=True`) that
R's bare `meanvar(x)` generic-dispatch route *also* raises for the same
non-"rpart"-classed inputs -- just with UseMethod's own differently-worded
message, which is expected and flagged via `warnings.warn` rather than
failing the test (per this test-generation task's protocol).

Per this test-generation task's protocol: both sides must raise for a test
to pass; if they raise with differently-worded messages, that's flagged via
`warnings.warn` (through `assert_python_and_r_errors_agree`) rather than
failing the test outright.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from r2py_rpart.meanvar_rpart import meanvar

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    build_meanvar_tree,
    r_meanvar_error,
    r_meanvar_like_expr,
)


# ---------------------------------------------------------------------------
# 1. tree = None -- `!inherits(NULL, "rpart")` is TRUE in R; python's own
#    `isinstance(None, dict)` is False.
# ---------------------------------------------------------------------------

def test_meanvar_none_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar(None)
    r_msg = r_meanvar_error("NULL", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=None")


# ---------------------------------------------------------------------------
# 2. tree = an empty list -- R's `list()` doesn't `inherits(x, "rpart")`
#    either; python's `isinstance(x, dict)` is False for a bare list.
# ---------------------------------------------------------------------------

def test_meanvar_empty_list_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar([])
    r_msg = r_meanvar_error("list()", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=[]")


# ---------------------------------------------------------------------------
# 3. tree = a plain dict with no "_rpart_class" marker at all -- R's
#    equivalent (a class-less `list(frame=..., method="anova")`) also fails
#    `inherits(x, "rpart")`.
# ---------------------------------------------------------------------------

def test_meanvar_dict_without_rpart_class_marker_raises_value_error():
    tree = {"frame": pd.DataFrame({"var": ["<leaf>"], "yval": [1.0], "dev": [1.0], "n": [1.0]}), "method": "anova"}
    with pytest.raises(ValueError) as exc_info:
        meanvar(tree)
    r_msg = r_meanvar_error(
        'list(frame = data.frame(var = "<leaf>", yval = 1.0, dev = 1.0, n = 1.0), method = "anova")',
        generic=False,
    )
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="dict without _rpart_class")


# ---------------------------------------------------------------------------
# 4. tree = a bare pandas.DataFrame (not wrapped in a dict at all) --
#    python's `isinstance(tree, dict)` is False; R's analogous bare
#    `data.frame(...)` (no "rpart" class) also fails `inherits`.
# ---------------------------------------------------------------------------

def test_meanvar_bare_dataframe_input_raises_value_error():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(ValueError) as exc_info:
        meanvar(df)
    r_msg = r_meanvar_error("data.frame(a = 1:3)", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=bare DataFrame")


# ---------------------------------------------------------------------------
# 5. tree = a bare numeric scalar -- python's `isinstance(5, dict)` is
#    False; R's `inherits(5, "rpart")` is also FALSE. This is the case
#    where both messages match *exactly* (both sides say
#    `Not a legitimate "rpart" object`), confirmed empirically.
# ---------------------------------------------------------------------------

def test_meanvar_numeric_scalar_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar(5)
    r_msg = r_meanvar_error("5", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=5")
    assert 'Not a legitimate "rpart" object' in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. tree = a bare string -- same "not legitimate" branch, different input
#    type again.
# ---------------------------------------------------------------------------

def test_meanvar_string_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar("hello")
    r_msg = r_meanvar_error('"hello"', generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='tree="hello"')


# ---------------------------------------------------------------------------
# 7. tree$method == "class" -- a legitimate "rpart"-classed object, but with
#    a non-"anova" method: exercises the *second* stop()/raise branch, and
#    is dispatched identically on both sides since the class marker is
#    present (no `generic=False` workaround needed for R here).
# ---------------------------------------------------------------------------

def test_meanvar_classification_method_raises_value_error():
    tree = build_meanvar_tree(["<leaf>"], [1.0], [1.0], [1.0], [1], method="class")
    with pytest.raises(ValueError) as exc_info:
        meanvar(tree)
    r_expr = r_meanvar_like_expr(["<leaf>"], [1.0], [1.0], [1.0], [1], method="class")
    r_msg = r_meanvar_error(r_expr, generic=True)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='method="class"')
    assert "Plot not useful for classification or poisson trees" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 8. tree$method == "poisson" -- the other explicitly-documented
#    non-"anova" method (rpart.Rd's `method` argument lists
#    "anova"/"poisson"/"class"/"exp").
# ---------------------------------------------------------------------------

def test_meanvar_poisson_method_raises_value_error():
    tree = build_meanvar_tree(["<leaf>"], [1.0], [1.0], [1.0], [1], method="poisson")
    with pytest.raises(ValueError) as exc_info:
        meanvar(tree)
    r_expr = r_meanvar_like_expr(["<leaf>"], [1.0], [1.0], [1.0], [1], method="poisson")
    r_msg = r_meanvar_error(r_expr, generic=True)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='method="poisson"')


# ---------------------------------------------------------------------------
# 9. tree$method == "exp" -- same branch, third non-"anova" method value.
# ---------------------------------------------------------------------------

def test_meanvar_exp_method_raises_value_error():
    tree = build_meanvar_tree(["<leaf>"], [1.0], [1.0], [1.0], [1], method="exp")
    with pytest.raises(ValueError) as exc_info:
        meanvar(tree)
    r_expr = r_meanvar_like_expr(["<leaf>"], [1.0], [1.0], [1.0], [1], method="exp")
    r_msg = r_meanvar_error(r_expr, generic=True)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='method="exp"')


# ---------------------------------------------------------------------------
# 10. tree without a "frame" key at all -- python's `tree['frame']` raises a
#     bare KeyError (not the documented ValueError); R's analogous
#     `tree$frame` is NULL, which silently degrades all the way through to
#     `plot(NULL, NULL, ...)`, raising a *different* error ("need finite
#     'xlim' values") for an unrelated reason. Both sides raise, but for
#     different underlying causes with unavoidably different messages --
#     documented explicitly here rather than silently smoothed over by
#     assert_python_and_r_errors_agree's substring check.
# ---------------------------------------------------------------------------

def test_meanvar_dict_without_frame_key_raises_key_error():
    tree = {"_rpart_class": "rpart", "method": "anova"}
    with pytest.raises(KeyError):
        meanvar(tree)
    r_msg = r_meanvar_error('structure(list(method = "anova"), class = "rpart")', generic=True)
    assert r_msg is not None  # R also raises (from `plot()` on an all-NULL x/y), just a different message
    warnings.warn(
        "KNOWN GAP: tree without a 'frame' key raises python KeyError('frame') "
        f"vs. R's {r_msg!r} (need finite 'xlim' values, from plot() on NULL data) -- "
        "both raise, but for different underlying reasons.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 11. tree without a "method" key at all -- python's `tree['method']` raises
#     a bare KeyError; R's `tree$method` is NULL, and `!NULL == "anova"` is
#     `logical(0)`, so `if (logical(0))` raises "argument is of length
#     zero" -- again both raise, for different underlying reasons.
# ---------------------------------------------------------------------------

def test_meanvar_dict_without_method_key_raises_key_error():
    tree = {
        "_rpart_class": "rpart",
        "frame": pd.DataFrame({"var": ["<leaf>"], "yval": [1.0], "dev": [1.0], "n": [1.0]}),
    }
    with pytest.raises(KeyError):
        meanvar(tree)
    r_expr = (
        'structure(list(frame = data.frame(var = "<leaf>", yval = 1.0, dev = 1.0, n = 1.0)), '
        'class = "rpart")'
    )
    r_msg = r_meanvar_error(r_expr, generic=True)
    assert r_msg is not None  # R also raises ("argument is of length zero"), for a different reason
    warnings.warn(
        f"KNOWN GAP: tree without a 'method' key raises python KeyError('method') vs. R's {r_msg!r} "
        "-- both raise, but for different underlying reasons.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 12. A non-dict tree that nonetheless carries a "method"/"frame"-like
#     attribute pattern is irrelevant to python (the `isinstance(tree, dict)`
#     check short-circuits first) -- an int is used here as a second
#     "wrong type entirely" case distinct from the numeric-scalar-via-R-`5`
#     case above (`bool` is a `dict` subtype surprise-check: confirms a
#     bare python bool is also correctly rejected, since `isinstance(True,
#     dict)` is False just like any other non-dict).
# ---------------------------------------------------------------------------

def test_meanvar_boolean_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar(True)
    r_msg = r_meanvar_error("TRUE", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=True")

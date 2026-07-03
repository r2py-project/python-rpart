"""Negative-path parity tests for r2py_rpart's `meanvar_rpart` function
itself, called *directly*, vs. R's `meanvar.rpart`.

meanvar_rpart.py's two explicit `stop()`/`raise ValueError` legitimacy
guards --

    if (!inherits(tree, "rpart")) stop("Not a legitimate \"rpart\" object")
    if (!tree$method == "anova") stop("Plot not useful for classification or poisson trees")

    if not (isinstance(tree, dict) and tree.get('_rpart_class') == 'rpart'):
        raise ValueError('Not a legitimate "rpart" object')
    if tree['method'] != 'anova':
        raise ValueError('Plot not useful for classification or poisson trees')

-- execute identically whether reached via meanvar_rpart directly or via the
meanvar() one-line pass-through, and are already exhaustively exercised (all
12 scenarios, including both `generic=True`/`generic=False` R-dispatch
routes and the KeyError-vs-R's-own-different-error "frame"/"method"-key-
missing gaps) in test_meanvar_negative.py. This file does not re-derive that
coverage; instead it targets negative-path behavior that is genuinely
specific to meanvar_rpart's own *concrete signature* -- `(tree, xlab="ave(y)",
ylab="ave(deviance)", **kwargs)`, no `*args` slot -- as opposed to meanvar()'s
`(tree, **kwargs)`.

R's `meanvar.rpart <- function(tree, xlab = "ave(y)", ylab = "ave(deviance)",
...)` accepts an arbitrary number of *extra* positional arguments via `...`
(forwarded into `plot()`/`text()`); python's meanvar_rpart, lacking a `*args`
catch-all of its own (only tree/xlab/ylab are positional, everything else
must be a *keyword* to land in `**kwargs`), raises a plain `TypeError` for a
4th positional argument -- confirmed empirically (see below) to correspond
to R *also* raising, but for an entirely unrelated reason (the extra
positional value collides with `plot.default`'s own next unnamed formal,
`xlim`, producing "invalid 'xlim' value" rather than any argument-count
complaint) -- both sides raise, message-incomparable by nature (a python
`TypeError` about argument count has no R analogue), so this is documented
as a KNOWN GAP rather than silently smoothed over.

A missing, fully-omitted `tree` argument is also exercised directly (calling
meanvar_rpart() with zero arguments at all) -- both sides raise for
essentially the same reason (a required argument was never supplied), just
phrased differently ("missing 1 required positional argument: 'tree'" vs.
R's "argument \"tree\" is missing, with no default").
"""
from __future__ import annotations

import warnings

import pytest

from r2py_rpart.meanvar_rpart import meanvar_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    build_meanvar_tree,
    r_meanvar_error,
    r_meanvar_like_expr,
)


# ---------------------------------------------------------------------------
# 1. `tree` omitted entirely (zero arguments) -- a python-signature-level
#    failure (TypeError: missing required positional argument), not the
#    documented `ValueError`; R's own missing-argument error is analogous in
#    spirit ("argument \"tree\" is missing, with no default") though
#    obviously differently worded, so this is flagged via
#    assert_python_and_r_errors_agree's warning path rather than asserted
#    for an exact match.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_missing_tree_argument_raises_type_error_on_both_sides():
    with pytest.raises(TypeError) as exc_info:
        meanvar_rpart()
    assert "tree" in str(exc_info.value)

    # r_meanvar_call_code() renders `fn + "(" + ", ".join(args) + ")"` with
    # `args = [x_expr]`; passing x_expr="" makes `", ".join([""])` itself
    # the empty string, so the generated call collapses to a genuine
    # zero-argument `rpart:::meanvar.rpart()` -- exactly the R-side
    # counterpart of the zero-argument python call above.
    r_msg = r_meanvar_error("", generic=False)
    assert r_msg is not None
    assert "tree" in r_msg
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="meanvar_rpart() with no arguments")


# ---------------------------------------------------------------------------
# 2. A 4th, unnamed positional argument (beyond tree/xlab/ylab) -- python's
#    meanvar_rpart has no `*args` catch-all (only `**kwargs`), so this is a
#    plain TypeError about argument count; R's `...` happily accepts it as an
#    extra *unnamed* argument forwarded into plot()'s own remaining formals,
#    where it collides with `xlim` and raises "invalid 'xlim' value" instead
#    -- both sides raise, for entirely unrelated reasons (confirmed
#    empirically), hence documented as a KNOWN GAP.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_extra_unnamed_positional_argument_raises_type_error_known_gap():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    with pytest.raises(TypeError, match="positional argument"):
        meanvar_rpart(tree, "a", "b", "c")

    from _r_rpart_helpers import _r_meanvar_in_null_device, r_error_message

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    call_code = f'rpart:::meanvar.rpart({r_expr}, "a", "b", "c")'
    r_msg = r_error_message(lambda: _r_meanvar_in_null_device(call_code))
    assert r_msg is not None  # R also raises: "invalid 'xlim' value" (from plot.window)
    warnings.warn(
        "KNOWN GAP: a 4th unnamed positional argument raises python "
        f"TypeError (argument-count mismatch, no *args slot) vs. R's {r_msg!r} "
        "(the extra value collides with plot.default's own xlim formal) -- "
        "both raise, for unrelated underlying reasons.",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 3. tree=None reached via meanvar_rpart *directly* (not meanvar()) --
#    re-confirms the "Not a legitimate rpart object" branch fires
#    identically when meanvar_rpart is imported and invoked on its own.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_direct_call_none_input_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar_rpart(None)
    r_msg = r_meanvar_error("NULL", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="meanvar_rpart(None)")
    assert 'Not a legitimate "rpart" object' in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4. tree$method == "class" reached via meanvar_rpart directly, with xlab
#    supplied *positionally* alongside the erroring input -- confirms the
#    second guard clause still fires correctly even when combined with the
#    positional-argument path this file otherwise focuses on.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_classification_method_direct_call_with_positional_xlab_raises_value_error():
    tree = build_meanvar_tree(["<leaf>"], [1.0], [1.0], [1.0], [1], method="class")
    with pytest.raises(ValueError) as exc_info:
        meanvar_rpart(tree, "some x label")
    r_expr = r_meanvar_like_expr(["<leaf>"], [1.0], [1.0], [1.0], [1], method="class")
    r_msg = r_meanvar_error(r_expr, xlab="some x label", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='meanvar_rpart(tree, "some x label"), method="class"')
    assert "Plot not useful for classification or poisson trees" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. A non-dict `tree` (a bare list) reached via meanvar_rpart directly, with
#    both xlab AND ylab supplied positionally -- confirms the *first* guard
#    clause (type/class check) still short-circuits before python ever tries
#    to do anything with the positionally-supplied labels.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_direct_call_list_input_with_positional_labels_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        meanvar_rpart([], "x label", "y label")
    r_msg = r_meanvar_error("list()", xlab="x label", ylab="y label", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='meanvar_rpart([], "x label", "y label")')

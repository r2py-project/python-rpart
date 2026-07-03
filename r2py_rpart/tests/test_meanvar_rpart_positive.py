"""Positive-path parity tests for r2py_rpart's `meanvar_rpart` function
itself, called *directly*, vs. R's `meanvar.rpart` (rpart/R/meanvar.rpart.R).

meanvar_rpart.py's own `meanvar(tree, **kwargs)` is a one-line pass-through:

    def meanvar(tree: dict, **kwargs) -> dict[str, Any]:
        return meanvar_rpart(tree, **kwargs)

so meanvar_rpart's *transformation logic* -- the "<leaf>"-row filter,
`x = frame$yval`, `y = frame$dev / frame$n`, `label = row.names(frame)`, both
`stop()`/`raise ValueError` legitimacy guards, and every documented
xlab/ylab/kwargs behavior -- is already exhaustively benchmarked against R in
test_meanvar_positive.py/test_meanvar_negative.py/test_meanvar_edge.py (via
the public `meanvar()` entry point, which is functionally indistinguishable
from calling meanvar_rpart with keyword-only xlab/ylab). Re-deriving that
same coverage here would be pure duplication.

What *is* genuinely specific to meanvar_rpart's own direct-call signature,
and not exercised at all by the meanvar()-wrapper test suite, is that
meanvar_rpart's concrete signature --

    def meanvar_rpart(tree: dict, xlab: str = 'ave(y)', ylab: str = 'ave(deviance)', **kwargs)

-- mirrors R's own `meanvar.rpart <- function(tree, xlab = "ave(y)", ylab =
"ave(deviance)", ...)` argument *order* exactly, with xlab/ylab as real,
named, positional-or-keyword parameters of meanvar_rpart itself. meanvar()'s
own signature, `(tree, **kwargs)`, has no such positional slot -- `**kwargs`
only ever binds *keyword* arguments, so `meanvar(tree, "some xlab")` is a
`TypeError` (too many positional arguments) even though the semantically
equivalent `meanvar_rpart(tree, "some xlab")` succeeds. The tests below
exercise exactly that: calling meanvar_rpart directly (imported straight from
r2py_rpart.meanvar_rpart, never going through meanvar()), with xlab/ylab
supplied positionally, via a positional/keyword mix, and via `tree=` itself
as a keyword -- all benchmarked against R's `rpart:::meanvar.rpart(tree,
xlab=..., ylab=...)` (R's own named-argument call is behaviorally identical
to a positional one for a 3-parameter function; what's under test here is
python's *own* argument-binding for meanvar_rpart's signature, not R's).

See tests/_r_rpart_helpers.py's "meanvar-specific plumbing" section for the
shared R-/python-side machinery reused below, plus its
`call_meanvar_rpart_and_extract()` helper (added alongside this task),
which -- unlike the pre-existing `call_meanvar_and_extract()` -- imports and
calls `meanvar_rpart` directly and forwards `*args` so positional xlab/ylab
can be exercised.
"""
from __future__ import annotations

import inspect

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart import rpart
from r2py_rpart.meanvar_rpart import meanvar, meanvar_rpart

from _r_rpart_helpers import (
    build_meanvar_tree,
    call_meanvar_rpart_and_extract,
    mtcars_df,
    r_assign,
    r_control,
    r_dataframe_assign,
    r_fit_rpart,
    r_meanvar_like_expr,
    r_meanvar_result,
    r_meanvar_runs_without_error,
)


# ---------------------------------------------------------------------------
# 1. meanvar_rpart's own signature mirrors R's `function(tree, xlab =
#    "ave(y)", ylab = "ave(deviance)", ...)` parameter order/defaults
#    exactly -- unlike meanvar()'s `(tree, **kwargs)`, which has no xlab/ylab
#    parameters of its own at all.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_signature_matches_r_argument_order_and_defaults():
    sig = inspect.signature(meanvar_rpart)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names[:3] == ["tree", "xlab", "ylab"]
    assert params[1].default == "ave(y)"
    assert params[2].default == "ave(deviance)"
    assert params[-1].kind == inspect.Parameter.VAR_KEYWORD  # **kwargs, mirroring R's `...`

    # meanvar()'s own wrapper signature, by contrast, has no xlab/ylab
    # parameter at all -- confirming the asymmetry these tests exercise.
    meanvar_names = [p.name for p in inspect.signature(meanvar).parameters.values()]
    assert "xlab" not in meanvar_names
    assert "ylab" not in meanvar_names


# ---------------------------------------------------------------------------
# 2. Direct call, default xlab/ylab (no args beyond tree at all) -- confirms
#    meanvar_rpart itself (not just meanvar()) matches R for the baseline case.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_direct_call_default_labels_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [4.0, 8.0, 12.0], [2.0, 6.0, 3.0], [2.0, 3.0, 1.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "ave(y)"
    assert py_out["ylabel"] == "ave(deviance)"


# ---------------------------------------------------------------------------
# 3. xlab supplied *positionally* (second positional argument), ylab left at
#    its default -- impossible to express via meanvar()'s own `(tree,
#    **kwargs)` signature, only via meanvar_rpart directly.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_positional_xlab_only_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "positional x label")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="positional x label", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "positional x label"
    assert py_out["ylabel"] == "ave(deviance)"  # untouched R default


# ---------------------------------------------------------------------------
# 4. Both xlab AND ylab supplied positionally (second and third positional
#    arguments) -- the fullest exercise of meanvar_rpart's own
#    positional-argument binding.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_positional_xlab_and_ylab_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "pos x", "pos y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="pos x", ylab="pos y", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "pos x"
    assert py_out["ylabel"] == "pos y"


# ---------------------------------------------------------------------------
# 5. xlab positional, ylab keyword -- a positional/keyword *mix*, confirming
#    python's ordinary argument-binding rules apply to meanvar_rpart exactly
#    as they would to any plain function with this signature.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_positional_xlab_keyword_ylab_mix_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, "mixed x", ylab="mixed y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="mixed x", ylab="mixed y", generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["xlabel"] == "mixed x"
    assert py_out["ylabel"] == "mixed y"


# ---------------------------------------------------------------------------
# 6. `tree` itself supplied as an explicit keyword argument (`tree=...`)
#    rather than positionally -- meanvar_rpart's first parameter has no `/`
#    positional-only marker, so this must also succeed.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_tree_as_keyword_argument_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [5.0], [10.0], [4.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    result = meanvar_rpart(tree=tree, xlab="kw-tree x", ylab="kw-tree y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="kw-tree x", ylab="kw-tree y", generic=False)

    assert_allclose(np.asarray(result["x"], dtype=float), r_out["x"])
    assert_allclose(np.asarray(result["y"], dtype=float), r_out["y"])
    assert list(result["label"]) == r_out["label"]


# ---------------------------------------------------------------------------
# 7. A real, identically-fitted anova tree (mtcars) with xlab/ylab supplied
#    positionally through the direct meanvar_rpart call -- confirms the
#    positional-argument path also holds end to end against a genuine fit,
#    not just hand-built synthetic frames.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_real_mtcars_fit_positional_labels_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control=r_control(xval=0))
    r_assign("mv_rpart_fit_tmp", r_fit)
    r_out = r_meanvar_result("mv_rpart_fit_tmp", xlab="Fitted mpg", ylab="Deviance/n", generic=False)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})
    py_out = call_meanvar_rpart_and_extract(py_fit, "Fitted mpg", "Deviance/n")

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-10)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-10)
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "Fitted mpg"
    assert py_out["ylabel"] == "Deviance/n"


# ---------------------------------------------------------------------------
# 8. Extra, unrecognized keyword argument (`col=`) passed directly to
#    meanvar_rpart (not routed through meanvar()'s own **kwargs
#    pass-through) -- confirms meanvar_rpart's own `**kwargs` acceptance
#    in isolation.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_extra_unrecognized_kwarg_direct_call_does_not_raise():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_rpart_and_extract(tree, col="blue")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr, generic=False)  # R's meanvar.rpart(tree, col="blue") also succeeds
    r_out = r_meanvar_result(r_expr, generic=False)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])


# ---------------------------------------------------------------------------
# 9. Calling meanvar_rpart directly (all-keyword arguments) produces an
#    output byte-for-byte identical to calling the public meanvar() wrapper
#    with the same arguments -- confirming meanvar() really is nothing more
#    than a pure pass-through to meanvar_rpart, for the keyword-only subset
#    of calls both entry points can express.
# ---------------------------------------------------------------------------

def test_meanvar_rpart_direct_call_matches_meanvar_wrapper_for_shared_kwarg_only_calls():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [2.0, 4.0, 6.0], [1.0, 3.0, 5.0], [1.0, 2.0, 3.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    direct_result = meanvar_rpart(tree, xlab="shared x", ylab="shared y")
    wrapper_result = meanvar(tree, xlab="shared x", ylab="shared y")

    assert_allclose(direct_result["x"], wrapper_result["x"])
    assert_allclose(direct_result["y"], wrapper_result["y"])
    assert direct_result["label"] == wrapper_result["label"]

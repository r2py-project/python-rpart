"""Negative-path parity tests for r2py_rpart.prune_rpart itself (imported and
called *directly*), focused strictly on argument-count/argument-name errors
that are specific to `prune_rpart`'s own concrete signature
(`def prune_rpart(tree, cp)`, no `**kwargs` catch-all) and therefore are not
reachable through `r2py_rpart.prune.prune(tree, **kwargs)` -- the thin
wrapper `test_prune_negative.py` already benchmarks exhaustively for every
*value*-level (malformed-tree/malformed-cp) error scenario.

Both "missing tree" and "missing cp" are already exercised in
test_prune_negative.py, but *through* `prune()`'s own name/signature (its
TypeError message says "prune()", not "prune_rpart()") -- calling
`prune_rpart` directly here is not a value-level duplicate: it is the only
way to confirm `prune_rpart`'s *own* missing-argument error text
(`"prune_rpart() missing ... argument(s)"`), which is a distinct, genuinely
new assertion. `prune()`'s wrapper forwards every kwarg through untouched
(`prune_rpart(tree, **kwargs)`), so R's own message (which does not care
which python function ends up calling it) is identical in both cases; only
the python-side function name embedded in the error text differs.

An extra-positional-argument scenario (`prune_rpart(fit, 0.1, 0.2)`) and an
unrecognized-keyword-argument scenario (`prune_rpart(fit, cp=0.1, bogus=1)`)
were also investigated live against R before writing this file: in both
cases R's own `prune.rpart(...)` method does **not** raise (the extra
value/keyword is silently absorbed by the method's own `...`), while
python's `prune_rpart(...)` raises a `TypeError` immediately, since it has no
`**kwargs`/extra-positional catch-all of its own -- confirmed empirically.
Since this suite's negative-test protocol requires *both* sides to raise to
pass, both scenarios are instead recorded as KNOWN GAPS in
test_prune_rpart_edge.py (matching this codebase's established convention
for R-succeeds/python-raises asymmetries -- see test_prune_edge.py's own
test 12 for the same asymmetry already documented against `prune()`), not
here.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import pytest

from r2py_rpart import rpart
from r2py_rpart.prune_rpart import prune_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    mtcars_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. `cp` missing entirely, but called via `prune_rpart` directly (not
#    through `prune()`'s wrapper): python's own missing-required-positional-
#    argument TypeError names `prune_rpart` itself
#    (`"prune_rpart() missing 1 required positional argument: 'cp'"`),
#    confirmed empirically -- distinct wording from `prune()`'s own version
#    of the same underlying scenario in test_prune_negative.py, though both
#    are compared against the identical R error
#    (`argument "cp" is missing, with no default`).
# ---------------------------------------------------------------------------

def test_prune_rpart_missing_cp_argument_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0)")
    r_assign("prune_rpart_missing_cp_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_rpart_missing_cp_tmp)"))

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})
    with pytest.raises(TypeError) as exc_info:
        prune_rpart(py_fit)  # type: ignore[call-arg]

    assert "prune_rpart" in str(exc_info.value)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="prune_rpart(fit) with cp omitted")


# ---------------------------------------------------------------------------
# 2. Both `tree` and `cp` missing entirely (`prune_rpart()` with zero
#    arguments): python's TypeError names *both* missing parameters at once
#    (`"prune_rpart() missing 2 required positional arguments: 'tree' and
#    'cp'"`, confirmed empirically) -- R's own `prune.rpart()` instead
#    reports only the *first* missing argument it actually needs
#    (`argument "tree" is missing, with no default`, since `cp` is never
#    even reached before `tree` fails).  Both raise, so this is a genuine
#    passing parity test (message wording differs but that is tolerated by
#    `assert_python_and_r_errors_agree`'s warn-not-fail rule); it is included
#    here specifically because it depends on `prune_rpart`'s own signature
#    having exactly two required, catch-all-free parameters, unlike
#    `prune(tree, **kwargs)` (whose own zero-argument call instead fails on
#    the *wrapper's* missing `tree`, already covered in
#    test_prune_negative.py, before `prune_rpart` is ever reached).
# ---------------------------------------------------------------------------

def test_prune_rpart_missing_all_arguments_raises():
    r_message = r_error_message(lambda: run_r("prune.rpart()"))

    with pytest.raises(TypeError) as exc_info:
        prune_rpart()  # type: ignore[call-arg]

    assert "prune_rpart" in str(exc_info.value)
    assert "tree" in str(exc_info.value) and "cp" in str(exc_info.value)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="prune_rpart() with no arguments")

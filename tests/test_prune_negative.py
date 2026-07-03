"""Negative-path parity tests for r2py_rpart.prune (and its underlying
prune_rpart) vs. R's rpart::prune.rpart (called directly -- see module
docstring of test_prune_positive.py for why the direct-call form, not the
`prune(...)` S3 generic, is this suite's comparison target: python's own
prune()/prune_rpart() never dispatch through any generic of their own).

IMPORTANT CAVEAT, discovered empirically before writing any test below:
prune.rpart.R's own body (rpart/R/prune.rpart.R) has *no* `inherits(tree,
"rpart")` legitimacy check of its own (unlike print.rpart/plot.rpart/
plotcp/printcp) -- it just does `tree$frame`, `tree$cptable`, etc. directly.
Since R's `$` operator on `NULL`/a plain `list()` (even one missing every
expected named component) just silently returns `NULL` and keeps
propagating through empty-vector arithmetic, `prune.rpart(tree, cp=...)`
frequently *succeeds* as a silent no-op on inputs that r2py_rpart's plain
dict-indexing (`tree['frame']`) raises immediately on (`None`, `{}`, a
component-missing dict, a pandas DataFrame with no "frame" column, ...).
Those asymmetric cases (R succeeds / python raises) fail this suite's own
"both sides must raise" pass condition for a *negative* test and are
instead documented as confirmed, permanent behavioral gaps in
test_prune_edge.py, per this codebase's established convention (see e.g.
test_printcp_positive.py's KNOWN GAP tests) of keeping such findings visible
rather than silently dropped.

That said, prune.rpart.R's *own* body is not the only place a legitimacy
check could be reached: whenever `toss` actually ends up non-empty,
prune.rpart.R calls `snip.rpart(tree, toss)` -- and `snip.rpart.R` (unlike
prune.rpart.R) *does* open with `if (!inherits(x, "rpart")) stop("Not an
\"rpart\" object")`, matched essentially verbatim by r2py_rpart's own
`snip_rpart._rpart_class` check (`raise TypeError('Not an "rpart" object')`
-- the identical message, modulo R's "Error in snip.rpart(tree, toss) : "
call-site prefix). Test 10 below exercises exactly that shared code path
directly (a fully valid, real fit with its class marker stripped, pruned at
a cp that genuinely tosses something) -- confirmed empirically to raise the
*same* message on both sides, unlike every other "malformed tree" scenario
in this module.

The remaining tests below are restricted to genuine cases where *both*
sides are confirmed (via a live rpy2 session, before writing these tests)
to raise: tree values that are atomic (non-list-like) in R terms -- a bare
string, number, boolean, or vector, all of which trip R's "$ operator is
invalid for atomic vectors" and python's "is not subscriptable"/"indices
must be" family of TypeErrors identically -- plus missing-required-argument
cases and `cp` values whose *type* (not just value) numpy/pandas cannot
coerce into a float64 comparison/assignment (a length-mismatched vector, a
complex number), which R's own arithmetic likewise rejects (with a
different, but component-for-component analogous, error).

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing
(`r_prune_error`, `assert_python_and_r_errors_agree`).
"""
from __future__ import annotations

import pytest

from r2py_rpart import rpart
from r2py_rpart.prune import prune

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    mtcars_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_prune_error,
    run_r,
)


# ---------------------------------------------------------------------------
# 1-4. `tree` is an atomic (non-list-like) R value: a bare string, an int, a
#      python list (-> R's `c(1,2,3)`, itself an atomic numeric vector), and
#      a bool (-> R's `TRUE`, a length-1 logical vector). R's `tree$frame`
#      raises "$ operator is invalid for atomic vectors" identically for
#      every one of these (confirmed empirically); python's own
#      `tree['frame']` raises a (differently-worded, but always present)
#      TypeError for each, since none of these types support string-key
#      subscripting.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_tree, r_expr",
    [
        ("hello", '"hello"'),
        (5, "5"),
        ([1, 2, 3], "c(1, 2, 3)"),
        (True, "TRUE"),
    ],
    ids=["string", "int", "list", "bool"],
)
def test_prune_atomic_tree_raises(bad_tree, r_expr):
    r_message = r_prune_error(r_expr, cp=0.1)

    with pytest.raises(Exception) as exc_info:
        prune(bad_tree, cp=0.1)

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"atomic tree={bad_tree!r}")


# ---------------------------------------------------------------------------
# 5. `cp` missing entirely (but `tree` is a genuine, valid fit): R's
#    `argument "cp" is missing, with no default` (raised lazily, the first
#    time `cp` is actually referenced inside prune.rpart's body) vs.
#    python's ordinary missing-required-positional-argument TypeError
#    (`prune_rpart(tree, cp)` has no default for `cp` either).
# ---------------------------------------------------------------------------

def test_prune_missing_cp_argument_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0)")
    r_assign("prune_missing_cp_fit_tmp", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_missing_cp_fit_tmp)"))

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        prune(py_fit)  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="prune(fit) with cp omitted")


# ---------------------------------------------------------------------------
# 6. Both `tree` and `cp` missing entirely: `prune.rpart()`/`prune()` with no
#    arguments at all raises R's "argument \"tree\" is missing, with no
#    default" (the *first* missing argument, checked before `cp` is ever
#    reached); python's `prune()` raises its own missing-`tree` TypeError.
# ---------------------------------------------------------------------------

def test_prune_missing_all_arguments_raises():
    r_message = r_error_message(lambda: run_r("prune.rpart()"))

    with pytest.raises(Exception) as exc_info:
        prune()  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="prune() with no arguments")


# ---------------------------------------------------------------------------
# 7. `cp` is a length-2 vector/list: R's own body never errors on the
#    `ff$complexity <= cp` comparison itself (R silently recycles), but
#    *does* error later, at `newx$cptable[length(keep), 1L] <- cp` --
#    "number of items to replace is not a multiple of replacement length" --
#    since `keep` never has exactly 2 (or a multiple of 2) rows for this
#    fit. Python's `ff['complexity'].values <= cp` raises immediately
#    instead, at the comparison itself (`ValueError: operands could not be
#    broadcast together`) -- a different site, but both sides are confirmed
#    (empirically) to raise for this input.
# ---------------------------------------------------------------------------

def test_prune_cp_length_mismatched_vector_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_fit_tmp2", r_fit)
    r_message = r_prune_error("prune_fit_tmp2", cp=[0.1, 0.2])

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    with pytest.raises(Exception) as exc_info:
        prune(py_fit, cp=[0.1, 0.2])

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="cp=[0.1, 0.2] (length mismatch)")


# ---------------------------------------------------------------------------
# 8. `cp` is a complex number: R's `ff$complexity <= cp` raises "invalid
#    comparison with complex values" directly (R has no ordering for
#    complex numbers at all); python's numpy/pandas machinery likewise
#    cannot coerce a complex scalar into the float64 `cptable` column,
#    raising a TypeError of its own (confirmed empirically -- the exact
#    raise site differs from R's, at the later `.iloc[...] = cp` assignment
#    rather than the boolean comparison itself, but both sides do raise).
# ---------------------------------------------------------------------------

def test_prune_cp_complex_number_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_fit_tmp3", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_fit_tmp3, cp=complex(real=1, imaginary=2))"))

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    with pytest.raises(Exception) as exc_info:
        prune(py_fit, cp=complex(1, 2))

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="cp=complex(1, 2)")


# ---------------------------------------------------------------------------
# 9. A misspelled keyword (`notcp=` instead of `cp=`): since `cp` is still
#    never supplied under its real name, both sides ultimately raise the
#    *same* underlying "missing cp" error as test 5 above -- R's `...`
#    silently absorbs the unrecognized `notcp` (it's never referenced) and
#    only then hits its own missing-`cp` check; python's `prune_rpart()` has
#    no `**kwargs` catch-all of its own, so it instead raises immediately
#    for the unexpected keyword. Different mechanisms, both raise.
# ---------------------------------------------------------------------------

def test_prune_misspelled_keyword_argument_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0)")
    r_assign("prune_fit_tmp4", r_fit)
    r_message = r_error_message(lambda: run_r("prune.rpart(prune_fit_tmp4, notcp=0.1)"))

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})
    with pytest.raises(Exception) as exc_info:
        prune(py_fit, notcp=0.1)  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="prune(fit, notcp=0.1)")


# ---------------------------------------------------------------------------
# 10. A dict carrying every "real" rpart fit component (frame, cptable,
#     splits, ...) but with its `_rpart_class` marker removed -- called at a
#     `cp` that genuinely tosses at least one internal node (so `toss` is
#     non-empty and prune.rpart.R's own body actually reaches its
#     `snip.rpart(tree, toss)` call). Unlike every other "malformed tree"
#     scenario in this module, R's equivalent (`class(fit) <- NULL`) *does*
#     raise here -- via `snip.rpart.R`'s own `inherits(x, "rpart")` check,
#     not prune.rpart.R's -- with a message essentially identical
#     (`Not an "rpart" object`) to r2py_rpart's own `snip_rpart` check. See
#     this module's docstring for why this is the one "unblessed object"
#     scenario that is a genuine match rather than a known gap.
# ---------------------------------------------------------------------------

def test_prune_valid_looking_dict_missing_rpart_class_marker_with_actual_toss_raises():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_assign("prune_unclassed_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r("class(prune_unclassed_fit_tmp) <- NULL; prune.rpart(prune_unclassed_fit_tmp, cp=0.1)")
    )

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    unclassed = dict(py_fit)
    del unclassed["_rpart_class"]
    with pytest.raises(TypeError) as exc_info:
        prune(unclassed, cp=0.1)

    assert str(exc_info.value) == 'Not an "rpart" object'
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="valid-looking dict missing _rpart_class, real toss"
    )

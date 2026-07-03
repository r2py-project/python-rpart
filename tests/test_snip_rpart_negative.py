"""Negative-path parity tests for r2py_rpart.snip_rpart vs. R's
rpart::snip.rpart, focused strictly on scenarios that must raise on *both*
sides. See test_snip_rpart_positive.py's module docstring for the
"non-interactive, `toss=` supplied explicitly" scope this whole suite shares,
and tests/_r_rpart_helpers.py's `r_snip`/`r_snip_error`/`r_snip_call_code`
plumbing (snip.rpart is exported directly from the rpart NAMESPACE as a
plain function, not an S3 generic/method pair, so there is no
generic-vs-direct-call distinction to make here).

Per this suite's own protocol: if both sides raise, the test passes even
when the wording differs (`assert_python_and_r_errors_agree` merely warns on
a wording mismatch); if only one side raises, the test fails outright -- any
such asymmetry belongs in test_snip_rpart_edge.py as a documented KNOWN GAP
instead.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import contextlib

import pytest

from r2py_rpart import rpart
from r2py_rpart.snip_rpart import snip_rpart
from r2py_rpart.zzz import rpart_env as _py_rpart_env

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    kyphosis_df,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    run_r,
)


@contextlib.contextmanager
def _no_prior_plot_state():
    """Ensure `snip_rpart`'s (and R's `snip.rpart`'s) mouse-fallback path
    sees no stashed device parameters left behind by any *previous* `plot()`
    call in this test session -- both `r2py_rpart.zzz.rpart_env` and R's own
    (internal) `rpart:::rpart_env` are process-wide globals that persist
    across every test in the same pytest run (rpy2 embeds a single, shared R
    session for the whole run; python's `rpart_env` is likewise a plain
    module-level dict). Since `test_plot_rpart_positive.py` genuinely calls
    `plot_rpart()`/`plot()` elsewhere in this suite, running *after* it would
    otherwise leave real device parameters behind, making the "no
    information available" error path below silently unreachable (confirmed
    empirically -- without this guard, `snip_rpart(fit)` and R's
    `snip.rpart(fit)` would instead reach the stubbed-empty `identify()`
    call and simply return the tree unchanged, no error at all).

    Saves and restores both sides' state around the test body, so no other
    test's cached plot parameters are permanently disturbed by running this
    one.
    """
    py_saved = dict(_py_rpart_env)
    _py_rpart_env.clear()
    r_backup = run_r("as.list(rpart:::rpart_env)")
    run_r("rm(list=ls(envir=rpart:::rpart_env), envir=rpart:::rpart_env)")
    try:
        yield
    finally:
        _py_rpart_env.clear()
        _py_rpart_env.update(py_saved)
        r_assign("snip_env_restore_tmp", r_backup)
        run_r(
            "list2env(get('snip_env_restore_tmp', envir=globalenv()), envir=rpart:::rpart_env)"
        )


# ---------------------------------------------------------------------------
# 1. `x` is not an "rpart" object at all -- snip_rpart's very first check
#    (`if not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart')`)
#    mirrors R's own `if (!inherits(x, "rpart")) stop(...)`, which runs
#    *before* `toss` is ever inspected. Parametrized across several
#    "obviously not an rpart fit" python/R value pairs.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "x_expr, py_x",
    [
        ("NULL", None),
        ("list()", {}),
        ("5", 5),
        ('"abc"', "abc"),
        ("data.frame()", __import__("pandas").DataFrame()),
    ],
    ids=["none", "empty_dict", "int_scalar", "string", "empty_dataframe"],
)
def test_snip_rpart_illegitimate_x_raises_on_both_sides(x_expr, py_x):
    r_message = r_error_message(lambda: run_r(f"snip.rpart({x_expr}, toss=2)"))

    with pytest.raises(TypeError) as exc_info:
        snip_rpart(py_x, [2])

    assert 'Not an "rpart" object' in str(exc_info.value)
    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context=f"snip_rpart({py_x!r}, [2])"
    )


# ---------------------------------------------------------------------------
# 2. `x` missing entirely (`snip_rpart()` with zero arguments): python's
#    TypeError names the missing positional parameter
#    (`"snip_rpart() missing 1 required positional argument: 'x'"`,
#    confirmed empirically); R's own `snip.rpart()` raises
#    `argument "x" is missing, with no default`. Both raise -- a genuine
#    (wording-differs-but-tolerated) parity pass.
# ---------------------------------------------------------------------------

def test_snip_rpart_missing_x_argument_raises_on_both_sides():
    r_message = r_error_message(lambda: run_r("snip.rpart()"))

    with pytest.raises(TypeError) as exc_info:
        snip_rpart()  # type: ignore[call-arg]

    assert "snip_rpart" in str(exc_info.value)
    assert "x" in str(exc_info.value)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="snip_rpart() with no arguments")


# ---------------------------------------------------------------------------
# 3. `toss` containing a non-numeric string element (`toss=["abc"]`):
#    python's `np.array(toss, dtype=np.int64)` raises `ValueError`
#    immediately, at the very top of `snip_rpart`'s body. R's snip.rpart
#    does *not* fail immediately -- the offending "abc" is first silently
#    dropped by the "Nodes %s are not in this tree" warning-and-filter step
#    (it never matches any integer node id) -- but that filtering leaves
#    `toss` permanently coerced to *character* type (even once empty), so
#    the later `toss %/% 2L` integer-division step (inside the descendant-
#    expansion loop) fails with `"non-numeric argument to binary operator"`.
#    Both sides do ultimately raise (confirmed empirically before writing
#    this test), just via very differently-worded errors at very different
#    points in each implementation -- exactly the "differs in wording, not
#    in outcome" case this suite's protocol is designed to tolerate.
# ---------------------------------------------------------------------------

def test_snip_rpart_non_numeric_toss_element_raises_on_both_sides():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("snip_neg_nonnumeric_tmp", r_fit)
    r_message = r_error_message(lambda: run_r('snip.rpart(snip_neg_nonnumeric_tmp, toss="abc")'))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with pytest.raises(ValueError):
        snip_rpart(py_fit, ["abc"])  # type: ignore[list-item]

    # (message wording is expected to differ completely between the two
    # sides here -- this call only records that fact via a warning, per
    # the shared helper's own contract, it does not require agreement)
    assert_python_and_r_errors_agree(
        "invalid literal for int()", r_message, context='snip_rpart(fit, ["abc"])'
    )


# ---------------------------------------------------------------------------
# 4. `toss` omitted entirely (falls through to python's own
#    `snip_rpart_mouse(x)` / R's `snip.rpart.mouse(x)` interactive fallback):
#    with no prior `plot()` call ever having stashed device parameters, both
#    implementations raise the *exact* "no information available on
#    parameters from previous call to plot()" message immediately -- neither
#    side ever reaches the actual interactive `identify()`/mouse-click loop,
#    so this is safe to exercise in a headless test session (confirmed
#    empirically to error immediately rather than hang).
# ---------------------------------------------------------------------------

def test_snip_rpart_missing_toss_raises_identical_message_on_both_sides():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("snip_neg_toss_omitted_tmp", r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with _no_prior_plot_state():
        r_message = r_error_message(lambda: run_r("snip.rpart(snip_neg_toss_omitted_tmp)"))
        with pytest.raises(RuntimeError) as exc_info:
            snip_rpart(py_fit)

    expected = "no information available on parameters from previous call to plot()"
    assert expected in str(exc_info.value)
    assert r_message is not None and expected in r_message


# ---------------------------------------------------------------------------
# 5. `toss=[]` (explicit, empty): `len(toss) == 0` takes the exact same
#    branch as `toss` omitted entirely (test 4 above) on the python side --
#    R's `missing(toss) || length(toss) == 0L` condition is likewise
#    satisfied by an explicit `toss=c()`/`toss=NULL` just as much as by
#    omitting the argument. Both again raise the identical
#    missing-plot-parameters message.
# ---------------------------------------------------------------------------

def test_snip_rpart_empty_toss_list_raises_identical_message_on_both_sides():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0)")
    r_assign("snip_neg_toss_empty_tmp", r_fit)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0})
    with _no_prior_plot_state():
        r_message = r_error_message(lambda: run_r("snip.rpart(snip_neg_toss_empty_tmp, toss=NULL)"))
        with pytest.raises(RuntimeError) as exc_info:
            snip_rpart(py_fit, [])

    expected = "no information available on parameters from previous call to plot()"
    assert expected in str(exc_info.value)
    assert r_message is not None and expected in r_message


# ---------------------------------------------------------------------------
# 6. `x` is a dict correctly tagged `_rpart_class == "rpart"` (so it passes
#    snip_rpart's own legitimacy check) but missing the `frame` component
#    entirely: python's very next line (`ff = x['frame'].copy()`) raises a
#    `KeyError`. R's equivalent malformed object (`structure(list(),
#    class="rpart")`, i.e. `$frame` silently evaluates to `NULL` rather than
#    erroring) does *not* fail at the same point -- but it still ultimately
#    raises, once `rep(1L:ff.n, ff$ncompete + ...)` is reached with
#    `ff.n == 0L` and `ff$ncompete` (`NULL`) coerced through arithmetic to
#    `numeric(0)`, giving `rep(integer(0), numeric(0))`'s sibling call an
#    invalid (empty) `times` argument -- confirmed empirically before writing
#    this test. So both sides do raise, just via completely different error
#    types/messages/call sites (`KeyError('frame')` vs. R's `"invalid
#    'times' argument"`) -- another genuine, wording-differs-but-tolerated
#    parity pass.
# ---------------------------------------------------------------------------

def test_snip_rpart_rpart_classed_dict_missing_frame_raises_on_both_sides():
    r_message = r_error_message(
        lambda: run_r('snip.rpart(structure(list(), class="rpart"), toss=2)')
    )

    with pytest.raises(KeyError):
        snip_rpart({"_rpart_class": "rpart"}, [2])

    assert r_message is not None
    # (wording is expected to differ completely -- KeyError('frame') vs. R's
    # "invalid 'times' argument" -- only the "both raise" outcome matters)

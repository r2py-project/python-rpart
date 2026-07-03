"""Negative-path parity tests for r2py_rpart.text_rpart vs. R's
`text.rpart`.

text.rpart.R's body has exactly two explicit `stop()` guards, both mirrored
verbatim in text_rpart.py:

    if (!inherits(x, "rpart")) stop("Not a legitimate \"rpart\" object")
    if (nrow(x$frame) <= 1L) stop("fit is not a tree, just a root")

    if not isinstance(x, dict) or x.get('_rpart_class') != 'rpart':
        raise ValueError('Not a legitimate "rpart" object')
    if len(frame) <= 1:
        raise ValueError('fit is not a tree, just a root')

plus one indirect failure mode inherited from `rpartco()` (called
internally, with no `parms` override, whenever `cxy`/`ax` don't already
carry pre-computed layout info): if `text_rpart()`/`text.rpart()` is called
without a *prior* `plot(x, ...)`/`plot_rpart(x, ...)` call having populated
the per-device layout parms, both sides raise the identical (R: literal;
python: a faithfully-ported RuntimeError) "no information available on
parameters from previous call to plot()" message.

Since `x` deliberately lacks any "rpart" class in most type-check cases,
R's own generic `text(x)` would dispatch to `text.default` instead of ever
reaching text.rpart's checks -- so `rpart:::text.rpart(x, ...)` is called
directly throughout (`generic=False` in `r_text_rpart_error()`), mirroring
how r2py_rpart.text_rpart() itself performs these checks unconditionally,
regardless of any class marker on its input.

Per this test-generation task's protocol: both sides must raise for a test
to pass; if they raise with differently-worded messages, that is flagged
via `warnings.warn` (through `assert_python_and_r_errors_agree`) rather
than failing the test outright.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart
from r2py_rpart.plot_rpart import plot_rpart
from r2py_rpart.text_rpart import text_rpart
from r2py_rpart.zzz import rpart_env

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    extract_frame_arrays,
    kyphosis_df,
    r_eval_capturing_warning,
    r_rpart_like_expr_for_plot,
    r_text_rpart_error,
)


@pytest.fixture(autouse=True)
def _clean_rpart_env():
    """Ensure `rpart_env['device1']` (r2py_rpart's stand-in for R's
    per-device `rpart_env`) never leaks between tests -- several tests
    below deliberately need it *absent* to exercise text_rpart's
    rpartco()-inherited "no information available" failure mode."""
    rpart_env.pop("device1", None)
    yield
    rpart_env.pop("device1", None)


# ---------------------------------------------------------------------------
# 1-6. `x` is not a legitimate "rpart" object at all: None, an int, a plain
#    string, an empty list, an empty dict, and an empty pandas DataFrame --
#    all hit text_rpart.py's first guard (`not isinstance(x, dict) or
#    x.get('_rpart_class') != 'rpart'`), mirroring R's
#    `!inherits(x, "rpart")`.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,r_expr",
    [
        (None, "NULL"),
        (5, "5"),
        ("abc", '"abc"'),
        ([], "list()"),
        ({}, "list()"),
        (pd.DataFrame(), "data.frame()"),
    ],
    ids=["none", "int", "string", "empty_list", "empty_dict", "empty_dataframe"],
)
def test_text_rpart_not_a_legitimate_rpart_object(value, r_expr):
    with pytest.raises((ValueError, TypeError)) as exc_info:
        text_rpart(value)
    r_msg = r_text_rpart_error(r_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context=f"x={value!r}")


# ---------------------------------------------------------------------------
# 7. A dict carrying a *different* class marker (mirroring an R object of
#    some unrelated S3 class, e.g. "lm") -- still fails the legitimacy
#    check on both sides, exactly like the bare-type cases above.
# ---------------------------------------------------------------------------

def test_text_rpart_wrong_class_marker_raises():
    fake = {"_rpart_class": "lm", "frame": pd.DataFrame({"var": ["<leaf>"]}, index=[1])}
    with pytest.raises(ValueError) as exc_info:
        text_rpart(fake)
    r_msg = r_text_rpart_error('structure(list(), class = "lm")')
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="wrong class marker")


# ---------------------------------------------------------------------------
# 8. A root-only tree (frame has exactly 1 row, no splits at all) -- a
#    genuine r2py_rpart.rpart() fit forced to not split via an unreachable
#    `minsplit`, hitting text_rpart.py's *second* guard
#    (`len(frame) <= 1`) rather than the type guard.
# ---------------------------------------------------------------------------

def test_text_rpart_root_only_genuine_fit_raises_value_error():
    df = kyphosis_df()
    fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class",
        control={"minsplit": 10_000},
    )
    assert fit["frame"].shape[0] == 1

    with pytest.raises(ValueError) as exc_info:
        text_rpart(fit)

    node, var, dev = extract_frame_arrays(fit)
    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    r_msg = r_text_rpart_error(x_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only genuine fit")


# ---------------------------------------------------------------------------
# 9. A root-only tree built directly as a minimal synthetic frame (rather
#    than forcing a genuine rpart() fit not to split) -- the same
#    `nrow(x$frame) <= 1L`/`len(x['frame']) <= 1` boundary, isolated from
#    any particular fitting control knob. Uses a dict that also satisfies
#    the *first* guard (`_rpart_class` = "rpart") so this test exercises
#    only the second check.
# ---------------------------------------------------------------------------

def test_text_rpart_root_only_synthetic_frame_raises_value_error():
    frame = pd.DataFrame({"var": ["<leaf>"], "dev": [8.0]}, index=[1])
    fit = {"_rpart_class": "rpart", "frame": frame}

    with pytest.raises(ValueError) as exc_info:
        text_rpart(fit)

    x_expr = r_rpart_like_expr_for_plot(np.array([1.0]), np.array(["<leaf>"]), np.array([8.0]))
    r_msg = r_text_rpart_error(x_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only synthetic frame")


# ---------------------------------------------------------------------------
# 10. Calling text_rpart() with no `x` argument at all raises a python
#    TypeError (missing required positional argument), distinct in wording
#    from R's own "argument \"x\" is missing, with no default" -- both
#    raise, so this passes (with an expected wording-mismatch warning via
#    assert_python_and_r_errors_agree).
# ---------------------------------------------------------------------------

def test_text_rpart_missing_x_argument_raises_on_both_sides():
    with pytest.raises(TypeError) as exc_info:
        text_rpart()

    # r_text_rpart_error() always inserts x_expr as the first positional
    # arg; build the "no x at all" call directly instead.
    from _r_rpart_helpers import r_error_message, run_r
    r_msg = r_error_message(lambda: run_r("rpart:::text.rpart()"))
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x omitted entirely")


# ---------------------------------------------------------------------------
# 11. Calling text_rpart(fit) *without* a prior plot(fit)/plot_rpart(fit)
#    call in the same "device" -- rpartco()'s own `rpart_env` lookup fails
#    with an error message that is a *verbatim*, character-for-character
#    match on both sides (not just a substring-contained match): "no
#    information available on parameters from previous call to plot()".
#    Confirms the `_clean_rpart_env` fixture actually isolates this state
#    between tests (the positive-test suite always calls plot_rpart()
#    first).
# ---------------------------------------------------------------------------

def test_text_rpart_without_prior_plot_call_raises_matching_message():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    assert "device1" not in rpart_env

    with pytest.raises(RuntimeError) as exc_info:
        text_rpart(fit)

    from _r_rpart_helpers import r_dataframe_assign, r_fit_rpart, r_error_message, run_r
    r_dataframe_assign("df_no_plot_tmp", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", data_name="df_no_plot_tmp", method='"class"')
    import rpy2.robjects as ro
    ro.globalenv["no_plot_fit_tmp"] = r_fit
    # R's own rpart_env (rpart:::rpart_env) is a *package-namespace-level*
    # environment, not per-test-session state -- unlike python's
    # `rpart_env` dict (cleaned by the `_clean_rpart_env` fixture above), a
    # stale `deviceN` entry from an *earlier* test's genuine `plot()` call
    # can otherwise leak into this test if R happens to recycle the same
    # `dev.cur()` slot for a fresh `pdf(NULL)` device (which it does,
    # deterministically, once every previously opened null device has been
    # `dev.off()`'d) -- so it must be cleared explicitly here too, for the
    # same reason the python-side fixture exists.
    run_r("rm(list = ls(envir = rpart:::rpart_env), envir = rpart:::rpart_env)")
    run_r("grDevices::pdf(NULL)")
    try:
        r_msg = r_error_message(lambda: run_r("text(no_plot_fit_tmp)"))
    finally:
        run_r("grDevices::dev.off()")

    py_msg = str(exc_info.value).strip()
    assert r_msg is not None
    assert py_msg in r_msg, f"python={py_msg!r} not found in R message {r_msg!r}"


# ---------------------------------------------------------------------------
# 12. Passing the deprecated `label=` argument raises a UserWarning on the
#    python side and an R `warning()` with the identical (single-quoted)
#    text on the R side: "argument 'label' is no longer used" -- unlike the
#    error-message comparisons above, this checks the *warning* text
#    matches essentially verbatim (both sides quote 'label' the same way),
#    rather than merely both-sides-raise-something.
# ---------------------------------------------------------------------------

def test_text_rpart_label_argument_warns_matching_message_both_sides():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    try:
        plot_rpart(fit, ax=ax)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            text_rpart(fit, ax=ax, label="oldstyle")
        py_messages = [str(w.message) for w in caught]
    finally:
        plt.close(fig)

    assert any("label" in m and "no longer used" in m for m in py_messages)

    from _r_rpart_helpers import r_dataframe_assign, r_fit_rpart, run_r
    r_dataframe_assign("df_label_warn_tmp", df)
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", data_name="df_label_warn_tmp", method='"class"'
    )
    import rpy2.robjects as ro
    ro.globalenv["label_warn_fit_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r("plot(label_warn_fit_tmp)")
        _, r_warning = r_eval_capturing_warning('text(label_warn_fit_tmp, label = "oldstyle")')
    finally:
        run_r("grDevices::dev.off()")

    assert r_warning is not None
    assert r_warning == "argument 'label' is no longer used"
    py_msg = next(m for m in py_messages if "no longer used" in m)
    assert py_msg == r_warning


# ---------------------------------------------------------------------------
# 13. `x` is a dict that satisfies neither the "rpart"-class-marker key nor
#    is even a mapping type text_rpart.py's `.get(...)` could call (a bare
#    numpy array) -- `isinstance(x, dict)` is False so the first guard's
#    `not isinstance(x, dict)` short-circuits before ever touching
#    `.get(...)`, raising the same "Not a legitimate" error as the other
#    non-dict cases above (distinct from a hypothetical AttributeError if
#    the short-circuit were absent).
# ---------------------------------------------------------------------------

def test_text_rpart_numpy_array_input_raises_not_attribute_error():
    arr = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError) as exc_info:
        text_rpart(arr)
    assert str(exc_info.value) == 'Not a legitimate "rpart" object'
    r_msg = r_text_rpart_error("c(1, 2, 3)")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=numpy array")

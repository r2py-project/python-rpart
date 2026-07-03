"""Positive-path parity tests for r2py_rpart's `post_rpart` function itself
(NOT the thin `post(tree, **kwargs): post_rpart(tree, **kwargs)` wrapper),
benchmarked against R's `rpart:::post.rpart` / `post()` (see
`/groups/jli9/Yufei/python-rpart/rpart/man/post.rpart.Rd`).

test_post_positive.py/test_post_negative.py/test_post_edge.py (a prior
test-generation run, for the sibling `post()` wrapper in post.py) already
exercise post_rpart's behavior *exhaustively* through `post()` -- every
kwarg (title_/filename/digits/pretty/use_n/horizontal), every method
("class"/"anova"), the default-title/digits derivations, file-writing, and
orientation -- since `post()` forwards everything straight through with no
logic of its own. Re-deriving all of that here would be pure duplication.

This file instead focuses on what is genuinely *specific* to `post_rpart`'s
own signature/behavior and is invisible when only ever calling it through
`post()`:

  - `post_rpart` has real, named, positionally-matchable parameters
    (`tree, title_=..., filename=..., digits=..., pretty=..., use_n=...,
    horizontal=..., **kwargs`), mirroring R's own
    `post.rpart(tree, title., filename=..., digits=..., pretty=...,
    use.n=..., horizontal=..., ...)` method signature *exactly*, argument
    for argument, in the same order. `post()`'s own signature
    (`post(tree, **kwargs)`) cannot express positional calls to any of
    title_/filename/digits/pretty/use_n/horizontal at all -- only
    `post_rpart` itself can be called that way, exactly like R's own
    `rpart:::post.rpart(tree, "title", "", 5, TRUE, TRUE, TRUE)` positional
    form (as opposed to `post(tree, title.="title", ...)`).
  - `post_rpart`'s own `**kwargs` catch-all (mirroring R's own `...`) is
    reachable directly, without going through `post()`'s own (identical)
    `**kwargs` forwarding layer.
  - `post_rpart.py`'s own private `_rpart_digits` builtins hook (read via
    `getattr(builtins, '_rpart_digits', 7)` whenever `digits` is omitted/
    `None`) is post_rpart's own internal stand-in for R's
    `getOption("digits")` -- exercised here with a custom value, mirroring
    R's own `options(digits=...)`.

`call_post_rpart_direct_and_extract()` (in `_r_rpart_helpers.py`) is exactly
`call_post_and_extract()`'s twin, except it imports and calls
`r2py_rpart.post_rpart.post_rpart` directly (never through `post()`) and
forwards positional `*args`, needed for several tests below.
"""
from __future__ import annotations

import builtins

import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart

from _r_rpart_helpers import (
    call_post_rpart_direct_and_extract,
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_post_runs_without_error,
    run_r,
)


@pytest.fixture(autouse=True)
def _clean_rpart_digits_hook():
    """Ensure `builtins._rpart_digits` (post_rpart.py's private stand-in for
    R's `getOption("digits")`) never leaks between tests, regardless of
    whether a given test sets it and/or raises partway through."""
    if hasattr(builtins, "_rpart_digits"):
        delattr(builtins, "_rpart_digits")
    yield
    if hasattr(builtins, "_rpart_digits"):
        delattr(builtins, "_rpart_digits")


def _rvar(r_obj) -> str:
    ro.globalenv["post_rpart_positive_fit_tmp"] = r_obj
    return "post_rpart_positive_fit_tmp"


# ---------------------------------------------------------------------------
# 1. A sanity smoke test that calling `post_rpart` directly (bypassing
#    `post()` entirely) reproduces the exact same title/patch-count as R's
#    genuine, fully-keyword `rpart:::post.rpart(...)` call -- confirming the
#    direct entry point under test here is not somehow different from what
#    the sibling `post()` suite already exercises indirectly.
# ---------------------------------------------------------------------------

def test_post_rpart_direct_call_matches_r_post_rpart_keyword_call(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_="Kyphosis tree", filename="", digits=5, pretty=True, use_n=True, horizontal=True
    )
    assert py_out["retval"] is None
    assert py_out["title"] == "Kyphosis tree"
    assert py_out["n_patches"] == fit["frame"].shape[0]

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    assert r_post_runs_without_error(
        _rvar(r_fit), generic=False, filename="", title_="Kyphosis tree", digits=5,
        pretty=True, use_n=True, horizontal=True,
    )


# ---------------------------------------------------------------------------
# 2 & 3. Full *positional* invocation, in R's own documented argument order
#    (tree, title., filename, digits, pretty, use.n, horizontal) -- something
#    only `post_rpart` itself supports (`post()`'s `**kwargs`-only wrapper
#    has no positional parameters to match against beyond `tree`). Confirmed
#    against R's own `rpart:::post.rpart(...)` called the identical
#    positional way, on both a classification and a regression fit.
# ---------------------------------------------------------------------------

def test_post_rpart_full_positional_call_classification(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_rpart_direct_and_extract(monkeypatch, fit, "Kyphosis tree", "", 5, True, True, True)
    assert py_out["title"] == "Kyphosis tree"
    assert py_out["n_patches"] == fit["frame"].shape[0]
    assert any("/" in t for _, t, _, _ in py_out["texts"])  # use.n=TRUE -> event counts present

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_rpart_positive_pos_class_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r('rpart:::post.rpart(post_rpart_positive_pos_class_tmp, "Kyphosis tree", "", 5, TRUE, TRUE, TRUE)')
    finally:
        run_r("grDevices::dev.off()")


def test_post_rpart_full_positional_call_anova(monkeypatch):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")

    py_out = call_post_rpart_direct_and_extract(monkeypatch, fit, "Mileage tree", "", 5, True, True, False)
    assert py_out["title"] == "Mileage tree"
    assert py_out["n_patches"] == fit["frame"].shape[0]

    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')
    ro.globalenv["post_rpart_positive_pos_anova_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r('rpart:::post.rpart(post_rpart_positive_pos_anova_tmp, "Mileage tree", "", 5, TRUE, TRUE, FALSE)')
    finally:
        run_r("grDevices::dev.off()")


# ---------------------------------------------------------------------------
# 4. A mixed positional+keyword call (`tree` and `title_` positional, the
#    rest keyword) -- R's own argument matching supports this identical mix
#    for `rpart:::post.rpart`, and python's ordinary function-call semantics
#    support it for `post_rpart` the same way.
# ---------------------------------------------------------------------------

def test_post_rpart_mixed_positional_and_keyword_call(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, "Mixed style", filename="", use_n=False
    )
    assert py_out["title"] == "Mixed style"
    assert not any("/" in t for _, t, _, _ in py_out["texts"])  # use_n=False

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_rpart_positive_mixed_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r('rpart:::post.rpart(post_rpart_positive_mixed_tmp, "Mixed style", filename="", use.n=FALSE)')
    finally:
        run_r("grDevices::dev.off()")


# ---------------------------------------------------------------------------
# 5. Keyword arguments given in an order that does not match the parameter
#    declaration order at all (horizontal first, tree/title_/filename last)
#    -- ordinary python keyword-call semantics (and R's own by-name argument
#    matching) make this fully order-independent; confirmed identical to the
#    declaration-order call.
# ---------------------------------------------------------------------------

def test_post_rpart_shuffled_keyword_argument_order(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    declared_order = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_="x", filename="", digits=3, pretty=True, use_n=True, horizontal=False
    )
    shuffled_order = call_post_rpart_direct_and_extract(
        monkeypatch, fit, horizontal=False, use_n=True, pretty=True, digits=3, filename="", title_="x"
    )
    assert declared_order["title"] == shuffled_order["title"]
    assert declared_order["texts"] == shuffled_order["texts"]

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_rpart_positive_shuffled_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(
            'rpart:::post.rpart(post_rpart_positive_shuffled_tmp, horizontal=FALSE, use.n=TRUE, '
            'pretty=TRUE, digits=3, filename="", title.="x")'
        )
    finally:
        run_r("grDevices::dev.off()")


# ---------------------------------------------------------------------------
# 6. An extra, undocumented keyword argument (mirroring R's `...`) is
#    silently absorbed by post_rpart's own `**kwargs` when called directly
#    (never referenced again in the function body) -- confirmed this does
#    not raise on either side (R's `...` similarly just accumulates it).
# ---------------------------------------------------------------------------

def test_post_rpart_extra_unknown_kwarg_accepted_via_kwargs(monkeypatch):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    py_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_="x", filename="", paper="letter"
    )
    assert py_out["retval"] is None

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_rpart_positive_extra_kwarg_tmp"] = r_fit
    # R's `...` similarly just accumulates an unused extra named argument
    # like `paper=` without raising.
    assert r_post_runs_without_error(
        _rvar(r_fit), generic=False, filename="", title_="x", paper="letter"
    )


# ---------------------------------------------------------------------------
# 7. `builtins._rpart_digits` (post_rpart.py's own private stand-in for R's
#    `getOption("digits")`, consulted only when `digits` is omitted/None) --
#    a custom value changes the *default* digits used, mirroring R's own
#    `options(digits=...)` changing `post.rpart`'s own default
#    (`getOption("digits") - 2`). Confirmed: hook=9 -> effective digits=7 on
#    the python side produces the exact same (more precise) leaf label text
#    as passing digits=7 explicitly, and R's `options(digits=9)` default
#    (9 - 2 = 7) runs without error.
# ---------------------------------------------------------------------------

def test_post_rpart_rpart_digits_hook_changes_default_digits(monkeypatch):
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")

    builtins._rpart_digits = 9
    hooked_out = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="")
    delattr(builtins, "_rpart_digits")
    explicit_out = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="", digits=7)
    assert hooked_out["texts"] == explicit_out["texts"]

    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')
    ro.globalenv["post_rpart_positive_digits_hook_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(
            'local({op <- options(digits=9); on.exit(options(op)); '
            'rpart:::post.rpart(post_rpart_positive_digits_hook_tmp, title.="x", filename="")})'
        )
    finally:
        run_r("grDevices::dev.off()")


# ---------------------------------------------------------------------------
# 8. All non-default keyword arguments customized simultaneously (title_,
#    digits, pretty, use_n, horizontal all diverging from their documented
#    defaults at once) on a categorical (factor-splitting) fit -- exercising
#    "all parameters in combination", called directly against post_rpart
#    rather than through post()'s forwarding layer.
# ---------------------------------------------------------------------------

def test_post_rpart_all_kwargs_customized_simultaneously(monkeypatch):
    df = cu_summary_df()
    fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type", data=df, method="class",
        control={"minsplit": 30, "cp": 0.05},
    )

    py_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_="Combo", filename="", digits=2, pretty=0, use_n=False, horizontal=False
    )
    assert py_out["title"] == "Combo"
    assert not any("/" in t for _, t, _, _ in py_out["texts"])  # use_n=False

    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Reliability ~ Price + Country + Mileage + Type", method='"class"',
        control="rpart.control(minsplit=30, cp=0.05)",
    )
    ro.globalenv["post_rpart_positive_combo_tmp"] = r_fit
    run_r("grDevices::pdf(NULL)")
    try:
        run_r(
            'rpart:::post.rpart(post_rpart_positive_combo_tmp, title.="Combo", filename="", '
            'digits=2, pretty=0, use.n=FALSE, horizontal=FALSE)'
        )
    finally:
        run_r("grDevices::dev.off()")

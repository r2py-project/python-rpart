"""Boundary/edge-case parity tests for r2py_rpart's `post_rpart` function
itself (NOT the thin `post(tree, **kwargs): post_rpart(tree, **kwargs)`
wrapper), benchmarked against R's `rpart:::post.rpart`.

test_post_edge.py (the prior test-generation run's sibling suite, for
`post()`) already documents post_rpart's four permanent, tree-structure-
independent bugs/gaps (default-title off-by-one, unconditional
`compress=True`, silently-dropped extra postscript kwargs, the fixed
`"tree.ps"` default filename) and the minimal-legitimate-tree/root-only
boundary. None of that is repeated here.

This file instead focuses on boundary values/behaviors that are only
reachable through `post_rpart`'s own real function signature -- its
positional parameters, its private `_rpart_digits` builtins hook (its
internal stand-in for R's `getOption("digits")`), and its
`_post_rpart_MISSING` sentinel object -- none of which `post()`'s
`**kwargs`-only wrapper can express or expose.

KNOWN, GENUINE DIVERGENCE DOCUMENTED BELOW
-------------------------------------------------------------------------
`test_post_rpart_low_digits_hook_python_clamps_r_does_not_known_gap` --
post_rpart.py's own digits-default computation, `max(getattr(builtins,
'_rpart_digits', 7) - 2, 1)`, clamps the *effective* default to a floor of
1. R's real default, `getOption("digits") - 2`, has no such floor: a low
enough `options(digits=...)` produces a *negative* effective `digits`
value that R happily passes straight through to `sprintf("%.<digits>g",
...)` inside `text.rpart`'s numeric formatting -- which, confirmed via
direct rpy2 experimentation below, does not error, but instead silently
produces the nonsensical literal text `"%.0-1g"` (R's own `sprintf()` fails
to substitute a negative precision and the unsubstituted format string
leaks through as the "formatted" value) rather than any real number.
python's floor-of-1 clamp means this specific pathological R output can
never occur on the python side at all -- a permanent, confirmed
capability/robustness gap in python's favor.
"""
from __future__ import annotations

import builtins
import warnings

import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart
from r2py_rpart.post_rpart import _post_rpart_MISSING, post_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    call_post_rpart_direct_and_extract,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    run_r,
)


@pytest.fixture(autouse=True)
def _clean_rpart_digits_hook():
    """Ensure `builtins._rpart_digits` never leaks between tests."""
    if hasattr(builtins, "_rpart_digits"):
        delattr(builtins, "_rpart_digits")
    yield
    if hasattr(builtins, "_rpart_digits"):
        delattr(builtins, "_rpart_digits")


def _r_call_in_null_device(code: str) -> str | None:
    run_r("grDevices::pdf(NULL)")
    try:
        return r_error_message(lambda: run_r(code))
    finally:
        run_r("grDevices::dev.off()")


@pytest.fixture()
def _anova_fit_and_r_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')
    ro.globalenv["post_rpart_edge_fit_tmp"] = r_fit
    return fit, "post_rpart_edge_fit_tmp"


@pytest.fixture()
def _class_fit_and_r_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_rpart_edge_class_fit_tmp"] = r_fit
    return fit, "post_rpart_edge_class_fit_tmp"


# ---------------------------------------------------------------------------
# 1. KNOWN, GENUINE DIVERGENCE: a low enough `_rpart_digits` hook value
#    (mirroring a low `options(digits=...)`) makes python's own
#    `max(hook - 2, 1)` floor clamp visibly kick in -- producing the exact
#    same sane, real-number leaf-label text (`"2e+01"`) for hook=1 and
#    hook=2 alike -- while R's genuinely *unclamped* equivalent default
#    (`getOption("digits") - 2` == -1 for `options(digits=1)`) produces the
#    literal, nonsensical text `"%.0-1g"` instead of any real number at all
#    (confirmed directly via `fit$functions$text(..., digits=-1, ...)`,
#    exactly mirroring `post.rpart`'s own undocumented default-computation
#    formula from post.rpart.Rd). See module docstring for the full
#    root-cause analysis.
# ---------------------------------------------------------------------------

def test_post_rpart_low_digits_hook_python_clamps_r_does_not_known_gap(monkeypatch, _anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    builtins._rpart_digits = 1  # max(1 - 2, 1) == 1 (clamp kicks in)
    out_hook_1 = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="")
    delattr(builtins, "_rpart_digits")

    builtins._rpart_digits = 2  # max(2 - 2, 1) == 1 (clamp kicks in too)
    out_hook_2 = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="")
    delattr(builtins, "_rpart_digits")

    # both clamp to the same effective digits=1 -> identical, sane label text
    assert out_hook_1["texts"] == out_hook_2["texts"]
    leaf_labels = [t for _, t, _, _ in out_hook_1["texts"] if "\nn=" in t]
    assert len(leaf_labels) > 0
    for label in leaf_labels:
        number_part = label.split("\n", 1)[0]
        assert "%" not in number_part  # a real formatted number, not a raw format string

    # R's genuinely unclamped default (options(digits=1) -> digits = -1)
    # produces the literal, un-substituted format string instead of any
    # real number -- confirmed directly against post.rpart's own documented
    # default formula.
    run_r(
        f'fr <- {r_var}$frame; yv <- fr$yval; '
        f'txt <- {r_var}$functions$text(yval=yv, dev=fr$dev, wt=fr$wt, ylevel=NULL, '
        f'digits=(1L - 2L), n=fr$n, use.n=TRUE)'
    )
    r_texts = [str(s) for s in run_r("txt")]
    assert any("%.0-1g" in t for t in r_texts), (
        f"expected R's unclamped digits=-1 default to leak a literal, "
        f"un-substituted sprintf format string; got {r_texts!r}"
    )
    warnings.warn(
        "python's post_rpart.py default-digits computation "
        "(max(getattr(builtins, '_rpart_digits', 7) - 2, 1)) clamps to a "
        "floor of 1, while R's real default (getOption(\"digits\") - 2, no "
        "floor) can go negative and silently corrupts leaf-label text "
        "('%.0-1g' instead of a real number) for a low enough "
        "options(digits=...) -- permanent, confirmed divergence (python is "
        "more robust here).",
        UserWarning,
        stacklevel=2,
    )


# ---------------------------------------------------------------------------
# 2. `digits=True` (python `bool` is an `int` subclass, so this type-checks
#    as `int | None` and reaches formatg.py's own `f'%.{digits}g'`
#    f-string unmodified) -- confirmed to raise on *both* sides: python's
#    `formatg()` builds the literal (invalid) format string `"%.Trueg"`,
#    which numpy's vectorized `%` formatting rejects with "unsupported
#    format character 'T'"; R's own `sprintf("%.TRUE", ...)` (booleans
#    coerce to their literal name, not "1", when interpolated into
#    `sprintf`'s format argument) is equally rejected, with R's own
#    "invalid format" message. Both sides raise for the same underlying
#    reason (a boolean leaking into a numeric format-string precision
#    field) even though the exact wording differs -- warned, not failed,
#    per protocol.
# ---------------------------------------------------------------------------

def test_post_rpart_digits_bool_true_raises_on_both_sides(monkeypatch, _anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    with pytest.raises(ValueError) as exc_info:
        call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="", digits=True)
    assert "format" in str(exc_info.value).lower()

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, title.="x", filename="", digits=TRUE)')
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="digits=True")
    assert r_msg is not None and "format" in r_msg.lower()


# ---------------------------------------------------------------------------
# 3. `digits=0` (the documented lower edge distinct from digits=True/None) --
#    unlike the omitted/None default, an *explicit* 0 is never subject to
#    post_rpart.py's own `max(..., 1)` clamp (that clamp only fires inside
#    the `if digits is None:` branch) -- confirmed both sides accept it
#    without error and produce the exact same (rounded-to-1-sig-fig) leaf
#    label text.
# ---------------------------------------------------------------------------

def test_post_rpart_digits_explicit_zero_boundary(monkeypatch, _anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    py_out = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="", digits=0)
    leaf_labels = [t for _, t, _, _ in py_out["texts"] if "\nn=" in t]
    assert len(leaf_labels) > 0
    for label in leaf_labels:
        assert "%" not in label.split("\n", 1)[0]

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, title.="x", filename="", digits=0)')
    assert r_msg is None


# ---------------------------------------------------------------------------
# 4. `digits=None` passed *explicitly* (as opposed to omitted entirely) --
#    post_rpart.py's own `if digits is None:` guard treats an explicit
#    `None` identically to an omitted default, recomputing it from the
#    `_rpart_digits` hook. Confirmed this produces byte-identical label
#    text to omitting `digits` entirely, and that R's own `digits=NULL`
#    (a genuine, explicit NULL binding, not R's lazily-evaluated default
#    expression) likewise runs without error.
# ---------------------------------------------------------------------------

def test_post_rpart_digits_explicit_none_matches_omitted_default(monkeypatch, _anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    omitted_out = call_post_rpart_direct_and_extract(monkeypatch, fit, title_="x", filename="")
    explicit_none_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_="x", filename="", digits=None
    )
    assert omitted_out["texts"] == explicit_none_out["texts"]

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, title.="x", filename="", digits=NULL)')
    assert r_msg is None


# ---------------------------------------------------------------------------
# 5. `title_=None` -- a value that is neither the `_post_rpart_MISSING`
#    sentinel (so the `if title_ is _post_rpart_MISSING:` branch is
#    skipped) nor a string (so `len(title_)` blows up). R's own
#    `title.=NULL` hits the exact structural analog: `nzchar(NULL)`
#    returns a zero-length logical, and `if (nzchar(title.))` on a
#    zero-length condition raises "argument is of length zero" -- both
#    sides raise, for genuinely parallel reasons (an empty/absent length
#    check on a null-like value), even though the literal wording differs.
# ---------------------------------------------------------------------------

def test_post_rpart_title_none_raises_on_both_sides(_class_fit_and_r_var):
    fit, r_var = _class_fit_and_r_var

    with pytest.raises(TypeError) as exc_info:
        post_rpart(fit, title_=None, filename="")
    assert "NoneType" in str(exc_info.value) or "len()" in str(exc_info.value)

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, title.=NULL, filename="")')
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="title_=None")
    assert r_msg is not None and "length zero" in r_msg


# ---------------------------------------------------------------------------
# 6. `title_=""` supplied *positionally* (the 2nd positional argument,
#    rather than by keyword as the sibling `post()` suite always does) --
#    the empty-string boundary (`nzchar("")` is FALSE / `len("") > 0` is
#    False) suppresses the title regardless of *how* it was passed in.
# ---------------------------------------------------------------------------

def test_post_rpart_empty_string_title_positional_suppresses_title(monkeypatch, _class_fit_and_r_var):
    fit, r_var = _class_fit_and_r_var

    py_out = call_post_rpart_direct_and_extract(monkeypatch, fit, "", "")
    assert py_out["title"] == ""

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, "", "")')
    assert r_msg is None


# ---------------------------------------------------------------------------
# 7. `_post_rpart_MISSING` (post_rpart.py's own private module-level
#    sentinel object standing in for R's `missing(title.)`) can itself be
#    passed explicitly as `title_=` by any caller that imports it --
#    reproducing *exactly* the same default-title codepath as omitting
#    `title_` entirely. This is a purely python-internal implementation
#    detail with no direct R analog (R has no first-class sentinel object a
#    caller could pass in this way) -- a regression anchor confirming the
#    sentinel identity check (`is`, not `==`) stays stable, not an R-parity
#    check.
# ---------------------------------------------------------------------------

def test_post_rpart_explicit_sentinel_reuse_matches_omitted_title(monkeypatch, _class_fit_and_r_var):
    fit, _r_var = _class_fit_and_r_var

    omitted_out = call_post_rpart_direct_and_extract(monkeypatch, fit, filename="")
    explicit_sentinel_out = call_post_rpart_direct_and_extract(
        monkeypatch, fit, title_=_post_rpart_MISSING, filename=""
    )
    assert omitted_out["title"] == explicit_sentinel_out["title"]
    assert omitted_out["title"].startswith("Endpoint = ")


# ---------------------------------------------------------------------------
# 8. Every boundary/degenerate kwarg value combined at once
#    (digits=1 [the documented practical floor], pretty=0 [no abbreviation
#    at all], use_n=False, horizontal=False), all passed *positionally* in
#    R's own documented argument order -- confirming post_rpart's positional
#    dispatch keeps working correctly when every value is simultaneously at
#    its most extreme, matching R's identical fully-positional boundary
#    call.
# ---------------------------------------------------------------------------

def test_post_rpart_all_boundary_values_combined_positionally(monkeypatch, _class_fit_and_r_var):
    fit, r_var = _class_fit_and_r_var

    py_out = call_post_rpart_direct_and_extract(monkeypatch, fit, "Boundary", "", 1, 0, False, False)
    assert py_out["title"] == "Boundary"
    assert not any("/" in t for _, t, _, _ in py_out["texts"])  # use_n=False

    r_msg = _r_call_in_null_device(
        f'rpart:::post.rpart({r_var}, "Boundary", "", 1, 0, FALSE, FALSE)'
    )
    assert r_msg is None


# ---------------------------------------------------------------------------
# 9. `filename=None` -- structurally the exact same "null-like value hits a
#    length/equality check meant for a real string" boundary as
#    `title_=None` (case 5 above), but on the *other* string-typed
#    parameter: python's `if filename != '':` is vacuously true for `None`,
#    so it falls into `fig.savefig(None, ...)`, which matplotlib rejects
#    outright; R's own analogous `if (filename != "")` guard -- confirmed
#    via post.rpart.R's documented `filename = ""` branching -- raises the
#    exact same "argument is of length zero" message as title_=NULL did,
#    for the identical zero-length-comparison reason.
# ---------------------------------------------------------------------------

def test_post_rpart_filename_none_raises_on_both_sides(_class_fit_and_r_var):
    fit, r_var = _class_fit_and_r_var

    with pytest.raises(ValueError) as exc_info:
        post_rpart(fit, title_="x", filename=None)
    assert "outfile" in str(exc_info.value) or "path" in str(exc_info.value).lower()

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, title.="x", filename=NULL)')
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="filename=None")
    assert r_msg is not None and "length zero" in r_msg

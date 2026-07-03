"""Negative-path parity tests for r2py_rpart's `post_rpart` function itself
(NOT the thin `post(tree, **kwargs): post_rpart(tree, **kwargs)` wrapper),
benchmarked against R's `rpart:::post.rpart`.

test_post_negative.py (the prior test-generation run's sibling suite, for
`post()`) already exhaustively covers post_rpart's *internal* legitimacy
checks (`Not a legitimate "rpart" object` / `fit is not a tree, just a
root`, inherited from `plot_rpart()`/`text_rpart()`) and various malformed
`tree=`/`filename=` inputs. None of that is repeated here.

This file instead covers failure modes that can *only* arise from
`post_rpart`'s own real (non-generic) python function signature --
`post_rpart(tree, title_=..., filename=..., digits=..., pretty=...,
use_n=..., horizontal=..., **kwargs)` -- which `post()`'s `**kwargs`-only
wrapper cannot even reach (calling `post(tree, "some title")` fails at
`post()`'s own boundary with a *different* "too many positional arguments"
TypeError, never reaching `post_rpart` at all):

  1. Calling `post_rpart()` with the required `tree` argument omitted
     entirely.
  2/3. A python keyword argument colliding with an already-filled
     positional slot (`post_rpart(tree, "positional title",
     title_="other")` / `..., "a.ps", filename="b.ps")`) -- python's
     ordinary call-binding machinery raises `TypeError: ... got multiple
     values for argument ...` for *both* unconditionally. R's own argument
     matching is far more permissive here: an explicit `name=value` match
     is removed from the pool *before* positional matching runs, so the
     "conflicting" positional value silently slides down to bind the next
     *unfilled* formal parameter instead (`digits` in both cases here) --
     sometimes causing a real (but unrelated-looking) downstream error
     (case 2, confirmed via direct rpy2 experimentation: the string ends up
     interpolated into a `sprintf()` format string), sometimes causing no
     error at all (case 3, confirmed: `filename`'s "conflicting" positional
     value quietly becomes a no-op `digits` value instead, and the call
     completes and even writes the *named* filename with no complaint).
  4. Passing one more positional argument than `post_rpart`'s fixed 7 named
     parameters -- python's `**kwargs` (unlike R's `...`) only ever
     captures *keyword* arguments, never excess *positional* ones, so this
     raises `TypeError: ... takes from 1 to 7 positional arguments but 8
     were given`. R's own `...` absorbs an excess positional argument the
     exact same way it absorbs an excess *named* one (confirmed via direct
     rpy2 experimentation: the call completes with no error at all).

Per this test-generation task's protocol: both sides must raise for a
negative test to "pass" outright; if only one side raises, that is a
genuine, confirmed capability gap and is asserted/documented explicitly
instead (mirroring test_post_negative.py's own established convention for
its `filename=123`/directory-not-found cases).
"""
from __future__ import annotations

import os
import warnings

import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart
from r2py_rpart.post_rpart import post_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    run_r,
)


def _r_call_in_null_device(code: str) -> str | None:
    """Run `code` (an R `rpart:::post.rpart(...)` call) inside a no-op
    `pdf(NULL)` device so a `filename=""` call never tries to open a real
    display, returning the R error message string if it raises, else
    None."""
    run_r("grDevices::pdf(NULL)")
    try:
        return r_error_message(lambda: run_r(code))
    finally:
        run_r("grDevices::dev.off()")


@pytest.fixture()
def _anova_fit_and_r_var(tmp_path, monkeypatch):
    """A genuine 'anova' fit, assigned into R's globalenv under a fixed name
    -- shared setup for every test below (each needs a real, fully-fitted
    object so `text.rpart`'s internal `$functions$text`/`$yval` calls have
    something real to operate on, and a throwaway cwd so any accidentally
    written `.ps` file lands somewhere auto-cleaned-up rather than the repo
    root)."""
    monkeypatch.chdir(tmp_path)
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    fit = rpart("Mileage ~ Weight", data=df, method="anova")
    r_dataframe_assign("car_df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="car_df", method='"anova"')
    ro.globalenv["post_rpart_negative_fit_tmp"] = r_fit
    return fit, "post_rpart_negative_fit_tmp"


# ---------------------------------------------------------------------------
# 1. `tree` is a required positional parameter with no default at all --
#    omitting it entirely must fail immediately, on both sides, before any
#    of post_rpart's own internal logic ever runs.
#
#    NOTE: R's own `filename=` default expression,
#    `paste(deparse(substitute(tree)), ".ps", sep = "")`, is evaluated
#    *lazily* -- and `deparse(substitute(<missing arg>))` yields `""`, so
#    R's real default filename becomes the literal `".ps"`, and R actually
#    opens a genuine `postscript(file=".ps", ...)` device (writing a real,
#    if degenerate, file) *before* it ever forces the truly-missing `tree`
#    promise and raises. `monkeypatch.chdir(tmp_path)` keeps that
#    unavoidable stray file out of the repo working directory.
# ---------------------------------------------------------------------------

def test_post_rpart_missing_required_tree_argument_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(TypeError) as exc_info:
        post_rpart()  # type: ignore[call-arg]
    assert "missing" in str(exc_info.value)
    assert "tree" in str(exc_info.value)

    r_msg = _r_call_in_null_device("rpart:::post.rpart()")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="post_rpart() with tree omitted")
    assert r_msg is not None and "tree" in r_msg


# ---------------------------------------------------------------------------
# 2. `title_` supplied both positionally (2nd arg) and by keyword --
#    unambiguous, unconditional TypeError in python. Confirmed R does *not*
#    reject this the same way at call-matching time -- the "extra"
#    positional value instead silently binds the next unfilled formal
#    (`digits`), which downstream corrupts an `sprintf()` format string --
#    still an error, on both sides, but the wording is unrelated (warned,
#    not failed, per protocol).
# ---------------------------------------------------------------------------

def test_post_rpart_title_positional_and_keyword_collision_raises(_anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    with pytest.raises(TypeError) as exc_info:
        post_rpart(fit, "positional title", title_="other title", filename="")
    assert "multiple values" in str(exc_info.value)
    assert "title_" in str(exc_info.value)

    r_msg = _r_call_in_null_device(
        f'rpart:::post.rpart({r_var}, "positional title", title.="other title", filename="")'
    )
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="title_ positional+keyword collision")


# ---------------------------------------------------------------------------
# 3. `filename` supplied both positionally (3rd arg) and by keyword --
#    python raises the same unconditional TypeError as case 2 above. R,
#    however, genuinely completes this call with *no* error at all: the
#    "extra" positional value silently becomes a (never-validated, never
#    used for anything but formatting) `digits` value instead, and the
#    explicitly-*named* `filename=` value is the one actually honored -- a
#    real, confirmed, one-sided capability gap (python is strictly safer
#    here), not merely a wording mismatch.
# ---------------------------------------------------------------------------

def test_post_rpart_filename_positional_and_keyword_collision_raises_in_python_but_not_r(
    _anova_fit_and_r_var, tmp_path
):
    fit, r_var = _anova_fit_and_r_var

    with pytest.raises(TypeError) as exc_info:
        post_rpart(fit, "t", "a.ps", filename="b.ps")
    assert "multiple values" in str(exc_info.value)
    assert "filename" in str(exc_info.value)

    r_msg = _r_call_in_null_device(f'rpart:::post.rpart({r_var}, "t", "a.ps", filename="b.ps")')
    if r_msg is not None:
        warnings.warn(
            f"Expected R's rpart:::post.rpart(tree, 't', 'a.ps', filename='b.ps') "
            f"(a positional+named argument collision) to succeed -- R's argument "
            f"matching silently reassigns the 'extra' positional value to the "
            f"next unfilled formal (digits) rather than rejecting the call -- "
            f"but it raised: {r_msg!r}",
            UserWarning,
            stacklevel=2,
        )
    assert r_msg is None
    # R actually wrote the *named* filename ("b.ps"), confirming the named
    # value won and no legitimacy/argument error occurred.
    assert os.path.exists(tmp_path / "b.ps")


# ---------------------------------------------------------------------------
# 4. One more positional argument than post_rpart's fixed 7 named
#    parameters -- python's `**kwargs` cannot absorb excess *positional*
#    arguments (only excess keyword ones), so this is a hard TypeError.
#    R's own `...`, by contrast, absorbs excess positional arguments the
#    same way it absorbs excess named ones -- confirmed the equivalent R
#    call completes with no error whatsoever, a genuine, permanent
#    python-vs-R signature-flexibility gap.
# ---------------------------------------------------------------------------

def test_post_rpart_excess_positional_argument_raises_in_python_but_not_r(_anova_fit_and_r_var):
    fit, r_var = _anova_fit_and_r_var

    with pytest.raises(TypeError) as exc_info:
        post_rpart(fit, "t", "", 5, True, True, True, "extra")
    assert "positional argument" in str(exc_info.value)

    r_msg = _r_call_in_null_device(
        f'rpart:::post.rpart({r_var}, "t", "", 5, TRUE, TRUE, TRUE, "extra")'
    )
    if r_msg is not None:
        warnings.warn(
            f"Expected R's rpart:::post.rpart(tree, 't', '', 5, TRUE, TRUE, TRUE, "
            f"'extra') (one more positional argument than post.rpart's own 6 named "
            f"parameters beyond tree) to succeed via R's `...` absorbing the excess "
            f"positional value -- but it raised: {r_msg!r}",
            UserWarning,
            stacklevel=2,
        )
    assert r_msg is None

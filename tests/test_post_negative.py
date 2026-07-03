"""Negative-path parity tests for r2py_rpart.post vs. R's `post` (a plain S3
generic, `post <- function(tree, ...) UseMethod("post")`, dispatching to
`post.rpart`).

python's `post()` is a thin wrapper with no legitimacy checks of its own:

    def post(tree, **kwargs): post_rpart(tree, **kwargs)

so every error it can raise actually originates one level down, inside
`post_rpart()`'s own two internal calls:

    plot_rpart(tree, uniform=True, branch=0.2, compress=True, margin=0.1, ax=ax)
        -> raise TypeError('Not a legitimate "rpart" object')   if not (dict w/ 'frame')
        -> raise ValueError('fit is not a tree, just a root')   if len(frame) <= 1
    text_rpart(tree, all=True, use_n=use_n, fancy=True, digits=digits, pretty=pretty, ax=ax)
        -> raise ValueError('Not a legitimate "rpart" object')  if x.get('_rpart_class') != 'rpart'
        -> raise ValueError('fit is not a tree, just a root')   if len(frame) <= 1  (unreachable
                                                                  here: plot_rpart's identical
                                                                  guard always fires first)

This exactly mirrors post.rpart.R's own two `plot(tree, ...)`/`text(tree,
...)` calls, which -- being the *plain* S3 generics, not `plot.rpart`/
`text.rpart` called directly -- only reach plot.rpart's/text.rpart's own
`stop("Not a legitimate \"rpart\" object")`/`stop("fit is not a tree, just a
root")` guards when `tree` genuinely carries the `"rpart"` class (otherwise
`plot()`/`text()` dispatch to `plot.default`/`text.default` instead, an
entirely different and uninteresting failure mode). So, exactly like
test_plot_rpart_negative.py's own established convention, most tests below
call `rpart:::plot.rpart(x, ...)`/`rpart:::text.rpart(x, ...)` *directly*
(bypassing R's generic dispatch) to reach the specific internal check being
exercised -- except for the one test dedicated to `post()`'s own outer
generic-dispatch behavior (`post <- function(tree, ...) UseMethod("post")`),
which is unique to `post` among the functions this test-generation task has
covered so far (`plot.rpart`/`text.rpart` are never generics themselves; only
S3 *methods*).

Per this test-generation task's protocol: both sides must raise for a test to
pass; if they raise with differently-worded messages, that is flagged via
`warnings.warn` (through `assert_python_and_r_errors_agree`) rather than
failing the test outright.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest
import rpy2.robjects as ro

from r2py_rpart import rpart
from r2py_rpart.post import post

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    extract_frame_arrays,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_plot_rpart_error,
    r_post_error,
    r_rpart_like_expr_for_plot,
    r_text_rpart_error,
)


# ---------------------------------------------------------------------------
# 1. x = None -- neither a legitimate rpart object structurally (python) nor
#    `"rpart"`-classed (R). R's plain top-level generic `post(NULL)` fails
#    via `UseMethod("post")` itself ("no applicable method"), a different
#    failure stage than python's internal `plot_rpart` TypeError -- both
#    raise, so the wording mismatch is only warned about, not failed.
# ---------------------------------------------------------------------------

def test_post_none_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        post(None)
    r_msg = r_post_error("NULL", generic=True, filename="")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=None (generic post())")

    # The internal check post_rpart() actually reaches (plot_rpart's own
    # TypeError guard) is reached by R's rpart:::plot.rpart(NULL, ...) too --
    # confirming *that* is the deeper, direct analog of python's real
    # control flow (mirroring test_plot_rpart_negative.py's own convention).
    r_msg_direct = r_plot_rpart_error("NULL", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg_direct, context="x=None (direct plot.rpart)")


# ---------------------------------------------------------------------------
# 2. x = a plain empty list -- same shape of divergence as x=None above.
# ---------------------------------------------------------------------------

def test_post_empty_list_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        post([])
    r_msg = r_post_error("list()", generic=True, filename="")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=[] (generic post())")

    r_msg_direct = r_plot_rpart_error("list()", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg_direct, context="x=[] (direct plot.rpart)")


# ---------------------------------------------------------------------------
# 3. x = an empty dict `{}` -- python's `post_rpart()` reaches plot_rpart's
#    `'frame' not in x` branch and raises exactly
#    'Not a legitimate "rpart" object'. On the R side, giving the minimal
#    synthetic object the `"rpart"` class (so `plot(tree, ...)` genuinely
#    dispatches to plot.rpart, exactly like test_plot_rpart_negative.py's own
#    `test_plot_rpart_dict_without_frame_key_raises_type_error`) still raises
#    -- just from `nrow(x$frame) <= 1L` erroring on a NULL `$frame` ("argument
#    is of length zero") rather than an explicit legitimacy message, since
#    R's `inherits(x, "rpart")` check is satisfied by construction here.
# ---------------------------------------------------------------------------

def test_post_empty_dict_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        post({}, filename="")
    assert 'Not a legitimate "rpart" object' == str(exc_info.value)

    r_msg = r_post_error(
        'structure(list(not_frame = 1), class = "rpart")', generic=False, filename="", title_="x"
    )
    assert r_msg is not None
    assert "length zero" in r_msg or "argument is of length" in r_msg


# ---------------------------------------------------------------------------
# 4. x = a bare pandas.DataFrame (not wrapped in a dict at all).
# ---------------------------------------------------------------------------

def test_post_bare_dataframe_input_raises_type_error():
    df = pd.DataFrame({"var": ["<leaf>"], "dev": [0.0]})
    with pytest.raises(TypeError) as exc_info:
        post(df, filename="")
    r_msg = r_post_error('data.frame(var = "<leaf>", dev = 0)', generic=True, filename="")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=bare DataFrame (generic post())")


# ---------------------------------------------------------------------------
# 5. x = a scalar (an int) -- as far from a legitimate rpart object as
#    possible; the very first legitimacy check on both sides must reject it.
# ---------------------------------------------------------------------------

def test_post_scalar_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        post(5, filename="")
    r_msg = r_post_error("5", generic=True, filename="")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=5 (generic post())")


# ---------------------------------------------------------------------------
# 6. A root-only tree (frame has exactly 1 row) -- a genuine
#    r2py_rpart.rpart() fit forced to not split at all, hitting
#    plot_rpart's *second* guard (`len(x['frame']) <= 1`) rather than the
#    type guard -- reached before text_rpart() or the title logic ever run.
# ---------------------------------------------------------------------------

def test_post_root_only_genuine_fit_raises_value_error():
    df = kyphosis_df()
    fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class",
        control={"minsplit": 10_000},
    )
    assert fit["frame"].shape[0] == 1

    with pytest.raises(ValueError) as exc_info:
        post(fit, filename="")

    node, var, dev = extract_frame_arrays(fit)
    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    r_msg = r_post_error(x_expr, generic=False, filename="", title_="x")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only genuine fit")
    assert "fit is not a tree, just a root" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. A root-only tree built directly as a minimal synthetic frame (rather
#    than forcing a genuine rpart() fit not to split) -- the same boundary,
#    isolated from any particular fitting control knob.
# ---------------------------------------------------------------------------

def test_post_root_only_synthetic_frame_raises_value_error():
    frame = pd.DataFrame({"var": ["<leaf>"], "dev": [8.0]}, index=[1])
    fit = {"frame": frame}

    with pytest.raises(ValueError) as exc_info:
        post(fit, filename="")

    x_expr = r_rpart_like_expr_for_plot(np.array([1.0]), np.array(["<leaf>"]), np.array([8.0]))
    r_msg = r_post_error(x_expr, generic=False, filename="", title_="x")
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only synthetic frame")


# ---------------------------------------------------------------------------
# 8. A dict with a legitimate (>1 row) `frame` but *no* `_rpart_class`
#    marker at all -- python's plot_rpart() only checks structurally for a
#    `'frame'` key (so it happily proceeds), but text_rpart()'s own
#    `x.get('_rpart_class') != 'rpart'` check then fires, raising the exact
#    same 'Not a legitimate "rpart" object' message. Since this specific
#    "passes the first internal check, fails only the second" staging is a
#    python-side implementation detail (R's `inherits(x, "rpart")` is a
#    single boolean that cannot pass for `plot.rpart` while failing for
#    `text.rpart` on the very same `x`), the R-side comparison target here is
#    `rpart:::text.rpart()` called *directly* and in isolation (bypassing
#    `plot()` entirely) on the equivalent class-less R list -- confirming
#    text.rpart's own legitimacy check is, in isolation, the exact same
#    message python's text_rpart() raises.
# ---------------------------------------------------------------------------

def test_post_dict_with_frame_but_no_rpart_class_marker_raises_value_error():
    frame = pd.DataFrame(
        {"var": ["Start", "<leaf>", "<leaf>"], "dev": [8.0, 0.0, 0.0]}, index=[1, 2, 3]
    )
    fit = {"frame": frame}  # deliberately no '_rpart_class' key

    with pytest.raises(ValueError) as exc_info:
        post(fit, filename="")
    assert 'Not a legitimate "rpart" object' == str(exc_info.value)

    r_msg = r_text_rpart_error(
        'list(frame = data.frame(var = c("Start", "<leaf>", "<leaf>"), '
        'dev = c(8, 0, 0), row.names = c("1", "2", "3")))'
    )
    assert r_msg is not None
    assert 'Not a legitimate "rpart" object' in r_msg


# ---------------------------------------------------------------------------
# 9. filename= pointing at a directory that does not exist -- python's
#    `fig.savefig()` raises a plain `FileNotFoundError`; R's own
#    `postscript(file = filename, ...)` fails with "cannot open file". Both
#    sides raise (different exception types/wording entirely -- warned, not
#    failed).
# ---------------------------------------------------------------------------

def test_post_nonexistent_directory_filename_raises_on_both_sides():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    with pytest.raises(Exception) as exc_info:
        post(fit, filename="/this/directory/does/not/exist_xyz/out.ps", title_="x")

    node, var, dev = extract_frame_arrays(fit)
    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    r_msg = r_post_error(
        x_expr, generic=False, filename="/this/directory/does/not/exist_xyz/out.ps", title_="x"
    )
    assert r_msg is not None
    assert "cannot open file" in r_msg or "No such file" in r_msg


# ---------------------------------------------------------------------------
# 10. filename= given as a non-string, non-path-like type (a bare int) --
#     matplotlib's `Figure.savefig()` rejects this outright
#     ("outfile must be a path or a file-like object"). R's `postscript()`
#     is far more permissive here: `file = 123` is silently coerced to the
#     literal filename `"123"` and the plot is written successfully -- a
#     genuine, confirmed divergence (python raises, R does not), so this is
#     documented explicitly (mirroring test_plot_rpart_negative.py's own
#     `test_plot_rpart_branch_col_out_of_map_int_raises_in_python_but_not_r`
#     convention for a real capability gap) rather than silently warned
#     about via `assert_python_and_r_errors_agree`.
# ---------------------------------------------------------------------------

def test_post_non_string_filename_raises_in_python_but_not_r(monkeypatch, tmp_path):
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")

    with pytest.raises(Exception) as exc_info:
        post(fit, filename=123, title_="x")
    assert "outfile" in str(exc_info.value) or "path" in str(exc_info.value).lower()

    # A genuine, fully-fitted R object is required here (rather than the
    # minimal synthetic frame-only object `r_rpart_like_expr_for_plot()`
    # builds elsewhere in this file): post.rpart's `text(tree, ...)` call
    # needs a real `$functions$text` closure/`$yval`/`$n`/`$wt` to reach the
    # *file-writing* stage at all -- this test is purely about
    # `filename=`'s own coercion behavior, not about legitimacy-check parity,
    # so there is no need to isolate away from R's/python's rpart()
    # potentially choosing different splits (see r_post_write_file_and_get_
    # orientation()'s own docstring for the identical rationale).
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    ro.globalenv["post_negative_fit_tmp"] = r_fit
    # R's postscript(file = 123, ...) coerces 123 to the literal filename
    # "123" and writes it into R's *current working directory* -- chdir into
    # a throwaway tmp_path first so that stray file lands somewhere that
    # gets cleaned up automatically, not in the repo/test working directory.
    monkeypatch.chdir(tmp_path)
    r_msg = r_post_error("post_negative_fit_tmp", generic=True, filename=123, title_="x")
    if r_msg is not None:
        warnings.warn(
            f"Expected R's post(..., filename=123) to succeed (numeric "
            f"filenames are coerced to a literal string filename) but it "
            f"raised: {r_msg!r}",
            UserWarning,
            stacklevel=2,
        )
    assert r_msg is None

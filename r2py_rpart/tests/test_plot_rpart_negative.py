"""Negative-path parity tests for r2py_rpart.plot_rpart vs. R's
`plot.rpart`.

plot.rpart.R's body has exactly two explicit `stop()` guards, both mirrored
verbatim in plot_rpart.py:

    if (!inherits(x, "rpart")) stop("Not a legitimate \"rpart\" object")
    if (nrow(x$frame) <= 1L) stop("fit is not a tree, just a root")

    if not isinstance(x, dict) or 'frame' not in x:
        raise TypeError('Not a legitimate "rpart" object')
    if len(x['frame']) <= 1:
        raise ValueError('fit is not a tree, just a root')

Every test below exercises one of these two branches. Since `x` deliberately
lacks any "rpart" class in most of these cases, R's own generic `plot(x)`
would dispatch to `plot.default` instead of ever reaching plot.rpart's
checks -- so `rpart:::plot.rpart(x, ...)` is called directly throughout
(`generic=False`, mirroring print.rpart's own established
`rpart:::print.rpart` convention in this test suite), exactly matching how
r2py_rpart.plot_rpart() itself performs these checks unconditionally,
regardless of any class marker on its input.

Per this test-generation task's protocol: both sides must raise for a test
to pass; if they raise with differently-worded messages, that's flagged via
`warnings.warn` (through `assert_python_and_r_errors_agree`) rather than
failing the test outright.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from r2py_rpart import rpart
from r2py_rpart.plot_rpart import plot_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    extract_frame_arrays,
    kyphosis_df,
    r_plot_rpart_error,
    r_rpart_like_expr_for_plot,
)


# ---------------------------------------------------------------------------
# 1. x = None -> `!inherits(NULL, "rpart")` is TRUE in R; python's own
#    `isinstance(None, dict)` is False.
# ---------------------------------------------------------------------------

def test_plot_rpart_none_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        plot_rpart(None)
    r_msg = r_plot_rpart_error("NULL", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=None")


# ---------------------------------------------------------------------------
# 2. x = a plain list -- R's `list()` doesn't `inherits(x, "rpart")` either;
#    python's `isinstance(x, dict)` is False for a bare list.
# ---------------------------------------------------------------------------

def test_plot_rpart_empty_list_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        plot_rpart([])
    r_msg = r_plot_rpart_error("list()", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=[]")


# ---------------------------------------------------------------------------
# 3. x = a dict with no 'frame' key at all -- matches R's structure(list(),
#    class="rpart") (has the class attribute, but no $frame element, so
#    nrow(x$frame) would itself error in R before reaching the intended
#    message -- confirmed below to still raise, just from the same
#    underlying "no frame" cause as python's `'frame' not in x` check).
# ---------------------------------------------------------------------------

def test_plot_rpart_dict_without_frame_key_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        plot_rpart({"not_frame": 1})
    r_msg = r_plot_rpart_error("structure(list(not_frame = 1), class = \"rpart\")", generic=False)
    assert r_msg is not None  # nrow(NULL) -> NULL; NULL <= 1L -> logical(0); if() on that errors
    assert "Not a legitimate" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4. x = a bare pandas.DataFrame (not wrapped in a dict at all) -- python's
#    `isinstance(x, dict)` is False; R's equivalent (a bare data.frame, no
#    "rpart" class) likewise fails `inherits(x, "rpart")`.
# ---------------------------------------------------------------------------

def test_plot_rpart_bare_dataframe_input_raises_type_error():
    df = pd.DataFrame({"var": ["<leaf>"], "dev": [0.0]})
    with pytest.raises(TypeError) as exc_info:
        plot_rpart(df)
    r_msg = r_plot_rpart_error("data.frame(var = \"<leaf>\", dev = 0)", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=bare DataFrame")


# ---------------------------------------------------------------------------
# 5. x = a scalar (an int) -- as far from a legitimate rpart object as
#    possible; both sides' very first legitimacy check must reject it.
# ---------------------------------------------------------------------------

def test_plot_rpart_scalar_input_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        plot_rpart(5)
    r_msg = r_plot_rpart_error("5", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x=5")


# ---------------------------------------------------------------------------
# 6. A root-only tree (frame has exactly 1 row, no splits at all) -- a
#    genuine r2py_rpart.rpart() fit forced to not split at all via an
#    unreachable `minsplit`, hitting plot_rpart.py's *second* guard
#    (`len(x['frame']) <= 1`) rather than the type guard.
# ---------------------------------------------------------------------------

def test_plot_rpart_root_only_genuine_fit_raises_value_error():
    df = kyphosis_df()
    fit = rpart(
        "Kyphosis ~ Age + Number + Start", data=df, method="class",
        control={"minsplit": 10_000},
    )
    assert fit["frame"].shape[0] == 1

    with pytest.raises(ValueError) as exc_info:
        plot_rpart(fit)

    node, var, dev = extract_frame_arrays(fit)
    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    r_msg = r_plot_rpart_error(x_expr, generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only genuine fit")


# ---------------------------------------------------------------------------
# 7. A root-only tree built directly as a minimal synthetic frame (rather
#    than forcing a genuine rpart() fit not to split) -- the same
#    `nrow(x$frame) <= 1L`/`len(x['frame']) <= 1` boundary, isolated from any
#    particular fitting control knob.
# ---------------------------------------------------------------------------

def test_plot_rpart_root_only_synthetic_frame_raises_value_error():
    frame = pd.DataFrame({"var": ["<leaf>"], "dev": [8.0]}, index=[1])
    fit = {"frame": frame}

    with pytest.raises(ValueError) as exc_info:
        plot_rpart(fit)

    x_expr = r_rpart_like_expr_for_plot(np.array([1.0]), np.array(["<leaf>"]), np.array([8.0]))
    r_msg = r_plot_rpart_error(x_expr, generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="root-only synthetic frame")


# ---------------------------------------------------------------------------
# 8. An empty dict `{}` -- neither 'frame' key present nor any other
#    structure; the most minimal "not a legitimate rpart object" input.
# ---------------------------------------------------------------------------

def test_plot_rpart_empty_dict_raises_type_error():
    with pytest.raises(TypeError) as exc_info:
        plot_rpart({})
    r_msg = r_plot_rpart_error("list()", generic=False)
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="x={}")
    assert 'Not a legitimate "rpart" object' == str(exc_info.value)


# ---------------------------------------------------------------------------
# 9. branch_col as an out-of-range integer (5) -- KNOWN, DOCUMENTED PARITY
#    GAP (see also test_plot_rpart_edge.py's more detailed version): R's
#    default 8-color palette accepts col=5 (cyan) without error, but
#    plot_rpart.py's `col_map` only covers indices 0-4; `col_map.get(5, 5)`
#    falls back to the literal int 5, which matplotlib's `Line2D` color
#    argument rejects outright. This is the one case in this file where the
#    two sides are *expected* to diverge (python raises, R does not) --
#    documented here explicitly rather than silently warned about, since it
#    is a real, permanent capability gap (col_map not covering R's full
#    default palette), not a wording-only mismatch.
# ---------------------------------------------------------------------------

def test_plot_rpart_branch_col_out_of_map_int_raises_in_python_but_not_r():
    df = kyphosis_df()
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    node, var, dev = extract_frame_arrays(fit)

    with pytest.raises(Exception):
        plot_rpart(fit, branch_col=5)

    x_expr = r_rpart_like_expr_for_plot(node, var, dev)
    r_msg = r_plot_rpart_error(x_expr, generic=False, branch_col=5)
    if r_msg is not None:
        warnings.warn(
            "Expected R's plot.rpart(..., branch.col=5) to succeed (cyan, "
            f"palette index 5) but it raised: {r_msg!r}",
            UserWarning,
            stacklevel=2,
        )
    assert r_msg is None

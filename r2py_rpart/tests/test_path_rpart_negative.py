"""Negative-path parity tests for r2py_rpart.path_rpart vs. R's
`path.rpart`.

Unlike labels.rpart (which has no `inherits()` legitimacy check of its
own -- see test_labels_rpart_negative.py's module docstring), path.rpart
*does* check its `tree` argument explicitly: `if (!inherits(tree,
"rpart")) stop('Not a legitimate "rpart" object')`, mirrored exactly by
r2py_rpart.path_rpart()'s own `if not isinstance(tree, dict) or
tree.get('_rpart_class') != 'rpart': raise ValueError(...)`. So every
malformed-`tree` scenario in Section 1 below calls `path.rpart(...)`
directly (path.rpart is exported from rpart's NAMESPACE as a plain
function, not an S3 method -- no `rpart:::` triple-colon trick needed,
unlike labels.rpart/print.rpart/plot.rpart's own negative-test helpers).

Section 1 covers scenarios where **both** implementations demonstrably
raise, using `assert_python_and_r_errors_agree()` to *warn* (rather than
fail) on any wording mismatch, per this test-generation task's negative-
test protocol.

Section 2 documents two **permanent, confirmed** one-sided-raise gaps --
both directions represented (R raises but python doesn't, and vice versa),
each pinned by a dedicated test that records the *actual* (asymmetric)
behavior on each side, mirroring this test suite's established convention
for other functions' known, permanent parity gaps (e.g.
test_labels_rpart_negative.py's Section 2, test_text_rpart_positive.py's
`fancy=True` bug).
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.path_rpart import path_rpart

from _r_rpart_helpers import (
    _PATH_RPART_OMIT,
    assert_python_and_r_errors_agree,
    kyphosis_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_path_rpart_error,
    run_r,
)


def _kyphosis_fits():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", method='"class"')
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class")
    return fit, r_fit


# ---------------------------------------------------------------------------
# Section 1: genuine both-sides-raise parity -- malformed/illegitimate
# `tree` objects.
# ---------------------------------------------------------------------------

def test_path_rpart_tree_none_raises():
    r_msg = r_path_rpart_error("NULL", nodes=1)
    with pytest.raises(Exception) as exc_info:
        path_rpart(None, nodes=[1])
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=None")


def test_path_rpart_tree_empty_dict_raises():
    r_msg = r_path_rpart_error("list()", nodes=1)
    with pytest.raises(Exception) as exc_info:
        path_rpart({}, nodes=[1])
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree={}")


def test_path_rpart_tree_scalar_int_raises():
    r_msg = r_path_rpart_error("5", nodes=1)
    with pytest.raises(Exception) as exc_info:
        path_rpart(5, nodes=[1])
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree=5")


def test_path_rpart_tree_string_raises():
    r_msg = r_path_rpart_error('"abc"', nodes=1)
    with pytest.raises(Exception) as exc_info:
        path_rpart("abc", nodes=[1])
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context='tree="abc"')


def test_path_rpart_tree_dict_without_rpart_class_raises():
    """A plain dict that merely *looks* like a fit (has 'frame') but lacks
    R's "rpart" class attribute / python's `_rpart_class` marker -- R's
    `inherits()` check and python's `tree.get('_rpart_class') != 'rpart'`
    check both reject it before ever touching `frame`."""
    r_code = """
    unclassed_tree_tmp <- list(frame = data.frame(var = "<leaf>", row.names = "1"))
    unclassed_tree_tmp
    """
    run_r(r_code)
    r_msg = r_error_message(lambda: run_r("path.rpart(unclassed_tree_tmp, nodes=1)"))
    assert r_msg is not None
    assert 'Not a legitimate "rpart" object' in r_msg

    import pandas as pd

    frame = pd.DataFrame({"var": ["<leaf>"]}, index=[1])
    with pytest.raises(ValueError) as exc_info:
        path_rpart({"frame": frame}, nodes=[1])
    assert str(exc_info.value) == 'Not a legitimate "rpart" object'


def test_path_rpart_missing_tree_argument_raises():
    """Neither side supplies any default for the first (`tree`) argument --
    calling with zero arguments must raise on both sides."""
    r_msg = r_error_message(lambda: run_r("path.rpart()"))
    with pytest.raises(TypeError) as exc_info:
        path_rpart()  # type: ignore[call-arg]
    assert_python_and_r_errors_agree(str(exc_info.value), r_msg, context="tree omitted entirely")


def test_path_rpart_legitimate_class_but_missing_frame_raises():
    """A genuinely "rpart"-classed object (R: `class(x) <- "rpart"`;
    python: `_rpart_class == 'rpart'`) that is nonetheless missing its
    `frame` element/key entirely: R's `ff <- object$frame` reads as NULL,
    then `if (n == 1L)` on `n <- nrow(NULL)` (itself NULL) raises "argument
    is of length zero"; python's `object['frame']` raises `KeyError`
    immediately, inside the `labels_rpart()` call path_rpart makes before
    ever reaching its own frame access. Both raise, for different
    underlying reasons."""
    r_code = """
    no_frame_tree_tmp <- structure(list(splits = matrix(0, nrow = 1, ncol = 5)), class = "rpart")
    no_frame_tree_tmp
    """
    run_r(r_code)
    r_msg = r_error_message(lambda: run_r("path.rpart(no_frame_tree_tmp, nodes=1)"))
    assert r_msg is not None
    assert "length zero" in r_msg

    with pytest.raises(KeyError):
        path_rpart({"_rpart_class": "rpart", "splits": np.zeros((1, 5))}, nodes=[1])


# ---------------------------------------------------------------------------
# Section 2: documented, permanent one-sided-raise gaps -- both directions
# represented.
# ---------------------------------------------------------------------------

def test_path_rpart_missing_nodes_argument_is_a_known_gap():
    """KNOWN GAP (R raises, python does not): omitting `nodes` entirely
    triggers R's *interactive* branch (`missing(nodes)` -> `xy <-
    rpartco(tree)`), and `rpartco()` itself immediately raises "no
    information available on parameters from previous call to plot()"
    whenever no prior `plot()` call has been made on the current graphics
    device (true in this headless test environment) -- so real R
    unavoidably errors here, never even reaching `identify()`.
    r2py_rpart.path_rpart()'s own `nodes is None` branch is instead a
    documented no-op stub (its own comment: "identify() is interactive R
    graphics; stub returns empty list so the while loop never runs"), so it
    returns `{}` without raising at all."""
    fit, r_fit = _kyphosis_fits()

    import rpy2.robjects as ro

    ro.globalenv["path_fit_tmp2"] = r_fit
    r_msg = r_error_message(lambda: run_r("path.rpart(path_fit_tmp2)"))
    assert r_msg is not None
    assert "no information available" in r_msg  # R: raises

    py_res = path_rpart(fit)  # python: does NOT raise
    assert py_res == {}


def test_path_rpart_nodes_bare_scalar_is_a_known_gap():
    """KNOWN GAP (python raises, R does not): `nodes=11` (a bare python
    int, as opposed to a length-1 list/array). R has no scalar/vector
    distinction -- a length-1 numeric works identically to any other
    numeric vector in `match()`. python's `path_rpart()` instead does
    `node_match(np.asarray(nodes), node)`; `np.asarray(11)` is a 0-d array,
    and iterating over a 0-d numpy array (`for n in nodes` inside
    `node_match()`) raises `TypeError: iteration over a 0-d array` --
    there is no equivalent scalar/vector unification on the python side."""
    fit, r_fit = _kyphosis_fits()

    import rpy2.robjects as ro

    ro.globalenv["path_fit_tmp3"] = r_fit
    r_msg = r_error_message(
        lambda: run_r('path_rpart_result_tmp <- path.rpart(path_fit_tmp3, nodes=11, print.it=FALSE)')
    )
    assert r_msg is None  # R: does NOT raise

    with pytest.raises(TypeError) as exc_info:
        path_rpart(fit, nodes=11, print_it=False)  # python: raises
    assert "0-d array" in str(exc_info.value)

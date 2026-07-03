"""Negative-path parity tests for r2py_rpart.rsq_rpart vs. R's
rpart::rsq.rpart.

rsq.rpart is a plain, exported R function (`export(..., rsq.rpart, ...)` in
NAMESPACE), not an S3 generic -- its own body does `if (!inherits(x,
"rpart")) stop("Not a legitimate \"rpart\" object")` directly, exactly like
printcp/plotcp (see test_printcp_negative.py's/test_plotcp_negative.py's own
notes on this same point) -- so a bare `rsq.rpart(x)` call reaches this
check directly for any `x`. All R-side calls below run inside a no-op
`pdf(NULL)` graphics device with console/table output swallowed (via
`_r_rpart_helpers.r_rsq_rpart_error()`), so they never try to open a real
display nor clutter test output in a headless test environment.

rsq_rpart.py's own explicit legitimacy check is:

  `not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart')` -> TypeError

-- mirroring printcp.py's `_rpart_class` check (not plotcp.py's weaker
`'cptable' not in x` check -- see printcp.rpart.py's own comparable check).
So, unlike plotcp's genuine, documented KNOWN GAP (a class-less dict with an
otherwise-valid `cptable` slips through plotcp.py unrejected), rsq_rpart.py
DOES reject a class-less dict here, just like printcp -- no such KNOWN GAP
exists for this particular check (see test 6 below).

Beyond that one explicit `raise`, rsq_rpart.py's remaining `x['cptable']`/
`x['method']` dict-key lookups and unguarded positional-column numpy
indexing (`p_rpart[:, 4]`/`[:, 3]`/`[:, 2]`/`[:, 1]`) are *implicit* failure
points with no dedicated `raise` site (rsq_rpart.py, unlike plotcp.py, has
no `ndim`/`shape[1] < 5` guard at all) -- each mirrors (with differently
worded messages, confirmed empirically against a live R session before
being written up here) a corresponding implicit failure inside R's own
`printcp(x)`/`p.rpart[, 5L]` etc.

Each test triggers an error condition on both sides and asserts that *both*
raise; if both raise but with differently-worded messages,
`assert_python_and_r_errors_agree` warns rather than fails (error text is
not part of rpart's documented contract) -- see tests/_r_rpart_helpers.py.
"""
from __future__ import annotations

import numpy as np
import pytest

from r2py_rpart import rpart
from r2py_rpart.rsq_rpart import rsq_rpart

from _r_rpart_helpers import (
    assert_python_and_r_errors_agree,
    from_r_dataframe,
    r_assign,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_matrix_literal,
    r_rsq_rpart_error,
    r_rsq_rpart_like_expr,
    r_rsq_rpart_runs_without_error,
    run_r,
)


_VALID_CPTABLE = np.array(
    [
        [0.5, 0, 1.0, 1.05, 0.10],
        [0.2, 1, 0.6, 0.70, 0.08],
        [0.01, 2, 0.4, 0.55, 0.07],
    ]
)


# ---------------------------------------------------------------------------
# 1-5. `x` is not a legitimate "rpart" object at all: None, a plain list, a
#      bare string, an empty dict, and a plain int. rsq_rpart.py's own check
#      (`not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart')`)
#      raises TypeError for all of these; R's `inherits(x, "rpart")` raises
#      the same "Not a legitimate ..." error for the R-equivalent value in
#      each case.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_x, r_expr",
    [
        (None, "NULL"),
        ([1, 2, 3], "c(1, 2, 3)"),
        ("hello", '"hello"'),
        ({}, "list()"),
        (5, "5"),
    ],
    ids=["none", "list", "string", "empty_dict", "int"],
)
def test_rsq_rpart_invalid_x_raises(bad_x, r_expr):
    with pytest.raises(Exception) as exc_info:
        rsq_rpart(bad_x)

    r_message = r_rsq_rpart_error(r_expr)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context=f"invalid x={bad_x!r}")


# ---------------------------------------------------------------------------
# 6. A valid-looking dict carrying all the "real" rpart fit components
#    (frame, method, cptable, ...) but with its `_rpart_class` marker
#    removed -- i.e. an object that "looks like" a legitimate fit but was
#    never actually blessed as one. Both sides reject it: R's equivalent is
#    stripping the "rpart" S3 class attribute via `class(fit) <- NULL` (so
#    `inherits(fit, "rpart")` becomes FALSE despite the list still holding
#    every named component `rpart()` produces), and rsq_rpart.py's own
#    `_rpart_class` check catches the python-side analogue directly. Unlike
#    plotcp.py's comparable check (a genuine, documented KNOWN GAP --
#    see test_plotcp_negative.py test 8), this is NOT a known gap: both
#    sides reject it, exactly like printcp.
# ---------------------------------------------------------------------------

def test_rsq_rpart_valid_looking_dict_missing_rpart_class_marker_raises():
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df_rsq_tmp", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", data_name="df_rsq_tmp", control="rpart.control(xval=5)")
    r_assign("unclassed_fit_tmp", r_fit)
    r_message = r_error_message(
        lambda: run_r(
            "grDevices::pdf(NULL); "
            "invisible(capture.output({class(unclassed_fit_tmp) <- NULL; "
            "rsq.rpart(unclassed_fit_tmp)})); grDevices::dev.off()"
        )
    )
    assert r_message is not None  # sanity: R does reject the class-less list

    py_fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 5})
    unclassed = dict(py_fit)
    del unclassed["_rpart_class"]
    with pytest.raises(Exception) as exc_info:
        rsq_rpart(unclassed)

    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="valid-looking dict missing _rpart_class"
    )


# ---------------------------------------------------------------------------
# 7. Calling rsq_rpart() with no arguments at all (`x` missing entirely, not
#    just invalid): Python's ordinary missing-required-positional-argument
#    TypeError vs. R's "argument \"x\" is missing, with no default".
# ---------------------------------------------------------------------------

def test_rsq_rpart_missing_required_x_argument_raises():
    r_message = r_error_message(lambda: run_r("rsq.rpart()"))

    with pytest.raises(Exception) as exc_info:
        rsq_rpart()  # type: ignore[call-arg]

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="rsq.rpart() with no arguments")


# ---------------------------------------------------------------------------
# 8. A dict that has both `_rpart_class` and `method`, but NO `cptable` key
#    at all -- rsq_rpart.py's `x['cptable']` lookup raises KeyError
#    directly. R's internal `p.rpart <- printcp(x)` gracefully returns NULL
#    when `x$cptable` is absent (printcp(x) itself does not error -- it
#    just prints "NULL" for the missing table), but the very next line,
#    `xstd <- p.rpart[, 5L]`, then raises on the NULL value ("incorrect
#    number of dimensions") -- confirmed empirically against a live R
#    session before being written up here. Both sides raise, for related
#    but differently-worded reasons.
# ---------------------------------------------------------------------------

def test_rsq_rpart_dict_missing_cptable_key_raises():
    run_r('x_no_cptable <<- structure(list(method = "anova"), class = "rpart")')
    r_message = r_rsq_rpart_error("x_no_cptable")
    assert r_message is not None

    with pytest.raises(Exception) as exc_info:
        rsq_rpart({"_rpart_class": "rpart", "method": "anova"})

    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="dict with no 'cptable' key")


# ---------------------------------------------------------------------------
# 9. `cptable` with fewer than 5 columns (only 3: CP/nsplit/rel error, i.e.
#    an `xval=0` fit's cptable) -- rsq.rpart.Rd's own documented purpose
#    (plotting the *cross-validated* R-square/relative-error) requires
#    xerror/xstd columns 4 and 5. rsq_rpart.py's `p_rpart[:, 4]` raises
#    IndexError directly (there is no dedicated `ValueError` guard here,
#    unlike plotcp.py's explicit `shape[1] < 5` check); R's `p.rpart[, 5L]`
#    raises its own "subscript out of bounds". Both raise, for related but
#    differently-worded reasons (confirmed empirically first).
# ---------------------------------------------------------------------------

def test_rsq_rpart_cptable_without_cross_validation_columns_raises():
    cptable_3col = np.array([[0.5, 0, 1.0], [0.01, 1, 0.3]])
    expr = r_rsq_rpart_like_expr(cptable_3col, method="anova")
    r_message = r_rsq_rpart_error(expr)
    assert r_message is not None and "subscript" in r_message

    with pytest.raises(Exception) as exc_info:
        rsq_rpart({"_rpart_class": "rpart", "method": "anova", "cptable": cptable_3col})

    assert isinstance(exc_info.value, IndexError)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="3-column (xval=0) cptable")


# ---------------------------------------------------------------------------
# 10. `cptable` as a 1-D vector (not a 2-D matrix at all) -- e.g. a
#     corrupted/malformed fit whose `cptable` collapsed to a single row.
#     rsq_rpart.py's `p_rpart[:, 4]` raises "too many indices for array"
#     (IndexError); R's `p.rpart[, 5L]` on a plain vector raises its own
#     distinct "incorrect number of dimensions" error -- both raise, for
#     related but differently-worded reasons.
# ---------------------------------------------------------------------------

def test_rsq_rpart_one_dimensional_cptable_raises():
    vec = np.array([0.5, 0.2, 0.05, 0.01, 0.1])
    run_r(
        'x_vec <<- structure(list(cptable = c(0.5, 0.2, 0.05, 0.01, 0.1), '
        'method = "anova"), class = "rpart")'
    )
    r_message = r_rsq_rpart_error("x_vec")
    assert r_message is not None

    with pytest.raises(Exception) as exc_info:
        rsq_rpart({"_rpart_class": "rpart", "method": "anova", "cptable": vec})

    assert isinstance(exc_info.value, IndexError)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="1-D vector cptable")


# ---------------------------------------------------------------------------
# 11. `cptable` as a bare python list-of-lists (neither numpy.ndarray nor
#     pandas.DataFrame) -- rsq_rpart.py's `hasattr(p_rpart, 'to_numpy')`
#     guard is False for a plain list, so it falls straight through to
#     `p_rpart[:, 4]`, which a python `list` cannot be indexed with (a
#     tuple index), raising an *unrelated* TypeError rather than any
#     documented error condition -- an internal implementation leak, not
#     one of rsq_rpart.py's own deliberate `raise` sites. R's own
#     equivalent (a plain `list()` of numeric vectors, rather than a
#     `matrix()`) is accepted by `[, 5L]` no better -- it raises its own
#     "incorrect number of dimensions" there too (confirmed empirically) --
#     so both sides raise, though the *kind* of error differs (TypeError
#     vs. a `stop()`-raised dimension error).
# ---------------------------------------------------------------------------

def test_rsq_rpart_list_of_lists_cptable_raises():
    run_r(
        'x_listcp <<- structure(list(cptable = list(c(0.5, 0, 1.0, 1.0, 0.05), '
        'c(0.05, 1, 0.6, 0.9, 0.04)), method = "anova"), class = "rpart")'
    )
    r_message = r_rsq_rpart_error("x_listcp")
    assert r_message is not None

    cptable_list = [[0.5, 0, 1.0, 1.0, 0.05], [0.05, 1, 0.6, 0.9, 0.04]]
    with pytest.raises(Exception) as exc_info:
        rsq_rpart({"_rpart_class": "rpart", "method": "anova", "cptable": cptable_list})
    assert isinstance(exc_info.value, TypeError)

    assert_python_and_r_errors_agree(
        str(exc_info.value), r_message, context="bare list-of-lists cptable (not ndarray/DataFrame)"
    )


# ---------------------------------------------------------------------------
# 12. A dict that has both `_rpart_class` and a valid `cptable`, but NO
#     `method` key at all -- rsq_rpart.py's `x['method']` lookup raises
#     KeyError directly (reached only *after* the cptable columns are
#     successfully sliced, since `method` is read after xstd/xerror/
#     rel_error/nsplit in rsq_rpart.py's own body). R's `x$method` on a
#     missing element is NULL, and `switch(NULL, anova = ..., ...)` (inside
#     the internal `printcp(x)` call, which runs *before* any cptable
#     slicing happens) raises "EXPR must be a length 1 vector" -- so R
#     actually fails *earlier* in its own execution than python does, a
#     check-order divergence noted here rather than silently folded into
#     the message-wording warning; both sides still raise.
# ---------------------------------------------------------------------------

def test_rsq_rpart_dict_missing_method_key_raises():
    run_r(f"x_no_method <<- structure(list(cptable = {r_matrix_literal(_VALID_CPTABLE)}), class = \"rpart\")")
    r_message = r_rsq_rpart_error("x_no_method")
    assert r_message is not None and "length 1" in r_message

    with pytest.raises(Exception) as exc_info:
        rsq_rpart({"_rpart_class": "rpart", "cptable": _VALID_CPTABLE})

    assert isinstance(exc_info.value, KeyError)
    assert_python_and_r_errors_agree(str(exc_info.value), r_message, context="dict with no 'method' key")

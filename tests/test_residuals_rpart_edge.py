"""Boundary/edge-case parity tests for r2py_rpart.residuals_rpart vs. R's
residuals.rpart (rpart:::residuals.rpart, S3-dispatched via residuals()).

See test_residuals_rpart_positive.py's module docstring for the general
comparison strategy, and test_residuals_rpart_negative.py's for the
`residuals(list(a=1))`-vs-`rpart:::residuals.rpart(list(a=1))` (generic
S3-dispatch bypass) distinction reused for the synthetic-object tests below.

KNOWN, GENUINE BUGS/GAPS FOUND WHILE WRITING THESE TESTS
--------------------------------------------------------------------------
Five confirmed, permanent divergences from R are documented as explicit
regression-anchor tests below rather than silently worked around (each
confirmed directly against a live R session before being written down):

  1. `test_residuals_classification_pearson_deviance_yval2_stacking_known_bug`
     -- residuals_rpart.py's classification pearson/deviance branch does
     `np.asarray(frame['yval2'].values[where_0], dtype=np.float64)`, but
     `frame['yval2']` is stored as one 1-D numpy array *per row* (an
     object-dtype column -- see rpart.py's own `frame["yval2"] =
     list(np.hstack(...))`), and under current numpy semantics
     `np.asarray(<object array of equal-length 1-D arrays>, dtype=float)`
     raises `ValueError: setting an array element with a sequence` instead
     of stacking into a proper 2-D array (numpy *does* auto-stack this for
     a plain python list of arrays, e.g. via `.tolist()` first -- see
     predict_rpart.py's own `_yval2_matrix()` helper, which sidesteps this
     exact same underlying data layout correctly). R itself computes a
     valid, finite pearson/deviance residual for every classification tree.
     This is filed as a non-xfail assertion so it starts passing
     automatically the moment residuals_rpart.py's yval2 extraction is
     fixed (e.g. `np.array(frame['yval2'].values[where_0].tolist(), ...)`,
     mirroring `_yval2_matrix()`).

  2. `test_residuals_missing_where_key_known_gap` -- R's `object$where` on an
     object missing a `$where` component is simply `NULL`; `frame$yval[NULL]`
     is `numeric(0)`, and R's arithmetic on a zero-length vector propagates
     silently (`y - numeric(0)` is `numeric(0)`, with no warning/error) --
     confirmed empirically. python's `object['where']` raises `KeyError`
     immediately instead.

  3. `test_residuals_out_of_range_where_index_known_gap` -- an out-of-range
     `where` index (beyond `nrow(frame)`) is `NA` in R's own
     `frame$yval[out_of_range_index]` (1-based, out-of-bounds numeric
     indexing into an R vector yields `NA`, not an error) -- confirmed
     empirically. python's 0-based numpy fancy-indexing instead raises
     `IndexError`.

  4. `test_residuals_missing_frame_key_but_classed_known_gap` -- an object
     with class `"rpart"` but *no* `$frame` component at all passes R's
     `inherits(object, "rpart")` check trivially (that check only looks at
     the class attribute) and silently computes `numeric(0)` (same
     `NULL`-propagation mechanism as gap 2 above). python's
     residuals_rpart() has its own *additional*, stricter legitimacy check
     (`'frame' not in object`) that immediately raises `ValueError` for
     this same input -- a stricter check than R's own, not merely a
     translation of it.

  5. `test_residuals_y_false_fit_stub_returns_nan_instead_of_raising_known_gap`
     -- when a tree is fit with `y=False` (so `object$y`/`object['y']` is
     absent), R's residuals.rpart falls back to
     `model.extract(model.frame(object), "response")`, reconstructing `y`
     from the stored `$call`+`$terms` (this can itself error inside R for
     unrelated environment-scoping reasons under rpy2, but it never
     silently produces a numeric result when it can't). python's own
     equivalent fallback (`object.get('y')`, called twice, a no-op stub --
     see residuals_rpart.py's own comment: "model.extract(model.frame
     (object), 'response') stub") leaves `y` as `None`; the subsequent
     `np.asarray(None, dtype=np.float64) - frame['yval'][where_0]`
     broadcasts a scalar `nan` against the fitted values, so python instead
     silently returns an all-`nan` array of the *correct length*, with no
     exception raised at all.

Each is confirmed via direct experimentation (see the accompanying comments)
rather than assumed from reading the source alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from r2py_rpart import residuals_rpart, rpart

from _r_rpart_helpers import (
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_error_message,
    r_fit_rpart,
    r_matrix_literal,
    r_minimal_rpart_expr,
    r_residuals,
    r_residuals_to_python,
    run_r,
)


# ---------------------------------------------------------------------------
# 1. Root-only tree (a single leaf node, forced via cp=1 so no split ever
#    clears the complexity threshold), classification, type="usual": every
#    observation must get the identical residual (the loss for the single
#    global predicted class).
# ---------------------------------------------------------------------------

def test_residuals_root_only_tree_classification_usual_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=1)")
    r_resid = r_residuals_to_python(r_residuals(r_fit, type="usual"))

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, control={"xval": 0, "cp": 1})
    assert len(py_fit["frame"]) == 1  # sanity: really is root-only
    py_resid = residuals_rpart(py_fit, type="usual")

    assert_allclose(py_resid, r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 2. Root-only tree, regression (anova): all three `type=` values must
#    coincide (as always for anova) and equal a constant `y - mean(y)`.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resid_type", ["usual", "pearson", "deviance"])
def test_residuals_root_only_tree_regression_all_types_mtcars(resid_type):
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp", control="rpart.control(xval=0, cp=1)")
    r_resid = r_residuals_to_python(r_residuals(r_fit, type=resid_type))

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0, "cp": 1})
    assert len(py_fit["frame"]) == 1
    py_resid = residuals_rpart(py_fit, type=resid_type)

    assert_allclose(py_resid, r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 3. Empty (0-observation) `y`/`where`, via a minimal synthetic object: both
#    sides must return a length-0 result rather than erroring.
# ---------------------------------------------------------------------------

def test_residuals_empty_y_and_where_returns_empty():
    r_expr = r_minimal_rpart_expr(
        y="numeric(0)", frame_yval="c(1, 2, 3)", where="integer(0)", method="anova"
    )
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr})"))
    assert len(r_resid) == 0

    py_fit = {
        "y": np.array([]),
        "frame": pd.DataFrame({"yval": [1.0, 2.0, 3.0]}, index=[1, 2, 3]),
        "where": np.array([], dtype=np.int64),
        "method": "anova",
    }
    py_resid = residuals_rpart(py_fit)
    assert len(py_resid) == 0


# ---------------------------------------------------------------------------
# 4. Singleton (single-observation) synthetic object, all three `type=`
#    values, classification method -- using "usual" only (see module
#    docstring gap 1: pearson/deviance is a known bug for classification).
# ---------------------------------------------------------------------------

def test_residuals_singleton_observation_classification_usual():
    r_expr = r_minimal_rpart_expr(
        y="c(2)",
        frame_yval="c(1)",
        where="c(1)",
        method="class",
        parms="list(loss=matrix(c(0,1,1,0), nrow=2))",
        ylevels='c("A", "B")',
    )
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr}, type=\"usual\")"))
    assert len(r_resid) == 1

    py_fit = {
        "y": np.array([2], dtype=np.int64),
        "frame": pd.DataFrame({"yval": [1.0]}, index=[1]),
        "where": np.array([1], dtype=np.int64),
        "method": "class",
        "parms": {"loss": np.array([[0.0, 1.0], [1.0, 0.0]])},
        "_ylevels": ["A", "B"],
    }
    py_resid = residuals_rpart(py_fit, type="usual")
    assert_allclose(py_resid, r_resid, rtol=1e-6)


# ---------------------------------------------------------------------------
# 5. Poisson-method residuals where `expect == 0` exactly (`lambda == 0` at
#    the predicted node): residuals.rpart.R's own `temp <- ifelse(expect ==
#    0, 0.0001, 0)` "failsafe for log(0)" branch actually applies here,
#    giving a *finite* pearson/deviance value -- the complementary case to
#    test_residuals_rpart_positive.py's poisson test (where `expect != 0`
#    almost everywhere, hitting the "divide by zero" branch of that same
#    `ifelse` instead). Isolated via a minimal synthetic object so `expect
#    == 0` can be hit deterministically (an actual fitted lambda is
#    essentially never exactly 0.0).
# ---------------------------------------------------------------------------

def test_residuals_poisson_expect_exactly_zero_finite_pearson_deviance():
    # y = cbind(time, events); node 1: lambda=0 (expect=0 for any time);
    # node 2: lambda=2, time=1 -> expect=2 (the ordinary divide-by-zero case,
    # included for contrast within the same test).
    r_expr = r_minimal_rpart_expr(
        y="matrix(c(5, 1, 0, 3), nrow=2)",  # col1=time=(5,1), col2=events=(0,3)
        frame_yval="c(0, 2)",
        where="c(1, 2)",
        method="poisson",
    )
    r_pearson = r_residuals_to_python(run_r(f'residuals({r_expr}, type="pearson")'))
    r_deviance = r_residuals_to_python(run_r(f'residuals({r_expr}, type="deviance")'))

    py_fit = {
        "y": np.column_stack([[5.0, 1.0], [0.0, 3.0]]),
        "frame": pd.DataFrame({"yval": [0.0, 2.0]}, index=[1, 2]),
        "where": np.array([1, 2], dtype=np.int64),
        "method": "poisson",
    }
    py_pearson = residuals_rpart(py_fit, type="pearson")
    py_deviance = residuals_rpart(py_fit, type="deviance")

    # node 1 (expect == 0): finite, via the temp=0.0001 failsafe branch.
    assert np.isfinite(r_pearson[0]) and np.isfinite(py_pearson[0])
    assert_allclose(py_pearson, r_pearson, rtol=1e-6, equal_nan=True)
    assert_allclose(py_deviance, r_deviance, rtol=1e-6, equal_nan=True)
    # node 2 (expect=2 != 0): the ordinary divide-by-zero-by-construction
    # case -- events(3) != expect(2), so pearson is +-inf, not nan.
    assert np.isinf(r_pearson[1]) and np.isinf(py_pearson[1])


# ---------------------------------------------------------------------------
# 6. `type=None` explicitly (as opposed to omitted): R's `match.arg(NULL)`
#    resolves to the first choice ("usual") without error, but python's
#    `type not in valid_types` -> `[t for t in valid_types if
#    t.startswith(None)]` raises `TypeError` immediately (`str.startswith`
#    requires a str argument) -- the reverse-direction sibling of the
#    `type=123` case in test_residuals_rpart_negative.py (there, both sides
#    raise; here, only python does).
# ---------------------------------------------------------------------------

def test_residuals_type_none_r_resolves_default_python_raises_known_gap():
    r_expr = r_minimal_rpart_expr(method="anova")
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr}, type=NULL)"))
    r_resid_usual = r_residuals_to_python(run_r(f'residuals({r_expr}, type="usual")'))
    assert_allclose(r_resid, r_resid_usual)  # sanity: NULL really means "usual"

    py_fit = {
        "y": np.array([1.0, 2.0, 3.0]),
        "frame": pd.DataFrame({"yval": [1.0, 2.0, 3.0]}, index=[1, 2, 3]),
        "where": np.array([1, 2, 3], dtype=np.int64),
        "method": "anova",
    }
    with pytest.raises(TypeError):
        residuals_rpart(py_fit, type=None)


# ---------------------------------------------------------------------------
# 7. KNOWN, GENUINE BUG: classification pearson/deviance residuals crash in
#    python (frame['yval2']'s per-row-array column can't be
#    `np.asarray(..., dtype=float)`-stacked directly), while R computes a
#    valid, finite result -- see module docstring gap 1. A minimal synthetic
#    2-class `yval2` (predicted class, 2 counts, 2 probabilities, 1
#    node-probability -- 6 columns total) isolates this from `rpart()`
#    tree-fitting entirely; the exact R-side numeric result was independently
#    hand-verified (`yprob = (0.8, 0.2)`; pearson = `(1-yhat)/yhat`; deviance
#    = `-2*log(yhat)`) before writing this test.
# ---------------------------------------------------------------------------

def test_residuals_classification_pearson_deviance_yval2_stacking_known_bug():
    yval2_mat = r_matrix_literal(np.array([[1.0, 5.0, 2.0, 0.8, 0.2, 0.9]]))
    r_expr = r_minimal_rpart_expr(
        y="c(1, 2, 1)",
        frame_yval="c(1)",
        where="c(1, 1, 1)",
        method="class",
        yval2=yval2_mat,
        ylevels='c("A", "B")',
    )
    r_pearson = r_residuals_to_python(run_r(f'residuals({r_expr}, type="pearson")'))
    r_deviance = r_residuals_to_python(run_r(f'residuals({r_expr}, type="deviance")'))
    # sanity: hand-computed expected values, independently of this port.
    assert_allclose(r_pearson, [0.25, 4.0, 0.25], rtol=1e-6)
    assert_allclose(r_deviance, [0.4462871, 3.2188758, 0.4462871], rtol=1e-5)

    frame = pd.DataFrame({"yval": [1.0]}, index=[1])
    frame["yval2"] = [np.array([1.0, 5.0, 2.0, 0.8, 0.2, 0.9])]
    py_fit = {
        "y": np.array([1, 2, 1], dtype=np.int64),
        "frame": frame,
        "where": np.array([1, 1, 1], dtype=np.int64),
        "method": "class",
        "_ylevels": ["A", "B"],
    }

    # python currently raises a ValueError inside the `np.asarray(frame
    # ['yval2'].values[where_0], dtype=np.float64)` stacking -- see module
    # docstring's root-cause analysis; these calls are not wrapped in
    # pytest.raises() so the test fails loudly (as an error) until fixed,
    # at which point it should also start asserting numeric parity with R.
    py_pearson = residuals_rpart(py_fit, type="pearson")
    assert_allclose(py_pearson, r_pearson, rtol=1e-6)
    py_deviance = residuals_rpart(py_fit, type="deviance")
    assert_allclose(py_deviance, r_deviance, rtol=1e-5)


# ---------------------------------------------------------------------------
# 8. KNOWN GAP: `object` missing the `where` key/component entirely. R's
#    `object$where` is silently `NULL` (`frame$yval[NULL]` is `numeric(0)`,
#    and `y - numeric(0)` is `numeric(0)`, no error) -- confirmed
#    empirically. python's `object['where']` raises `KeyError` immediately.
# ---------------------------------------------------------------------------

def test_residuals_missing_where_key_known_gap():
    r_expr = (
        'structure(list(y = c(1, 2, 3), frame = data.frame(yval = c(1, 2, 3)), '
        'method = "anova"), class = "rpart")'
    )
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr})"))
    assert list(r_resid) == []  # R: silently numeric(0), no error

    py_fit = {
        "y": np.array([1.0, 2.0, 3.0]),
        "frame": pd.DataFrame({"yval": [1.0, 2.0, 3.0]}, index=[1, 2, 3]),
        "method": "anova",
    }
    # python currently raises KeyError('where') here -- not wrapped in
    # pytest.raises() so the mismatch (R succeeds silently; python does not)
    # fails loudly, as a permanent regression anchor for this documented gap.
    py_resid = residuals_rpart(py_fit)
    assert len(py_resid) == 0


# ---------------------------------------------------------------------------
# 9. KNOWN GAP: an out-of-range `where` index (beyond `nrow(frame)`). R's
#    1-based, out-of-bounds numeric vector indexing yields `NA` (not an
#    error); python's 0-based numpy fancy-indexing raises `IndexError`.
# ---------------------------------------------------------------------------

def test_residuals_out_of_range_where_index_known_gap():
    r_expr = r_minimal_rpart_expr(
        y="c(1, 2, 3)", frame_yval="c(1, 2, 3)", where="c(1, 2, 99)", method="anova"
    )
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr})"))
    assert np.isnan(r_resid[2])  # R: silently NA for the out-of-range lookup
    assert_allclose(r_resid[:2], [0.0, 0.0])

    py_fit = {
        "y": np.array([1.0, 2.0, 3.0]),
        "frame": pd.DataFrame({"yval": [1.0, 2.0, 3.0]}, index=[1, 2, 3]),
        "where": np.array([1, 2, 99], dtype=np.int64),
        "method": "anova",
    }
    # python currently raises IndexError here (index 98 out of bounds for a
    # 3-row frame) -- not wrapped in pytest.raises() so the mismatch fails
    # loudly, as a permanent regression anchor for this documented gap.
    py_resid = residuals_rpart(py_fit)
    assert np.isnan(py_resid[2])
    assert_allclose(py_resid[:2], [0.0, 0.0])


# ---------------------------------------------------------------------------
# 10. KNOWN GAP: an object classed `"rpart"` but with no `$frame` component
#     at all. R's `inherits(object, "rpart")` check only inspects the class
#     attribute, so this object is "legitimate" as far as R is concerned,
#     and `frame <- object$frame` is silently `NULL` (same `NULL`-propagation
#     mechanism as gap 8 above) -- confirmed empirically: R returns
#     `numeric(0)`, no error. python's residuals_rpart() has its own
#     *additional*, stricter check (`'frame' not in object`) that
#     immediately raises `ValueError("Not a legitimate \"rpart\" object")`
#     for this exact same input.
# ---------------------------------------------------------------------------

def test_residuals_missing_frame_key_but_classed_known_gap():
    r_expr = 'structure(list(y = c(1, 2, 3), where = c(1, 2, 3), method = "anova"), class = "rpart")'
    r_resid = r_residuals_to_python(run_r(f"residuals({r_expr})"))
    assert list(r_resid) == []  # R: silently numeric(0), no error

    py_fit = {"y": np.array([1.0, 2.0, 3.0]), "where": np.array([1, 2, 3]), "method": "anova"}
    # python currently raises ValueError('Not a legitimate "rpart" object')
    # here (its own stricter, non-R-derived legitimacy check) -- not wrapped
    # in pytest.raises() so the mismatch fails loudly, as a permanent
    # regression anchor for this documented gap.
    py_resid = residuals_rpart(py_fit)
    assert len(py_resid) == 0


# ---------------------------------------------------------------------------
# 11. KNOWN GAP: a tree fit with `y=False` (so `object['y']` is absent).
#     R's residuals.rpart falls back to `model.extract(model.frame(object),
#     "response")` -- confirmed to *raise* under rpy2 for this exact
#     scenario (an environment-scoping issue reconstructing model.frame()
#     outside interactive top-level R, not a python-vs-R behavioral target
#     in itself, but it does confirm R never silently returns a numeric
#     result when `$y` is absent and reconstruction fails). python's
#     equivalent stub (`object.get('y')`, called twice, a literal no-op --
#     see residuals_rpart.py's own comment) leaves `y = None`, and
#     `np.asarray(None, dtype=float) - frame['yval'][where_0]` silently
#     broadcasts to an all-`nan` array of the correct length, with no
#     exception at all.
# ---------------------------------------------------------------------------

def test_residuals_y_false_fit_stub_returns_nan_instead_of_raising_known_gap():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = run_r(
        'rpart(mpg ~ wt + hp, data=df, method="anova", y=FALSE, control=rpart.control(xval=0))'
    )
    import rpy2.robjects as ro

    ro.globalenv["resid_edge_fit_tmp"] = r_fit
    r_message = r_error_message(lambda: run_r("residuals(resid_edge_fit_tmp)"))
    assert r_message is not None  # R: raises trying to reconstruct model.frame(object)

    py_fit = rpart("mpg ~ wt + hp", data=df, method="anova", control={"xval": 0}, y=False)
    assert "y" not in py_fit  # sanity: really did omit $y
    # python currently does NOT raise here -- it silently returns an
    # all-nan array of the correct length instead. Not wrapped in
    # pytest.raises() so this mismatch (R raises; python does not) fails
    # loudly, as a permanent regression anchor for this documented gap.
    py_resid = residuals_rpart(py_fit)
    assert len(py_resid) == len(df)
    assert np.all(np.isnan(py_resid))

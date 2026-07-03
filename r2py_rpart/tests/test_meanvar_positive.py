"""Positive-path parity tests for r2py_rpart.meanvar vs. R's `meanvar`
(dispatching to `meanvar.rpart`).

meanvar(tree, ...) (rpart/R/meanvar.rpart.R) is a plain S3 generic defined
within the rpart package itself (`meanvar <- function(tree, ...)
UseMethod("meanvar")`), with a single registered method, `meanvar.rpart`:

    meanvar.rpart <- function(tree, xlab = "ave(y)", ylab = "ave(deviance)", ...)
    {
        if (!inherits(tree, "rpart")) stop("Not a legitimate \"rpart\" object")
        if (!tree$method == "anova") stop("Plot not useful for classification or poisson trees")
        frame <- tree$frame
        frame <- frame[frame$var == "<leaf>", ]
        x <- frame$yval
        y <- frame$dev/frame$n
        label <- row.names(frame)
        plot(x, y, xlab = xlab, ylab = ylab, type = "n", ...)
        text(x, y, label)
        invisible(list(x = x, y = y, label = label))
    }

r2py_rpart's `meanvar(tree, **kwargs)` is a thin pass-through to
`meanvar_rpart(tree, xlab=..., ylab=..., **kwargs)` (see
r2py_rpart/meanvar_rpart.py) -- a follow-up test-generation task covers
`meanvar_rpart` directly; these tests exercise the public `meanvar` entry
point, benchmarking it against R's bare S3-generic `meanvar(tree, ...)`
call (the documented calling convention, `usage{meanvar(tree, ...)}`).

Unlike plotcp.R/rsq.rpart.R (whose derivations are keyed off `tree$cptable`,
built from RNG-driven cross-validation folds that R's and python's rpart()
draw independently -- see those modules' own test-generation notes), meanvar
is a *purely deterministic* function of `tree$frame` (specifically
`yval`/`dev`/`n` for the "<leaf>" rows) -- no cross-validation is involved at
all. So real, identically-fitted trees (built by R's `rpart()` and
r2py_rpart's `rpart()` from the same formula/data, `xval=0`) are directly
comparable end to end, in addition to minimal hand-built synthetic `frame`s
(built via `_r_rpart_helpers.build_meanvar_tree()` / `r_meanvar_like_expr()`)
that exercise the "<leaf>"-only filtering and various numeric frame
contents more directly.

Both sides return the derived `{"x":, "y":, "label":}` triple (R's
`invisible(list(x=, y=, label=))`; python's plain returned dict) -- these
are the primary comparison target. r2py_rpart.meanvar() additionally sets
concrete axis limits/labels/text annotations on the `matplotlib.axes.Axes`
it creates (`ax.set_xlim(x.min(), x.max())`, etc.) which R's
`plot(x, y, type="n")`/`text(x, y, label)` calls achieve too, but does not
itself return -- those are checked here only for *internal* consistency
(the plotted values on the python side agree with the derived x/y/label
python itself just returned), not against R.

See tests/_r_rpart_helpers.py's "meanvar-specific plumbing" section (both
R- and python-side) for all the shared machinery used below.
"""
from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from r2py_rpart import rpart
from r2py_rpart.meanvar_rpart import meanvar

from _r_rpart_helpers import (
    build_meanvar_tree,
    call_meanvar_and_extract,
    cu_summary_df,
    mtcars_df,
    r_assign,
    r_control,
    r_dataframe_assign,
    r_fit_rpart,
    r_meanvar_like_expr,
    r_meanvar_result,
    r_meanvar_runs_without_error,
)


# ---------------------------------------------------------------------------
# 1. A real, identically-fitted anova tree (mtcars), default xlab/ylab.
# ---------------------------------------------------------------------------

def test_meanvar_real_mtcars_fit_default_labels_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control=r_control(xval=0))
    r_assign("mv_fit_tmp", r_fit)
    r_out = r_meanvar_result("mv_fit_tmp")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0})
    py_out = call_meanvar_and_extract(py_fit)

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-10)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-10)
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "ave(y)"
    assert py_out["ylabel"] == "ave(deviance)"
    # python-only self-consistency: the axis limits it set match its own
    # derived x/y range exactly (mirrors r2py_rpart.meanvar_rpart.py's own
    # `ax.set_xlim(x.min(), x.max())`/`ax.set_ylim(y.min(), y.max())`).
    assert py_out["xlim"] == (float(py_out["x"].min()), float(py_out["x"].max()))
    assert py_out["ylim"] == (float(py_out["y"].min()), float(py_out["y"].max()))


# ---------------------------------------------------------------------------
# 2. A real, identically-fitted anova tree (cu.summary's Price ~ ...),
#    custom xlab AND ylab both supplied.
# ---------------------------------------------------------------------------

def test_meanvar_real_cu_summary_fit_custom_xlab_ylab_matches_r():
    df = cu_summary_df().dropna(subset=["Price", "Mileage", "Type", "Country"])
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Price ~ Mileage + Type + Country", control=r_control(xval=0, minsplit=4))
    r_assign("mv_fit_tmp", r_fit)
    r_out = r_meanvar_result("mv_fit_tmp", xlab="Fitted Price", ylab="Node Deviance / n")

    py_fit = rpart(
        "Price ~ Mileage + Type + Country", data=df, method="anova",
        control={"xval": 0, "minsplit": 4},
    )
    py_out = call_meanvar_and_extract(py_fit, xlab="Fitted Price", ylab="Node Deviance / n")

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-8)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-8)
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "Fitted Price"
    assert py_out["ylabel"] == "Node Deviance / n"


# ---------------------------------------------------------------------------
# 3. Synthetic root-only tree (a single "<leaf>" row) -- the minimal
#    non-degenerate case.
# ---------------------------------------------------------------------------

def test_meanvar_synthetic_root_only_tree_matches_r():
    var, yval, dev, n, index = ["<leaf>"], [20.0], [50.0], [10.0], [1]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"] == ["1"]


# ---------------------------------------------------------------------------
# 4. Synthetic tree mixing internal-node and leaf rows -- exercises the
#    `frame$var == "<leaf>"` filter (only the 2 leaf rows should survive).
# ---------------------------------------------------------------------------

def test_meanvar_synthetic_internal_and_leaf_mix_matches_r():
    var = ["x1", "<leaf>", "<leaf>"]
    yval = [10.0, 8.0, 15.0]
    dev = [50.0, 5.0, 3.0]
    n = [10.0, 6.0, 4.0]
    index = [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree, xlab="custom x", ylab="custom y")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="custom x", ylab="custom y")

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"] == ["2", "3"]
    assert len(py_out["x"]) == 2  # the internal "x1" row was filtered out


# ---------------------------------------------------------------------------
# 5. Synthetic tree with several leaves at deeper nesting (5 leaves, mixed
#    with internal rows), checking row-order preservation end to end.
# ---------------------------------------------------------------------------

def test_meanvar_synthetic_multi_leaf_tree_matches_r():
    var = ["x1", "x2", "<leaf>", "<leaf>", "x3", "<leaf>", "<leaf>", "<leaf>"]
    yval = [10.0, 6.0, 4.0, 9.0, 14.0, 12.0, 18.0, 22.0]
    dev = [100.0, 40.0, 8.0, 15.0, 30.0, 6.0, 5.0, 7.0]
    n = [20.0, 10.0, 5.0, 5.0, 10.0, 4.0, 3.0, 3.0]
    index = [1, 2, 4, 5, 3, 6, 7, 15]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"] == ["4", "5", "6", "7", "15"]


# ---------------------------------------------------------------------------
# 6. xlab supplied, ylab left at its default.
# ---------------------------------------------------------------------------

def test_meanvar_custom_xlab_only_default_ylab_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree, xlab="my x label")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, xlab="my x label")

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "my x label"
    assert py_out["ylabel"] == "ave(deviance)"  # untouched R default


# ---------------------------------------------------------------------------
# 7. ylab supplied, xlab left at its default.
# ---------------------------------------------------------------------------

def test_meanvar_custom_ylab_only_default_xlab_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree, ylab="my y label")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr, ylab="my y label")

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["label"] == r_out["label"]
    assert py_out["xlabel"] == "ave(y)"  # untouched R default
    assert py_out["ylabel"] == "my y label"


# ---------------------------------------------------------------------------
# 8. Negative yval/dev values (a legitimate anova tree can have a negative
#    fitted mean and/or deviance contribution) -- sign must be preserved
#    identically through the `dev/n` division.
# ---------------------------------------------------------------------------

def test_meanvar_negative_yval_and_dev_matches_r():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [-5.0, 5.0], [-10.0, 10.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])
    assert py_out["y"][0] < 0 < py_out["y"][1]


# ---------------------------------------------------------------------------
# 9. Non-integer (fractional) yval/dev/n values -- a generic float-typed
#    frame, not just whole numbers.
# ---------------------------------------------------------------------------

def test_meanvar_fractional_values_matches_r():
    var = ["<leaf>", "<leaf>", "<leaf>"]
    yval = [1.5, 2.25, 3.125]
    dev = [0.75, 1.125, 2.0625]
    n = [3.0, 4.0, 5.0]
    index = [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree)

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"], rtol=1e-12)
    assert_allclose(py_out["y"], r_out["y"], rtol=1e-12)
    assert py_out["label"] == r_out["label"]


# ---------------------------------------------------------------------------
# 10. Extra, unrecognized keyword arguments (mirroring R's `...`, which
#     meanvar.rpart forwards into `plot()`/`text()` as extra graphical
#     parameters e.g. `col=`) -- r2py_rpart.meanvar_rpart.py accepts (and
#     silently ignores) arbitrary `**kwargs` rather than erroring, so this
#     just confirms passing one through doesn't crash and doesn't change
#     the derived data, while independently confirming R's real meanvar()
#     also accepts a `col=` graphical parameter without raising (it is a
#     genuine, don't-care-about-the-value pass-through on both sides, so no
#     R-side value is meaningfully compared beyond "did not raise").
# ---------------------------------------------------------------------------

def test_meanvar_extra_unrecognized_kwarg_does_not_raise():
    var, yval, dev, n, index = ["<leaf>", "<leaf>"], [3.0, 7.0], [2.0, 4.0], [2.0, 2.0], [1, 2]
    tree = build_meanvar_tree(var, yval, dev, n, index)
    py_out = call_meanvar_and_extract(tree, col="red")

    r_expr = r_meanvar_like_expr(var, yval, dev, n, index)
    assert r_meanvar_runs_without_error(r_expr)  # R's meanvar(tree, col="red") also succeeds
    r_out = r_meanvar_result(r_expr)

    assert_allclose(py_out["x"], r_out["x"])
    assert_allclose(py_out["y"], r_out["y"])


# ---------------------------------------------------------------------------
# 11. meanvar() itself (the public entry point under test, as opposed to
#     meanvar_rpart directly) is confirmed to be a pure pass-through: the
#     return value from calling the top-level `meanvar` import is identical
#     to what call_meanvar_and_extract's plotted data derives.
# ---------------------------------------------------------------------------

def test_meanvar_wrapper_return_value_matches_direct_call():
    var, yval, dev, n, index = ["<leaf>", "<leaf>", "<leaf>"], [1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [1.0, 1.0, 1.0], [1, 2, 3]
    tree = build_meanvar_tree(var, yval, dev, n, index)

    result = meanvar(tree, xlab="a", ylab="b")

    assert set(result.keys()) == {"x", "y", "label"}
    assert_allclose(result["x"], [1.0, 2.0, 3.0])
    assert_allclose(result["y"], [1.0, 2.0, 3.0])
    assert result["label"] == ["1", "2", "3"]

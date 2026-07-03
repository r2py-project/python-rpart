"""Positive-path parity tests for r2py_rpart.prune (and its underlying
prune_rpart) vs. R's rpart::prune (which S3-dispatches to prune.rpart).

Both `prune` (the S3 generic) and `prune.rpart` (its method) are directly
*exported* from the rpart NAMESPACE, so either can be called directly from R
with no `rpart:::` internal-access trick -- see tests/_r_rpart_helpers.py's
prune-specific plumbing (`r_prune`, `r_prune_call_code`, `r_prune_error`).
r2py_rpart.prune()/prune_rpart() never go through any dispatch layer of
their own, so the comparison target used throughout below is R's
`prune.rpart(x, cp=...)` called directly (`generic=False`, `r_prune()`'s
default) -- except for one test (#9) that explicitly cross-checks the
generic `prune(x, cp=...)` S3-dispatch form against the direct one, to
confirm they agree (as they must, since `class(x) == "rpart"` for every
genuine fit used here).

Each test builds an rpart fit independently in both R and Python from the
*same* formula/data/control (xval=0, so tree structure is deterministic and
already known -- from test_rpart_positive.py -- to match between the two
implementations), then calls prune(fit, cp=...) on both sides and asserts
that the resulting `$frame` (var/complexity/ncompete/nsurrogate/row names),
`$cptable`, `$splits`, `$where`, and `$variable.importance` all agree.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart
from r2py_rpart.prune import prune

from _r_rpart_helpers import (
    CU_RELIABILITY_LEVELS,
    extract_r_fit,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_prune,
    run_r,
    stagec_df,
)


def _assert_pruned_matches_r(py_pruned: dict, r_pruned) -> None:
    """Assert that a python-pruned fit dict and an R-pruned rpart object
    (raw rpy2 result of `prune.rpart(...)`/`prune(...)`) agree on every
    field prune.rpart.R actually recomputes or carries over: `$frame`
    (var/complexity/ncompete/nsurrogate, and its row names/node ids),
    `$cptable`, `$splits`, `$where`, and `$variable.importance`."""
    r_out = extract_r_fit(r_pruned)

    py_frame = py_pruned["frame"]
    assert py_frame["var"].tolist() == r_out["var"]
    assert_allclose(py_frame.index.to_numpy(dtype=float), r_out["frame_index"].astype(float))
    assert_allclose(py_frame["complexity"].to_numpy(), r_out["complexity"], rtol=1e-6, atol=1e-8)
    assert_allclose(py_frame["ncompete"].to_numpy(), r_out["ncompete"])
    assert_allclose(py_frame["nsurrogate"].to_numpy(), r_out["nsurrogate"])

    assert_allclose(py_pruned["cptable"].to_numpy(dtype=float), r_out["cptable"], rtol=1e-5, atol=1e-8)
    assert_allclose(np.asarray(py_pruned["where"], dtype=float), r_out["where"])

    py_splits = py_pruned.get("splits")
    if r_out["splits"] is None:
        assert py_splits is None or len(py_splits) == 0
    else:
        assert py_splits is not None
        assert_allclose(py_splits.to_numpy(dtype=float), r_out["splits"], rtol=1e-6, atol=1e-8)

    py_vi = py_pruned.get("variable.importance")
    r_vi = r_out["variable_importance"]
    if r_vi is None or len(r_vi) == 0:
        assert py_vi is None or len(py_vi) == 0
    else:
        assert py_vi is not None
        assert set(py_vi.index) == set(r_vi.keys())
        for k, r_val in r_vi.items():
            assert_allclose(float(py_vi[k]), r_val, rtol=1e-5, atol=1e-8)


# ---------------------------------------------------------------------------
# 1. method="anova" (mtcars): prune at a mid-range cp strictly between the
#    cptable's first and last CP values, so exactly one internal node is
#    tossed (a genuine, non-degenerate prune).
# ---------------------------------------------------------------------------

def test_prune_anova_mid_cp_matches_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=0.1)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=0.1)

    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 2. method="class" (kyphosis): a classification tree, mid-range cp.
# ---------------------------------------------------------------------------

def test_prune_classification_mid_cp_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=0.02)

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=0.02)

    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 3. method="poisson" (Surv()-style two-column response, stagec dataset): a
#    deeper tree (9 splits at cp=0.001), pruned at a mid-range cp so several
#    (but not all) internal nodes are tossed -- exercises the multi-level
#    descendant-expansion logic in snip_rpart more thoroughly than a
#    single-toss prune would.
# ---------------------------------------------------------------------------

def _stagec_prebuilt_model_frame(df: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    m = df[predictors].copy()
    m.attrs["terms"] = {
        "order": [1] * len(predictors),
        "term.labels": predictors,
        "variables": ["Surv_response"] + predictors,
        "response": 1,
        "xlevels": {"ploidy": list(df["ploidy"].cat.categories)},
    }
    m.attrs["response"] = np.column_stack(
        [df["pgtime"].to_numpy(dtype=float), df["pgstat"].to_numpy(dtype=float)]
    )
    return m


def test_prune_poisson_deep_tree_mid_cp_matches_r_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.001))'
    )
    r_pruned = r_prune(r_fit, cp=0.02)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.001},
    )
    py_pruned = prune(py_fit, cp=0.02)

    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 4. Categorical predictors + surrogate splits (cu.summary, maxsurrogate=3):
#    several frame rows have nsurrogate > 0 and ncompete > 0, and some
#    splits are categorical (csplit-backed). Pruning here exercises
#    snip_rpart's csplit re-indexing (`x['csplit'] = x['csplit'][...]`) and
#    the surrogate-aware `importance()` recomputation, not just the plain
#    numeric-split path the other tests above cover.
# ---------------------------------------------------------------------------

def test_prune_categorical_with_surrogates_matches_r_cu_summary():
    from _r_rpart_helpers import cu_summary_df

    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Reliability ~ Price + Country + Mileage + Type",
        control="rpart.control(xval=0, cp=0.001, maxsurrogate=3)",
    )
    r_pruned = r_prune(r_fit, cp=0.06)

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type",
        data=df,
        method="class",
        control={"xval": 0, "cp": 0.001, "maxsurrogate": 3},
    )
    py_pruned = prune(py_fit, cp=0.06)

    ## Sanity: the unpruned fit really does have surrogate/competitor splits,
    ## so this test isn't accidentally degenerate.
    assert (py_fit["frame"]["nsurrogate"] > 0).any()
    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 5. cp exactly equal to one of the cptable's own CP values (rather than a
#    value strictly between two rows): exercises the `>= cp` boundary
#    condition in `ff$complexity <= cp` exactly (a node whose complexity
#    equals cp precisely must be tossed, not retained).
# ---------------------------------------------------------------------------

def test_prune_cp_exactly_matches_a_cptable_row_value():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_cptable = np.asarray(r_fit.rx2("cptable"))
    boundary_cp = float(r_cptable[1, 0])  # the second row's own CP value

    r_pruned = r_prune(r_fit, cp=boundary_cp)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=boundary_cp)

    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 6. cp so large that the entire tree collapses to its root (cp greater
#    than every internal node's complexity): both sides must produce a
#    single-row frame, a single-row cptable, and no variable.importance.
# ---------------------------------------------------------------------------

def test_prune_large_cp_collapses_to_root_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=1.0)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=1.0)

    assert py_pruned["frame"].shape[0] == 1
    assert py_pruned["frame"]["var"].iloc[0] == "<leaf>"
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 7. cp so small (<= every node's complexity) that no node is tossed at
#    all: prune_rpart's own `if len(toss) == 0: return tree` early-out
#    means the returned object should be numerically identical to the
#    *unpruned* fit (not merely "matches R's pruned result", but literally
#    unchanged), on both sides.
# ---------------------------------------------------------------------------

def test_prune_tiny_cp_is_a_no_op_matches_r():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=0.0)

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=0.0)

    ## no-op: same shape/values as the original, unpruned fit.
    assert py_pruned["frame"].shape[0] == py_fit["frame"].shape[0]
    assert py_pruned["frame"]["var"].tolist() == py_fit["frame"]["var"].tolist()
    _assert_pruned_matches_r(py_pruned, r_pruned)


# ---------------------------------------------------------------------------
# 8. Chained/double pruning: prune(prune(tree, cp=cp1), cp=cp2) with
#    cp2 > cp1. Exercises snip_rpart/prune_rpart composing correctly across
#    repeated application (both sides perform the identical two-step chain
#    independently, then are compared to each other), rather than only ever
#    being applied once to a freshly-fit tree.
# ---------------------------------------------------------------------------

def test_prune_chained_double_prune_matches_r():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.001))'
    )
    r_pruned1 = r_prune(r_fit, cp=0.01)
    r_pruned2 = r_prune(r_pruned1, cp=0.03)

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.001},
    )
    py_pruned1 = prune(py_fit, cp=0.01)
    py_pruned2 = prune(py_pruned1, cp=0.03)

    assert py_pruned2["frame"].shape[0] < py_pruned1["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned2, r_pruned2)


# ---------------------------------------------------------------------------
# 9. Generic-dispatch parity: R's plain `prune(fit, cp=...)` (S3 generic,
#    dispatching to prune.rpart since `class(fit) == "rpart"`) must produce
#    the exact same result as calling `prune.rpart(fit, cp=...)` directly --
#    confirming that using the direct-call form as this suite's standard
#    comparison target (see module docstring) is not silently skipping
#    anything the generic-dispatch route would have changed.
# ---------------------------------------------------------------------------

def test_prune_generic_dispatch_matches_direct_prune_rpart_call():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")

    r_pruned_generic = r_prune(r_fit, generic=True, cp=0.02)
    r_pruned_direct = r_prune(r_fit, generic=False, cp=0.02)

    generic_out = extract_r_fit(r_pruned_generic)
    direct_out = extract_r_fit(r_pruned_direct)
    assert generic_out["var"] == direct_out["var"]
    assert_allclose(generic_out["cptable"], direct_out["cptable"])
    assert_allclose(generic_out["where"], direct_out["where"])

    ## And python's single entry point matches both R call forms equally.
    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=0.02)
    _assert_pruned_matches_r(py_pruned, r_pruned_generic)
    _assert_pruned_matches_r(py_pruned, r_pruned_direct)


# ---------------------------------------------------------------------------
# 10. Numeric (non-factor) response fit with method="class" explicitly (a
#     0/1 integer column rather than a genuine factor) -- exercises the
#     `_ylevels`-less/character-coded-levels construction path together with
#     pruning, mirroring test_printcp_positive.py's analogous coverage for
#     printcp().
# ---------------------------------------------------------------------------

def test_prune_numeric_response_as_class_matches_r_kyphosis():
    df = kyphosis_df().copy()
    df["Kyph01"] = (df["Kyphosis"] == "present").astype(int)
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyph01 ~ Age + Number + Start", method='"class"', control="rpart.control(xval=0, cp=0.001)")
    r_pruned = r_prune(r_fit, cp=0.02)

    py_fit = rpart("Kyph01 ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    py_pruned = prune(py_fit, cp=0.02)

    assert py_pruned["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_pruned_matches_r(py_pruned, r_pruned)

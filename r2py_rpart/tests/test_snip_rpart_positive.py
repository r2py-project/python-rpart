"""Positive-path parity tests for r2py_rpart.snip_rpart vs. R's
rpart::snip.rpart, focused strictly on the non-interactive, programmatically
testable calling convention -- `toss=` supplied explicitly as a vector of
node numbers -- rather than the interactive (mouse-click-driven,
`snip.rpart.mouse`) fallback R uses when `toss` is omitted/empty (which
requires a live graphics device and has no meaningful python-side
equivalent; see test_snip_rpart_negative.py for that path's
immediate-error behavior in a headless session).

snip.rpart(x, toss) is exported directly from the rpart NAMESPACE as a plain
function (not an S3 generic/method pair like prune/prune.rpart), so there is
no generic-vs-direct-call distinction to make: a bare `snip.rpart(...)` R
call always reaches the same body r2py_rpart.snip_rpart() itself
implements -- see tests/_r_rpart_helpers.py's `r_snip`/`r_snip_call_code`
plumbing.

Each test builds an rpart fit independently in both R and Python from the
*same* formula/data/control (xval=0, so tree structure is deterministic and
already known -- from test_rpart_positive.py -- to match between the two
implementations), then calls snip.rpart(fit, toss=...) on both sides and
asserts that the resulting `$frame` (var/complexity/ncompete/nsurrogate/row
ids), `$splits`, `$csplit`, and `$where` all agree. Unlike prune.rpart,
snip.rpart never touches `$cptable`/`$variable.importance` (those are left
untouched, still reflecting the *original*, unsnipped fit) -- so this file's
comparison helper deliberately omits those two fields, unlike
test_prune_positive.py's/test_prune_rpart_positive.py's analogous helpers.

See tests/_r_rpart_helpers.py for the shared rpy2 plumbing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from r2py_rpart import rpart
from r2py_rpart.snip_rpart import snip_rpart

from _r_rpart_helpers import (
    CU_RELIABILITY_LEVELS,
    cu_summary_df,
    extract_r_fit,
    kyphosis_df,
    mtcars_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_snip,
    run_r,
    stagec_df,
)


def _assert_snip_matches_r(py_snipped: dict, r_snipped) -> None:
    """Assert that a python-snipped fit dict and an R-snipped rpart object
    (raw rpy2 result of `snip.rpart(...)`) agree on every field
    snip.rpart.R actually recomputes or carries over: `$frame`
    (var/complexity/ncompete/nsurrogate, and its row names/node ids),
    `$splits`, `$csplit`, and `$where`. Deliberately does NOT compare
    `$cptable`/`$variable.importance` -- snip.rpart never touches either."""
    r_out = extract_r_fit(r_snipped)

    py_frame = py_snipped["frame"]
    assert py_frame["var"].tolist() == r_out["var"]
    assert_allclose(py_frame.index.to_numpy(dtype=float), r_out["frame_index"].astype(float))
    assert_allclose(py_frame["complexity"].to_numpy(), r_out["complexity"], rtol=1e-6, atol=1e-8)
    assert_allclose(py_frame["ncompete"].to_numpy(), r_out["ncompete"])
    assert_allclose(py_frame["nsurrogate"].to_numpy(), r_out["nsurrogate"])

    assert_allclose(np.asarray(py_snipped["where"], dtype=float), r_out["where"])

    py_splits = py_snipped.get("splits")
    r_splits = r_out["splits"]
    if r_splits is None or r_splits.shape[0] == 0:
        assert py_splits is None or len(py_splits) == 0
    else:
        assert py_splits is not None
        assert len(py_splits) == r_splits.shape[0]
        assert_allclose(py_splits.to_numpy(dtype=float), r_splits, rtol=1e-6, atol=1e-8)

    py_csplit = py_snipped.get("csplit")
    r_csplit = r_out["csplit"]
    if r_csplit is None:
        assert py_csplit is None
    else:
        assert py_csplit is not None
        assert_allclose(np.asarray(py_csplit, dtype=float), r_csplit, rtol=1e-6, atol=1e-8)


# ---------------------------------------------------------------------------
# 1. Single internal node tossed (method="anova", mtcars): the simplest
#    genuine, non-degenerate snip -- one whole subtree removed, becoming a
#    single new leaf.
# ---------------------------------------------------------------------------

def test_snip_single_internal_node_matches_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    toss_node = int(py_fit["frame"].index[py_fit["frame"]["var"] != "<leaf>"][0])

    r_snipped = r_snip(r_fit, [toss_node])
    py_snipped = snip_rpart(py_fit, [toss_node])

    assert py_snipped["frame"].shape[0] < py_fit["frame"].shape[0]
    _assert_snip_matches_r(py_snipped, r_snipped)


# ---------------------------------------------------------------------------
# 2. Multiple, non-overlapping nodes tossed at once (method="class",
#    kyphosis): exercises `toss` as a multi-element list spanning two
#    distinct subtrees in one call.
# ---------------------------------------------------------------------------

def test_snip_multiple_nonoverlapping_nodes_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    internal = py_fit["frame"].index[py_fit["frame"]["var"] != "<leaf>"].tolist()
    assert len(internal) >= 2
    toss_nodes = [int(internal[0]), int(internal[-1])]

    r_snipped = r_snip(r_fit, toss_nodes)
    py_snipped = snip_rpart(py_fit, toss_nodes)

    _assert_snip_matches_r(py_snipped, r_snipped)


# ---------------------------------------------------------------------------
# 3. Redundant descendant explicitly included in `toss` alongside its own
#    ancestor (`toss=[node, child_of_node]`): snip_rpart's own descendant-
#    expansion logic already adds every descendant of a tossed node
#    automatically, so explicitly listing one too must be idempotent --
#    matches R's identical `unique(toss)` + expansion-loop behavior exactly.
# ---------------------------------------------------------------------------

def test_snip_redundant_descendant_in_toss_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    frame = py_fit["frame"]
    internal = frame.index[frame["var"] != "<leaf>"].tolist()
    node = int(internal[0])
    child = node * 2
    assert child in frame.index

    r_snipped_redundant = r_snip(r_fit, [node, child])
    py_snipped_redundant = snip_rpart(py_fit, [node, child])
    py_snipped_plain = snip_rpart(py_fit, [node])

    ## Explicitly including the descendant changes nothing vs. tossing just
    ## the ancestor alone.
    assert py_snipped_redundant["frame"]["var"].tolist() == py_snipped_plain["frame"]["var"].tolist()
    assert py_snipped_redundant["frame"].index.tolist() == py_snipped_plain["frame"].index.tolist()
    _assert_snip_matches_r(py_snipped_redundant, r_snipped_redundant)


# ---------------------------------------------------------------------------
# 4. Categorical predictors + surrogate splits (cu.summary, maxsurrogate=3):
#    tossing a node whose split (and competitor/surrogate splits) are
#    categorical (csplit-backed) exercises snip_rpart's csplit re-indexing
#    (`x['csplit'] = x['csplit'][...]` + re-numbering the `index` column of
#    the surviving `splits` rows), not just the plain numeric-split path the
#    other tests here cover.
# ---------------------------------------------------------------------------

def test_snip_categorical_csplit_reindex_matches_r_cu_summary():
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart(
        "Reliability ~ Price + Country + Mileage + Type",
        control="rpart.control(xval=0, cp=0.001, maxsurrogate=3)",
    )

    py_fit = rpart(
        "Reliability ~ Price + Country + Mileage + Type",
        data=df,
        method="class",
        control={"xval": 0, "cp": 0.001, "maxsurrogate": 3},
    )
    frame = py_fit["frame"]
    ## Sanity: the unpruned fit really does have categorical (ncat > 1)
    ## splits backed by csplit, so this test isn't accidentally degenerate.
    assert py_fit["csplit"] is not None and py_fit["csplit"].shape[0] > 0
    ## Node 5 (var="Type", ncompete=3, nsurrogate=2 per direct inspection) is
    ## an internal node with categorical competing/surrogate splits.
    toss_node = int(frame.index[frame["nsurrogate"] > 0][0])

    r_snipped = r_snip(r_fit, [toss_node])
    py_snipped = snip_rpart(py_fit, [toss_node])

    assert py_snipped["frame"].shape[0] < frame.shape[0]
    _assert_snip_matches_r(py_snipped, r_snipped)


# ---------------------------------------------------------------------------
# 5. Tossing the root node (`toss=[1]`) collapses the *entire* tree down to
#    a single-row, leaf-only frame -- every other node is a descendant of
#    the root, so the descendant-expansion loop sweeps in all of them.
# ---------------------------------------------------------------------------

def test_snip_root_node_collapses_to_single_leaf_matches_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    r_snipped = r_snip(r_fit, [1])
    py_snipped = snip_rpart(py_fit, [1])

    assert py_snipped["frame"].shape[0] == 1
    assert py_snipped["frame"]["var"].iloc[0] == "<leaf>"
    _assert_snip_matches_r(py_snipped, r_snipped)


# ---------------------------------------------------------------------------
# 6. Tossing an already-terminal (leaf) node is a no-op: the leaf has no
#    descendants to expand into, and it was already `var == "<leaf>"`
#    (nothing for the newleaf-marking step to actually change) -- the
#    resulting frame is identical to the original, unsnipped fit.
# ---------------------------------------------------------------------------

def test_snip_leaf_node_is_a_no_op_matches_r_kyphosis():
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Kyphosis ~ Age + Number + Start", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", control={"xval": 0, "cp": 0.001})
    frame = py_fit["frame"]
    leaf_node = int(frame.index[frame["var"] == "<leaf>"][0])

    r_snipped = r_snip(r_fit, [leaf_node])
    py_snipped = snip_rpart(py_fit, [leaf_node])

    assert py_snipped["frame"].shape[0] == frame.shape[0]
    assert py_snipped["frame"]["var"].tolist() == frame["var"].tolist()
    _assert_snip_matches_r(py_snipped, r_snipped)


# ---------------------------------------------------------------------------
# 7. `toss` supplied as a numpy array rather than a plain python list --
#    must produce byte-for-byte the same result as the equivalent list, and
#    still match R.
# ---------------------------------------------------------------------------

def test_snip_toss_as_numpy_array_matches_list_and_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    toss_node = int(py_fit["frame"].index[py_fit["frame"]["var"] != "<leaf>"][0])

    r_snipped = r_snip(r_fit, [toss_node])
    py_snipped_list = snip_rpart(py_fit, [toss_node])
    py_snipped_array = snip_rpart(py_fit, np.array([toss_node], dtype=np.int64))

    assert py_snipped_array["frame"]["var"].tolist() == py_snipped_list["frame"]["var"].tolist()
    assert py_snipped_array["frame"].index.tolist() == py_snipped_list["frame"].index.tolist()
    _assert_snip_matches_r(py_snipped_array, r_snipped)


# ---------------------------------------------------------------------------
# 8. `toss` supplied as other common python container/array-like types --
#    a plain tuple and a pandas Series of node numbers -- both of which
#    `np.array(toss, dtype=np.int64)` accepts transparently; each must agree
#    with the plain-list result and with R.
# ---------------------------------------------------------------------------

def test_snip_toss_as_tuple_and_pandas_series_match_r_mtcars():
    df = mtcars_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("mpg ~ wt + hp + disp + cyl", control="rpart.control(xval=0, cp=0.001)")

    py_fit = rpart("mpg ~ wt + hp + disp + cyl", data=df, method="anova", control={"xval": 0, "cp": 0.001})
    internal = py_fit["frame"].index[py_fit["frame"]["var"] != "<leaf>"].tolist()
    toss_nodes = [int(internal[0]), int(internal[-1])]

    r_snipped = r_snip(r_fit, toss_nodes)
    py_snipped_list = snip_rpart(py_fit, toss_nodes)
    py_snipped_tuple = snip_rpart(py_fit, tuple(toss_nodes))
    py_snipped_series = snip_rpart(py_fit, pd.Series(toss_nodes))

    for py_snipped in (py_snipped_tuple, py_snipped_series):
        assert py_snipped["frame"]["var"].tolist() == py_snipped_list["frame"]["var"].tolist()
        assert py_snipped["frame"].index.tolist() == py_snipped_list["frame"].index.tolist()
    _assert_snip_matches_r(py_snipped_list, r_snipped)


# ---------------------------------------------------------------------------
# 9. Deeper tree (method="poisson", Surv()-style two-column response,
#    stagec dataset), tossing two separate internal nodes at different
#    depths in one call -- exercises the multi-level descendant-expansion
#    logic (the `while (any(id2 > 1))`/`while np.any(id2 > 1)` loop) more
#    thoroughly than a single, shallow toss would.
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


def test_snip_two_internal_nodes_deep_tree_matches_r_stagec():
    df = stagec_df()
    predictors = ["age", "eet", "g2", "grade", "gleason", "ploidy"]

    r_dataframe_assign("df", df)
    run_r('df$ploidy <- factor(df$ploidy)')
    r_fit = run_r(
        "rpart(Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy, data=df, "
        'method="poisson", control=rpart.control(xval=0, maxsurrogate=0, cp=0.001))'
    )

    m = _stagec_prebuilt_model_frame(df, predictors)
    py_fit = rpart(
        "Surv(pgtime, pgstat) ~ age + eet + g2 + grade + gleason + ploidy",
        model=m,
        method="poisson",
        control={"xval": 0, "maxsurrogate": 0, "cp": 0.001},
    )
    frame = py_fit["frame"]
    internal = frame.index[frame["var"] != "<leaf>"].tolist()
    assert len(internal) >= 3
    ## Two internal nodes, from different parts of the tree, neither an
    ## ancestor/descendant of the other.
    toss_nodes = [int(internal[0]), int(internal[len(internal) // 2])]

    r_snipped = r_snip(r_fit, toss_nodes)
    py_snipped = snip_rpart(py_fit, toss_nodes)

    assert py_snipped["frame"].shape[0] < frame.shape[0]
    _assert_snip_matches_r(py_snipped, r_snipped)

"""Boundary/edge-case parity tests for r2py_rpart.path_rpart vs. R's
`path.rpart`.

See test_path_rpart_positive.py's module docstring for the shared
comparison strategy (calling R's exported `path.rpart(fit, ...)` directly
and r2py_rpart's `path_rpart(fit, ...)` on the *same* fitted model, both
restricted to the non-interactive `nodes=`-supplied branch) and
test_path_rpart_negative.py's for the malformed-`tree` convention.

This file targets genuine boundary conditions of path.rpart's own node-
selection/matching logic (`node.match()`/`descendants()`, shared with
prune.rpart/snip.rpart -- see `rpart/R/zzz.R`):

  - the smallest possible tree (`n == 1L`, root-only, `cp=1`);
  - the smallest possible *non-root-only* tree (exactly 3 frame rows);
  - `nodes=` containing *some* invalid node ids mixed with valid ones
    (partial match -- a warning, not an error, from `node.match()`);
  - `nodes=` where *every* supplied id is invalid -- R's
    `node.match()` returns a length-0 vector and path.rpart
    short-circuits to `return(invisible())` (plain `NULL`), a genuine,
    permanent divergence from r2py_rpart.path_rpart()'s own `{}` in that
    same scenario, pinned here as a KNOWN GAP;
  - `nodes=` as an empty vector/list (no warning on either side, but the
    same NULL-vs-`{}` KNOWN GAP as above);
  - extreme numeric node ids (very large integers, non-integer/fractional
    values) that can never match any real node -- confirming the
    "not in this tree" warning path is numerically robust on both sides,
    while also pinning a permanent, cosmetic-only numeric-formatting
    difference in the warning text itself for very large values (R's
    scientific-notation "1e+12" vs. python's plain "1000000000000") as a
    KNOWN GAP.
"""
from __future__ import annotations

import warnings

import numpy as np

from r2py_rpart import rpart
from r2py_rpart.path_rpart import path_rpart

from _r_rpart_helpers import (
    kyphosis_df,
    r_dataframe_assign,
    r_eval_capturing_warning,
    r_fit_rpart,
    r_path_rpart,
    r_path_rpart_call_code,
    r_path_rpart_to_python,
)


def _kyphosis_fits(**control):
    df = kyphosis_df()
    r_dataframe_assign("df", df)
    fit_kwargs = {"control": control} if control else {}
    fit = rpart("Kyphosis ~ Age + Number + Start", data=df, method="class", **fit_kwargs)
    ctrl_expr = None
    if control:
        ctrl_items = ", ".join(f"{k}={v}" for k, v in control.items())
        ctrl_expr = f"rpart.control({ctrl_items})"
    r_fit = r_fit_rpart(
        "Kyphosis ~ Age + Number + Start", method='"class"',
        **({"control": ctrl_expr} if ctrl_expr else {}),
    )
    return fit, r_fit


def _capture_warning_for_path_call(r_fit, **kwargs):
    """Run r_path_rpart_call_code(...)'s R source through
    r_eval_capturing_warning(), against an already-globalenv-assigned
    `path_fit_tmp`, returning (result-or-None, warning-message-or-None)."""
    import rpy2.robjects as ro

    ro.globalenv["path_fit_tmp"] = r_fit
    call_code = r_path_rpart_call_code("path_fit_tmp", **kwargs)
    code = f"path_rpart_result_tmp <- {call_code}\npath_rpart_result_tmp"
    result, warning_msg = r_eval_capturing_warning(code)
    return result, warning_msg


# ---------------------------------------------------------------------------
# 1. The smallest possible tree: `n == 1L`, root-only (forced via `cp=1`).
# ---------------------------------------------------------------------------

def test_path_rpart_root_only_tree_single_valid_node():
    fit, r_fit = _kyphosis_fits(cp=1)
    assert fit["frame"].shape[0] == 1
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=[1], **{"print.it": False}))
    py_res = path_rpart(fit, nodes=[1], print_it=False)
    assert py_res == r_res == {"1": ["root"]}


def test_path_rpart_root_only_tree_invalid_node_warns_and_returns_empty():
    """On a root-only tree, node 2 does not exist -- both sides warn
    ("supplied nodes 2 are not in this tree") and return an empty result
    (R: NULL: python: `{}`, per the NULL-vs-`{}` KNOWN GAP documented at
    module level)."""
    fit, r_fit = _kyphosis_fits(cp=1)
    r_res, r_warning = _capture_warning_for_path_call(r_fit, nodes=[2], **{"print.it": False})
    assert r_warning == "supplied nodes 2 are not in this tree"
    assert r_path_rpart_to_python(r_res) is None  # R: NULL

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[2], print_it=False)
    assert len(caught) == 1
    assert str(caught[0].message) == r_warning
    assert py_res == {}  # python: {} (KNOWN GAP vs. R's NULL)


# ---------------------------------------------------------------------------
# 2. The smallest possible *non-root-only* tree: exactly 3 frame rows
#    (root + 2 leaves), forced via maxdepth=1.
# ---------------------------------------------------------------------------

def test_path_rpart_minimal_three_row_tree_all_nodes():
    fit, r_fit = _kyphosis_fits(maxdepth=1)
    assert fit["frame"].shape[0] == 3
    node_ids = fit["frame"].index.tolist()
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=node_ids, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=node_ids, print_it=False)
    assert py_res == r_res
    assert py_res[str(node_ids[0])] == ["root"]
    # Each of the two leaves' own path is exactly ["root", <one split>].
    for leaf_id in node_ids[1:]:
        assert len(py_res[str(leaf_id)]) == 2


# ---------------------------------------------------------------------------
# 3. Partial node match: some supplied node ids are valid, some are not --
#    a warning naming only the bad ones, with the valid ones' paths still
#    returned.
# ---------------------------------------------------------------------------

def test_path_rpart_partial_invalid_nodes_warns_and_returns_valid_subset():
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[999, 11], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 999 are not in this tree"
    r_dict = r_path_rpart_to_python(r_res)
    assert r_dict == {"11": r_dict["11"]}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[999, 11], print_it=False)
    assert len(caught) == 1
    assert str(caught[0].message) == r_warning
    assert py_res == r_dict


def test_path_rpart_multiple_invalid_nodes_warns_with_all_bad_ids_listed():
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[999, 888, 11], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 999,888 are not in this tree"
    r_dict = r_path_rpart_to_python(r_res)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[999, 888, 11], print_it=False)
    assert str(caught[0].message) == r_warning
    assert py_res == r_dict


# ---------------------------------------------------------------------------
# 4. Every supplied node invalid -- R's node.match() returns a length-0
#    vector, path.rpart short-circuits to `return(invisible())` (plain
#    NULL); r2py_rpart.path_rpart() instead returns `{}`. Both sides still
#    warn identically.
# ---------------------------------------------------------------------------

def test_path_rpart_all_nodes_invalid_is_a_known_gap():
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[999, 888], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 999,888 are not in this tree"
    assert r_path_rpart_to_python(r_res) is None  # R: NULL (KNOWN GAP)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[999, 888], print_it=False)
    assert str(caught[0].message) == r_warning
    assert py_res == {}  # python: {} (KNOWN GAP vs. R's NULL)


# ---------------------------------------------------------------------------
# 5. nodes= as an empty vector/list -- no warning on either side (R's
#    `bad <- nodes[node.index == 0L]` is itself `numeric(0)`, so
#    `length(bad) > 0` is FALSE), but the same NULL-vs-`{}` KNOWN GAP.
# ---------------------------------------------------------------------------

def test_path_rpart_empty_nodes_list_is_a_known_gap():
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(r_fit, nodes=[], **{"print.it": False})
    assert r_warning is None  # R: no warning
    assert r_path_rpart_to_python(r_res) is None  # R: NULL (KNOWN GAP)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[], print_it=False)
    assert len(caught) == 0  # python: no warning either
    assert py_res == {}  # python: {} (KNOWN GAP vs. R's NULL)


def test_path_rpart_empty_nodes_numpy_array():
    """The same empty-`nodes=` scenario, but as an (empty) numpy array
    rather than a python list -- confirms `np.asarray([])`'s default
    float64 dtype does not upset `node_match()`'s int-keyed lookup dict."""
    fit, r_fit = _kyphosis_fits()
    py_res = path_rpart(fit, nodes=np.array([]), print_it=False)
    assert py_res == {}


# ---------------------------------------------------------------------------
# 6. Extreme numeric node ids that can never match any real node: a very
#    large integer (both sides warn, but the warning *text* itself diverges
#    -- R's scientific notation vs. python's plain decimal, a permanent
#    cosmetic-only KNOWN GAP) and a fractional (non-integer) value (which
#    matches on *content*, since no real node id is ever fractional).
# ---------------------------------------------------------------------------

def test_path_rpart_very_large_node_id_warning_text_is_a_known_gap():
    fit, r_fit = _kyphosis_fits()
    big = 1_000_000_000_000
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[big], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 1e+12 are not in this tree"  # R: scientific notation
    assert r_path_rpart_to_python(r_res) is None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[big], print_it=False)
    assert str(caught[0].message) == f"supplied nodes {big} are not in this tree"  # python: plain decimal
    assert str(caught[0].message) != r_warning  # KNOWN GAP: text differs
    assert py_res == {}


def test_path_rpart_fractional_node_id_never_matches():
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[11.5], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 11.5 are not in this tree"
    assert r_path_rpart_to_python(r_res) is None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[11.5], print_it=False)
    assert str(caught[0].message) == r_warning
    assert py_res == {}


def test_path_rpart_negative_node_id_never_matches():
    """Negative node ids are likewise never valid (rpart's own node
    numbering is always positive) -- both sides warn identically and
    return an empty result."""
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[-1], **{"print.it": False}
    )
    assert r_warning == "supplied nodes -1 are not in this tree"
    assert r_path_rpart_to_python(r_res) is None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[-1], print_it=False)
    assert str(caught[0].message) == r_warning
    assert py_res == {}


def test_path_rpart_zero_node_id_never_matches():
    """Node id 0 is likewise never a valid rpart node (numbering starts at
    1, the root)."""
    fit, r_fit = _kyphosis_fits()
    r_res, r_warning = _capture_warning_for_path_call(
        r_fit, nodes=[0], **{"print.it": False}
    )
    assert r_warning == "supplied nodes 0 are not in this tree"
    assert r_path_rpart_to_python(r_res) is None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        py_res = path_rpart(fit, nodes=[0], print_it=False)
    assert str(caught[0].message) == r_warning
    assert py_res == {}

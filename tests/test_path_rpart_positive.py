"""Positive-path parity tests for r2py_rpart.path_rpart vs. R's
`path.rpart` (exported directly from rpart's NAMESPACE, a plain function
rather than an S3 generic -- see
`/groups/jli9/Yufei/python-rpart/rpart/man/path.rpart.Rd` and
`/groups/jli9/Yufei/python-rpart/rpart/R/path.rpart.R`).

path_rpart(tree, nodes=None, pretty=0, print_it=True) reduces to a pure
function of an already-fitted model's `frame` (via `descendants()`/
`node_match()` from `r2py_rpart.zzz`) and `labels_rpart(tree,
pretty=pretty)`'s own split labels, *only* when `nodes` is explicitly
supplied -- the `nodes is None` branch is R's interactive,
mouse-driven-graphics `identify()` code path, which r2py_rpart.path_rpart()
itself stubs out as a no-op (its own module comment: "identify() is
interactive R graphics; stub returns empty list so the while loop never
runs") and which cannot be driven headlessly from R either (confirmed in
test_path_rpart_negative.py/test_path_rpart_edge.py: R's own `rpartco(tree)`
immediately raises without a prior `plot()` call on the current graphics
device). So this whole suite -- per this task's own scope -- exercises only
the non-interactive, `nodes=`-supplied branch.

See tests/_r_rpart_helpers.py's "path.rpart-specific plumbing" section for
the shared machinery used throughout:

  - `r_path_rpart(fit, **kwargs)` -- calls R's `path.rpart(fit, ...)`
    directly (path.rpart is exported, not an S3 method, so no `rpart:::`
    triple-colon trick is needed) and returns the raw rpy2 result. Passing
    the literal python `None` for `pretty=` renders as R's `pretty=NULL`
    (one of labels.rpart's three documented `pretty=` values); to omit an
    argument entirely (letting R's own `missing()` resolve it), use the
    `_PATH_RPART_OMIT` sentinel instead -- see its own docstring.
  - `r_path_rpart_to_python(robj)` -- converts that result into a plain
    `dict[str, list[str]]` (or python `None` for R's actual `NULL`),
    directly comparable to r2py_rpart.path_rpart()'s own return value.
  - `r_path_rpart_lines_and_result(fit, **kwargs)` /
    `capture_path_rpart_lines_and_result(capsys, tree, **kwargs)` -- capture
    both the `print.it=TRUE` printed console output (as a list of lines)
    and the returned dict, on the R and python sides respectively.

Every one of path_rpart's own parameters -- nodes= (as a list, a numpy
array, in-order/out-of-order, with duplicates), pretty= (all four
documented values), and print_it= -- is exercised below, across
continuous-only (kyphosis: classification; car.test.frame: regression) and
categorical (cu.summary: multi-level unordered-factor `Country`/`Type`
splits, exercising labels_rpart's `=`-prefixed level-set labels) model
shapes, established via each implementation's own `rpart(...)` fit on
identical data/formula (relying on both choosing the identical tree
structure for identical inputs, as already established throughout this
test suite -- see e.g. test_labels_rpart_positive.py's module docstring).
"""
from __future__ import annotations

import numpy as np

from r2py_rpart import rpart
from r2py_rpart.path_rpart import path_rpart

from _r_rpart_helpers import (
    cu_summary_df,
    from_r_dataframe,
    kyphosis_df,
    r_dataframe_assign,
    r_fit_rpart,
    r_path_rpart,
    r_path_rpart_lines_and_result,
    r_path_rpart_to_python,
    capture_path_rpart_lines_and_result,
    run_r,
)


def _kyphosis_fits(**control):
    """Continuous-only classification tree (Age/Number/Start)."""
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


def _car_test_frame_fits():
    """Continuous-only regression tree (Mileage ~ Weight); `xval=0` keeps
    the fit deterministic."""
    run_r("data(car.test.frame)")
    df = from_r_dataframe("car.test.frame")
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Mileage ~ Weight", control="rpart.control(xval=0)")
    fit = rpart("Mileage ~ Weight", data=df, method="anova", control={"xval": 0})
    return fit, r_fit


def _cu_summary_fits():
    """Classification tree with multi-level unordered-factor categorical
    predictors (`Country`/`Type`) as primary splits -- exercises
    path_rpart's dependence on labels_rpart's categorical-split (`=`-
    prefixed) branch."""
    df = cu_summary_df()
    r_dataframe_assign("df", df)
    r_fit = r_fit_rpart("Reliability ~ Price + Country + Mileage + Type", method='"class"')
    fit = rpart("Reliability ~ Price + Country + Mileage + Type", data=df, method="class")
    return fit, r_fit


# ---------------------------------------------------------------------------
# 1. Default arguments (pretty=0, print_it left at its own default but
#    suppressed for the return-value comparison below), continuous-only
#    predictors, multiple nodes at once -- the path.rpart.Rd worked-example
#    shape (`nodes = c(11, 22)`).
# ---------------------------------------------------------------------------

def test_path_rpart_default_args_continuous_kyphosis_multiple_nodes():
    fit, r_fit = _kyphosis_fits()
    nodes = [11, 22]
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=nodes, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res
    assert set(py_res.keys()) == {"11", "22"}


def test_path_rpart_default_args_continuous_car_test_frame():
    fit, r_fit = _car_test_frame_fits()
    # Use the first non-root non-leaf node and a leaf, from the fit itself.
    node_ids = fit["frame"].index.tolist()
    nodes = node_ids[:3]
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=nodes, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res


# ---------------------------------------------------------------------------
# 2. Default arguments, categorical predictors (Country/Type) -- confirms
#    path_rpart correctly threads pretty= through to labels_rpart's
#    categorical-split ("=" prefixed) branch.
# ---------------------------------------------------------------------------

def test_path_rpart_default_args_categorical_cu_summary():
    fit, r_fit = _cu_summary_fits()
    node_ids = fit["frame"].index.tolist()
    nodes = node_ids[:4]
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=nodes, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res
    # Sanity-check this fit actually exercises the categorical branch.
    assert any("=" in lab for path in py_res.values() for lab in path)


# ---------------------------------------------------------------------------
# 3. A single node (root, and a single non-root/non-leaf node) -- the
#    smallest possible `nodes=` input.
# ---------------------------------------------------------------------------

def test_path_rpart_single_root_node():
    fit, r_fit = _kyphosis_fits()
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=[1], **{"print.it": False}))
    py_res = path_rpart(fit, nodes=[1], print_it=False)
    assert py_res == r_res == {"1": ["root"]}


def test_path_rpart_single_non_root_node():
    fit, r_fit = _kyphosis_fits()
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=[11], **{"print.it": False}))
    py_res = path_rpart(fit, nodes=[11], print_it=False)
    assert py_res == r_res
    assert py_res["11"][0] == "root"
    assert len(py_res["11"]) > 1


# ---------------------------------------------------------------------------
# 4. Every node in the tree at once (`nodes=` the full frame index) --
#    confirms path_rpart's ancestor-selection logic agrees with R across
#    every possible target node, not just a hand-picked few.
# ---------------------------------------------------------------------------

def test_path_rpart_all_nodes_in_tree():
    fit, r_fit = _kyphosis_fits()
    node_ids = fit["frame"].index.tolist()
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=node_ids, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=node_ids, print_it=False)
    assert py_res == r_res
    assert set(py_res.keys()) == {str(n) for n in node_ids}
    # The root's own path is always exactly ["root"].
    assert py_res[str(node_ids[0])] == ["root"]


# ---------------------------------------------------------------------------
# 5. pretty=: the four documented compatibility values (0, None -> NULL,
#    True, False), each producing identical output to R's own
#    path.rpart(..., pretty=<value>), on the categorical fit (where pretty
#    actually changes the level-set label text).
# ---------------------------------------------------------------------------

def test_path_rpart_pretty_parameter_values_categorical():
    fit, r_fit = _cu_summary_fits()
    node_ids = fit["frame"].index.tolist()
    nodes = node_ids[:4]
    for pretty in (0, None, True, False):
        r_res = r_path_rpart_to_python(
            r_path_rpart(r_fit, nodes=nodes, pretty=pretty, **{"print.it": False})
        )
        py_res = path_rpart(fit, nodes=nodes, pretty=pretty, print_it=False)
        assert py_res == r_res, f"pretty={pretty}"


def test_path_rpart_pretty_default_matches_pretty_zero():
    fit, r_fit = _cu_summary_fits()
    nodes = fit["frame"].index.tolist()[:4]
    py_default = path_rpart(fit, nodes=nodes, print_it=False)
    py_zero = path_rpart(fit, nodes=nodes, pretty=0, print_it=False)
    assert py_default == py_zero


# ---------------------------------------------------------------------------
# 6. nodes= input type/order variations: a numpy array, a tuple, an
#    out-of-ascending-order list, and a list containing a duplicate node
#    id -- all must match R's own equivalents (R's `node.match`/`match()`
#    likewise tolerate arbitrary order and duplicates).
# ---------------------------------------------------------------------------

def test_path_rpart_nodes_as_numpy_array():
    fit, r_fit = _kyphosis_fits()
    nodes = np.array([11, 22])
    r_res = r_path_rpart_to_python(
        r_path_rpart(r_fit, nodes=nodes.tolist(), **{"print.it": False})
    )
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res


def test_path_rpart_nodes_as_tuple():
    fit, r_fit = _kyphosis_fits()
    nodes = (11, 22)
    r_res = r_path_rpart_to_python(
        r_path_rpart(r_fit, nodes=list(nodes), **{"print.it": False})
    )
    py_res = path_rpart(fit, nodes=list(nodes), print_it=False)
    assert py_res == r_res


def test_path_rpart_nodes_out_of_ascending_order():
    fit, r_fit = _kyphosis_fits()
    node_ids = fit["frame"].index.tolist()
    nodes = list(reversed(node_ids))
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=nodes, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res
    # Order of the `nodes=` argument does not affect the resulting dict's
    # content (only python dict *iteration* order, which is not compared).
    assert py_res == path_rpart(fit, nodes=node_ids, print_it=False)


def test_path_rpart_nodes_with_duplicate_entries():
    fit, r_fit = _kyphosis_fits()
    nodes = [11, 11, 22]
    r_res = r_path_rpart_to_python(r_path_rpart(r_fit, nodes=nodes, **{"print.it": False}))
    py_res = path_rpart(fit, nodes=nodes, print_it=False)
    assert py_res == r_res
    assert set(py_res.keys()) == {"11", "22"}


# ---------------------------------------------------------------------------
# 7. print_it=True: the printed console output (per node: a "node number:"
#    header line followed by indented split labels) must contain the same
#    *content* on both sides -- compared with surrounding whitespace
#    stripped, since R's `cat("\n", "node number:", n[i], "\n")` leaves a
#    trailing space before its newline (from `cat`'s default `sep=" "`)
#    that python's `print(f'\n node number: {n[i]}')` does not reproduce
#    (a permanent, cosmetic-only formatting difference, not a parity bug).
# ---------------------------------------------------------------------------

def test_path_rpart_print_it_true_output_matches_r_content(capsys):
    fit, r_fit = _kyphosis_fits()
    nodes = [1, 11]
    r_lines, r_res = r_path_rpart_lines_and_result(r_fit, nodes=nodes, **{"print.it": True})
    py_lines, py_res = capture_path_rpart_lines_and_result(capsys, fit, nodes=nodes, print_it=True)
    assert py_res == r_res
    r_stripped = [line.strip() for line in r_lines if line.strip() != ""]
    py_stripped = [line.strip() for line in py_lines if line.strip() != ""]
    assert py_stripped == r_stripped


def test_path_rpart_print_it_false_produces_no_output(capsys):
    fit, r_fit = _kyphosis_fits()
    nodes = [1, 11]
    r_lines, r_res = r_path_rpart_lines_and_result(r_fit, nodes=nodes, **{"print.it": False})
    py_lines, py_res = capture_path_rpart_lines_and_result(capsys, fit, nodes=nodes, print_it=False)
    assert r_lines == []
    assert py_lines == []
    assert py_res == r_res


# ---------------------------------------------------------------------------
# 8. Full parameter-combination sweep: nodes/pretty/print_it varied jointly
#    on both a continuous and a categorical fit, comparing only the
#    returned dict (print_it's side effect is exercised in isolation
#    above).
# ---------------------------------------------------------------------------

def test_path_rpart_all_parameter_combinations_continuous():
    fit, r_fit = _kyphosis_fits()
    node_ids = fit["frame"].index.tolist()
    for nodes in ([1], [11, 22], node_ids):
        for pretty in (0, True, False):
            for print_it in (True, False):
                r_res = r_path_rpart_to_python(
                    r_path_rpart(
                        r_fit, nodes=nodes, pretty=pretty, **{"print.it": print_it}
                    )
                )
                py_res = path_rpart(fit, nodes=nodes, pretty=pretty, print_it=print_it)
                assert py_res == r_res, (nodes, pretty, print_it)


def test_path_rpart_all_parameter_combinations_categorical():
    fit, r_fit = _cu_summary_fits()
    node_ids = fit["frame"].index.tolist()
    for nodes in ([1], node_ids[:4]):
        for pretty in (0, None, True, False):
            r_res = r_path_rpart_to_python(
                r_path_rpart(r_fit, nodes=nodes, pretty=pretty, **{"print.it": False})
            )
            py_res = path_rpart(fit, nodes=nodes, pretty=pretty, print_it=False)
            assert py_res == r_res, (nodes, pretty)

from __future__ import annotations

from typing import Any

import numpy as np
import warnings
import unicodedata

# Equivalent of R's rpart_env <- new.env() in zzz.R: a single shared
# namespace used by plot_rpart/rpartco/rpart_branch/snip_rpart_mouse to
# pass per-device plotting parameters between a plot_rpart() call and
# later calls that need the same layout (rpartco, rpart_branch, the
# interactive snip mouse picker). Must be imported (not copied) by those
# modules so they all see the same dict.
rpart_env: dict[str, Any] = {}



def descendants(nodes: np.ndarray[Any, np.dtype[np.int64]], include: bool = True) -> np.ndarray[Any, np.dtype[np.bool_]]:
    n = len(nodes)
    if n == 1:
        return np.ones((1, 1), dtype=bool)
    ind = np.arange(n)
    desc = np.zeros((n, n), dtype=bool)
    if include:
        np.fill_diagonal(desc, True)
    node_lookup = {int(v): i for i, v in enumerate(nodes)}
    parents = np.array([node_lookup.get(int(v) // 2, -1) for v in nodes])
    lev = np.floor(np.log2(nodes)).astype(int)
    desc[0, 1:n] = True
    for i in range(int(lev.max()), 1, -1):
        mask = (lev == i)
        col_idx = ind[mask]
        par_idx = parents[mask]
        valid = par_idx != -1
        if np.any(valid):
            desc[par_idx[valid], col_idx[valid]] = True
        safe_par_idx = np.where(par_idx != -1, par_idx, 0)
        new_parents = parents[safe_par_idx]
        new_parents[par_idx == -1] = -1
        parents[mask] = new_parents
        lev[mask] = i - 1
    return desc


def node_match(nodes: np.ndarray[Any, np.dtype[np.int_]], nodelist: np.ndarray[Any, np.dtype[np.int_]], leaves: np.ndarray[Any, np.dtype[np.bool_]] | None = None, print_it: bool = True) -> np.ndarray[Any, np.dtype[np.int_]]:
    nodes = np.asarray(nodes)
    nodelist = np.asarray(nodelist)
    lookup = {}
    for i, v in enumerate(nodelist):
        if v not in lookup:
            lookup[v] = i + 1
    node_index = np.array([lookup.get(n, 0) for n in nodes], dtype=np.intp)
    bad = nodes[node_index == 0]
    if len(bad) > 0 and print_it:
        bad_str = ",".join(str(x) for x in bad)
        warnings.warn(f"supplied nodes {bad_str} are not in this tree", UserWarning, stacklevel=2)
    good = nodes[node_index > 0]
    if leaves is not None:
        leaves = np.asarray(leaves, dtype=bool)
        found_positions = node_index[node_index > 0]
        leaves_subset = leaves[found_positions - 1]
        if np.any(leaves_subset):
            leaf_str = ",".join(str(x) for x in good[leaves_subset])
            warnings.warn(f"supplied nodes {leaf_str} are leaves", UserWarning, stacklevel=2)
            return found_positions[~leaves_subset]
    return node_index[node_index > 0]


def on_unload(libpath: str) -> None:
    # R's .onUnload hook called library.dynam.unload("rpart", libpath) to unload
    # the compiled shared library when the package namespace was unloaded.
    # In Python, CPython extension modules (.so files loaded via cffi/ctypes) are
    # managed automatically by the interpreter's reference-counting and shutdown
    # sequence, so no explicit unload step is required. This function is a no-op stub.
    pass


def string_bounding_box(s: list[str]) -> dict[str, np.ndarray[Any, np.dtype[np.int_]]]:
    def _display_width(text: str) -> int:
        width = 0
        for ch in text:
            eaw = unicodedata.east_asian_width(ch)
            width += 2 if eaw in ('W', 'F') else 1
        return width
    s2: list[list[str]] = [elem.split('\n') for elem in s]
    rows: np.ndarray[Any, np.dtype[np.int_]] = np.array([len(lines) for lines in s2], dtype=int)
    columns: np.ndarray[Any, np.dtype[np.int_]] = np.array([max(_display_width(line) for line in lines) for lines in s2], dtype=int)
    return {'columns': columns, 'rows': rows}


def tree_depth(nodes: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:
    depth = np.floor(np.log2(nodes) + 1e-7)
    return depth - depth.min()

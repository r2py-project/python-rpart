from __future__ import annotations

from typing import Any

import numpy as np
from collections import defaultdict

from .zzz import rpart_env



def compress(x: np.ndarray[Any, np.dtype[np.float64]], me: int, depth: int, is_leaf: np.ndarray[Any, np.dtype[np.bool_]], nspace: float) -> dict[str, Any]:
    lson = me + 1
    if is_leaf[lson]:
        left = {"left": np.array([x[lson]]), "right": np.array([x[lson]]), "depth": depth + 1, "sons": np.array([lson])}
    else:
        left = compress(x, me + 1, depth + 1, is_leaf, nspace)
        x = left["x"]

    rson = me + 1 + len(left["sons"])  # index of right son
    if is_leaf[rson]:
        right = {"left": np.array([x[rson]]), "right": np.array([x[rson]]), "depth": depth + 1, "sons": np.array([rson])}
    else:
        right = compress(x, rson, depth + 1, is_leaf, nspace)
        x = right["x"]

    maxd = max(left["depth"], right["depth"]) - depth
    mind = min(left["depth"], right["depth"]) - depth

    # Find the smallest distance between the two subtrees
    #   But only over depths that they have in common
    # 1 is a minimum distance allowed
    # R's right$left[1L:mind] and left$right[1L:mind] are 1-based inclusive -> Python [0:mind]
    slide = np.min(right["left"][0:mind] - left["right"][0:mind]) - 1
    if slide > 0:  # slide the right hand node to the left
        x = x.copy()
        x[right["sons"]] = x[right["sons"]] - slide
        x[me] = (x[right["sons"][0]] + x[left["sons"][0]]) / 2
    else:
        slide = 0

    # report back
    if left["depth"] > right["depth"]:
        templ = left["left"].copy()
        tempr = left["right"].copy()
        tempr[0:mind] = np.maximum(tempr[0:mind], right["right"] - slide)
    else:
        templ = left["left"].copy() - slide
        tempr = right["right"].copy() - slide
        templ[0:mind] = np.minimum(templ[0:mind], left["left"])

    return {
        "x": x,
        "left": np.concatenate([[x[me] - nspace * (x[me] - x[lson])], templ]),
        "right": np.concatenate([[x[me] - nspace * (x[me] - x[rson])], tempr]),
        "depth": maxd + depth,
        "sons": np.concatenate([[me], left["sons"], right["sons"]]),
    }


def rpartco(tree: dict[str, Any], parms: dict[str, Any] | None = None) -> dict[str, np.ndarray[Any, np.dtype[np.float64]]]:
    if parms is None:
        pn = 'device' + str(1)  # dev.cur() equivalent: fixed device id 1
        if pn not in rpart_env:
            raise RuntimeError('no information available on parameters from previous call to plot()')
        parms = rpart_env[pn]

    frame = tree['frame']
    node = frame.index.astype(float).values.astype(int)
    depth = np.floor(np.log2(node) + 1e-7).astype(int)
    depth = depth - depth.min()
    is_leaf = (frame['var'] == '<leaf>').values

    if parms:
        uniform = parms['uniform']
        nspace = parms['nspace']
        minbranch = parms['minbranch']
    else:
        uniform = False
        nspace = -1
        minbranch = 0.3

    # Shared setup used by both uniform and non-uniform paths, and by x-coordinate computation
    n = len(node)
    indices = np.arange(n)
    node_to_idx = {v: i for i, v in enumerate(node)}

    if uniform:
        max_depth = int(np.max(depth))
        y = (1 + max_depth - depth) / max(max_depth, 4)
        y = y.astype(float)
    else:
        # make y - (parent y) = change in deviance
        y = frame['dev'].values.astype(float).copy()
        dev = y.copy()

        # split indices by depth: depth 0, then 1, then ...
        depth_buckets: dict[int, np.ndarray] = {}
        bucket: dict = defaultdict(list)
        for idx, d in zip(indices, depth):
            bucket[d].append(idx)
        depth_buckets = {d: np.array(v) for d, v in sorted(bucket.items())}
        depth_levels = sorted(depth_buckets.keys())

        # build parent and sibling index arrays (0-based)
        parent = np.array([node_to_idx.get(node[i] // 2, -1) for i in range(n)])
        sibling_node = np.where(node % 2 == 1, node - 1, node + 1)
        sibling = np.array([node_to_idx.get(s, -1) for s in sibling_node])

        # first pass: assign depths (raw deviance differences)
        for d in depth_levels[1:]:
            i = depth_buckets[d]
            temp2 = dev[parent[i]] - (dev[i] + dev[sibling[i]])
            y[i] = y[parent[i]] - temp2

        fudge = minbranch * (np.max(y) - np.min(y)) / max(int(np.max(depth)), 1)

        # second pass: apply fudge factor
        for d in depth_levels[1:]:
            i = depth_buckets[d]
            temp2 = dev[parent[i]] - (dev[i] + dev[sibling[i]])
            haskids = ~(is_leaf[i] & is_leaf[sibling[i]])
            branch_length = np.where(temp2 <= fudge, np.where(haskids, fudge, temp2), temp2)
            y[i] = y[parent[i]] - branch_length

        y = y / np.max(y)

    # Compute x coordinates: space out leaves then fill in interior nodes
    x = np.zeros(n, dtype=float)
    x[is_leaf] = np.arange(1, int(is_leaf.sum()) + 1, dtype=float)

    left_child = np.array([node_to_idx.get(node[i] * 2, -1) for i in range(n)])
    right_child = np.array([node_to_idx.get(node[i] * 2 + 1, -1) for i in range(n)])

    # temp: non-leaf indices grouped by depth, iterate deepest first
    non_leaf_mask = ~is_leaf
    non_leaf_indices = indices[non_leaf_mask]
    non_leaf_depths = depth[non_leaf_mask]
    nl_bucket: dict = defaultdict(list)
    for idx, d in zip(non_leaf_indices, non_leaf_depths):
        nl_bucket[d].append(idx)
    nl_depth_buckets = {d: np.array(v) for d, v in sorted(nl_bucket.items())}

    for d in sorted(nl_depth_buckets.keys(), reverse=True):
        i = nl_depth_buckets[d]
        valid = (left_child[i] != -1) & (right_child[i] != -1)
        i_valid = i[valid]
        x[i_valid] = 0.5 * (x[left_child[i_valid]] + x[right_child[i_valid]])

    if nspace < 0:
        return {'x': x, 'y': y}

    result = compress(x, 0, 0, is_leaf, nspace)
    x = result['x']
    return {'x': x, 'y': y}

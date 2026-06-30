from __future__ import annotations

from typing import Any

import numpy as np

from .zzz import rpart_env



def rpart_branch(x: np.ndarray[Any, np.dtype[np.float64]], y: np.ndarray[Any, np.dtype[np.float64]], node: np.ndarray[Any, np.dtype[np.int64]], branch: float | None = None) -> dict[str, np.ndarray[Any, np.dtype[np.float64]]]:
    if branch is None:
        pn = 'device' + str(1)  # dev.cur() equivalent: fixed device id 1
        if pn not in rpart_env:
            raise RuntimeError("no information available on parameters from previous call to plot()")
        parms = rpart_env[pn]
        branch = parms["branch"]
    is_left = (node % 2 == 0)
    node_left = node[is_left]
    node_lookup = {v: i for i, v in enumerate(node)}
    parent = np.array([node_lookup.get(v // 2, -1) for v in node_left])
    sibling = np.array([node_lookup.get(v + 1, -1) for v in node_left])
    temp = (x[sibling] - x[is_left]) * (1 - branch) / 2
    n_left = int(is_left.sum())
    nan_row = np.full((1, n_left), np.nan)
    xx = np.vstack([
        x[is_left].reshape(1, -1),
        (x[is_left] + temp).reshape(1, -1),
        (x[sibling] - temp).reshape(1, -1),
        x[sibling].reshape(1, -1),
        nan_row,
    ])
    yy = np.vstack([
        y[is_left].reshape(1, -1),
        y[parent].reshape(1, -1),
        y[parent].reshape(1, -1),
        y[sibling].reshape(1, -1),
        nan_row,
    ])
    return {"x": xx, "y": yy}

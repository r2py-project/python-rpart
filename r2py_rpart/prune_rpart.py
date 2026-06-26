from __future__ import annotations

from typing import Any

import numpy as np



def prune_rpart(tree: dict[str, Any], cp: float) -> dict[str, Any]:
    ff = tree['frame']
    id = ff.index.astype(int).values
    mask = (ff['complexity'].values <= cp) & (ff['var'].values != '<leaf>')
    toss = id[mask]
    if len(toss) == 0:
        return tree
    newx = snip_rpart(tree, toss)
    temp = np.maximum(tree['cptable'][:, 0], cp)
    seen: dict[float, int] = {}
    first_occ: list[int] = []
    for i, v in enumerate(temp):
        if v not in seen:
            seen[v] = i
            first_occ.append(i)
    keep = np.array(first_occ, dtype=int)
    newx['cptable'] = tree['cptable'][keep, :].copy()
    newx['cptable'][len(keep) - 1, 0] = cp
    newx['variable.importance'] = importance(newx)
    return newx

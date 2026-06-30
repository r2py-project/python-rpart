from __future__ import annotations

from typing import Any

import numpy as np

from .importance import importance
from .snip_rpart import snip_rpart



def prune_rpart(tree: dict[str, Any], cp: float) -> dict[str, Any]:
    ff = tree['frame']
    id = ff.index.astype(int).values
    mask = (ff['complexity'].values <= cp) & (ff['var'].values != '<leaf>')
    toss = id[mask]
    if len(toss) == 0:
        return tree
    newx = snip_rpart(tree, toss)

    # cptable is normally a pandas DataFrame (see rpart.py); fall back to
    # plain ndarray indexing if it ever isn't.
    cptable = tree['cptable']
    is_df = hasattr(cptable, 'to_numpy')
    cptable_arr = cptable.to_numpy() if is_df else cptable

    temp = np.maximum(cptable_arr[:, 0], cp)
    seen: dict[float, int] = {}
    first_occ: list[int] = []
    for i, v in enumerate(temp):
        if v not in seen:
            seen[v] = i
            first_occ.append(i)
    keep = np.array(first_occ, dtype=int)

    if is_df:
        # .iloc preserves the original row labels at the kept positions,
        # matching R's tree$cptable[keep, , drop=FALSE] (which keeps the
        # original rownames rather than renumbering them).
        new_cptable = cptable.iloc[keep, :].copy()
        new_cptable.iloc[-1, 0] = cp
    else:
        new_cptable = cptable_arr[keep, :].copy()
        new_cptable[-1, 0] = cp
    newx['cptable'] = new_cptable
    newx['variable.importance'] = importance(newx)
    return newx

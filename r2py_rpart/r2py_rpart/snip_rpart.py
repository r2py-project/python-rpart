from __future__ import annotations

from typing import Any

import numpy as np
import warnings



def snip_rpart(x: dict[str, Any], toss: np.ndarray[Any, np.dtype[np.int64]] | list[int] | None = None) -> dict[str, Any]:
    if not (isinstance(x, dict) and x.get('__class__') == 'rpart'):
        raise TypeError('Not an "rpart" object')

    if toss is None or len(toss) == 0:
        toss_result = snip_rpart_mouse(x)
        if toss_result is None or len(toss_result) == 0:
            return x
        toss = np.array(toss_result, dtype=np.int64)
    else:
        toss = np.array(toss, dtype=np.int64)

    ff = x['frame']
    id = ff.index.astype(int).values
    ff_n = len(id)
    toss = np.unique(toss)

    # Warn about nodes not in tree: match(toss, id, 0L) -- membership test
    toss_in_id = np.isin(toss, id)
    if not np.all(toss_in_id):
        missing_nodes = toss[~toss_in_id]
        warnings.warn('Nodes %s are not in this tree' % str(missing_nodes))
        toss = toss[toss_in_id]

    # Expand toss to include all descendants
    id2 = id.copy()
    while np.any(id2 > 1):
        id2 = id2 // 2
        xx = np.isin(id2, toss)
        toss = np.concatenate([toss, id[xx]])
        id2[xx] = 0

    # Find which toss elements have their parent also in toss
    # temp == True means parent is in toss (so not a new leaf)
    # temp == False means parent is NOT in toss (so this is a new leaf boundary)
    parent_in_toss = np.isin(toss // 2, toss)
    # newleaf: 0-based row positions in id of the toss nodes whose parent is not in toss
    # match(toss[temp == 0L], id) in R gives 1-based positions; we use 0-based
    new_leaf_nodes = toss[~parent_in_toss]
    # Find 0-based positions of new_leaf_nodes in id
    id_index = {v: i for i, v in enumerate(id)}
    newleaf = np.array([id_index[v] for v in new_leaf_nodes if v in id_index], dtype=int)

    # keepit: 0-based row indices in id that are NOT in toss
    keepit = np.where(~np.isin(id, toss))[0]

    # Build n_split: for each frame row, repeat its 0-based index by the number
    # of splits it contributes (ncompete + nsurrogate + 1 if non-leaf, else 0)
    # R: rep(1L:ff.n, ff$ncompete + ff$nsurrogate + (ff$var != '<leaf>'))
    # In R this is 1-based; we use 0-based arange to match Python keepit
    counts = (ff['ncompete'].values + ff['nsurrogate'].values +
              (ff['var'].values != '<leaf>').astype(int))
    n_split = np.repeat(np.arange(ff_n, dtype=int), counts)

    # Select split rows where n_split index is in keepit
    split_mask = np.isin(n_split, keepit)
    split = x['splits'][split_mask, :]

    # Handle csplit: column index 1 (0-based) is ncat; column index 3 is csplit index
    # R: temp <- split[, 2L] > 1L  (col 2 in R = col 1 in Python)
    if split.shape[0] > 0:
        temp_mask = split[:, 1] > 1
    else:
        temp_mask = np.zeros(0, dtype=bool)

    if np.any(temp_mask):
        # R: x$csplit <- x$csplit[split[temp, 4L], , drop=FALSE]
        # split[temp, 4L] in R is col 4 (1-based) = col 3 (0-based)
        # These are 1-based row indices into csplit in R; convert to 0-based
        csplit_row_indices = split[temp_mask, 3].astype(int) - 1
        x['csplit'] = x['csplit'][csplit_row_indices, :]
        # R: split[temp, 4L] <- 1L:nrow(x$csplit) (re-index csplit references)
        # After subsetting, re-assign 1-based row indices
        nrow_csplit = x['csplit'].shape[0]
        split[temp_mask, 3] = np.arange(1, nrow_csplit + 1, dtype=split.dtype)
    else:
        x['csplit'] = None

    x['splits'] = split

    # Set new leaves' ncompete, nsurrogate to 0 and var to '<leaf>'
    ff['ncompete'].iloc[newleaf] = 0
    ff['nsurrogate'].iloc[newleaf] = 0
    ff['var'].iloc[newleaf] = '<leaf>'

    # Update frame: keep rows at sorted union of keepit and newleaf (0-based)
    sorted_idx = np.sort(np.concatenate([keepit, newleaf]))
    x['frame'] = ff.iloc[sorted_idx]

    # Update where: map old where indices to new frame positions
    # id[x['where']] gives the node IDs for each observation
    id2 = id[x['where']]
    # id3: node IDs in the new frame order
    id3 = id[sorted_idx]
    id3_index = {v: i for i, v in enumerate(id3)}
    temp = np.array([id3_index.get(v, -1) for v in id2], dtype=int)
    while np.any(temp == -1):
        id2[temp == -1] = id2[temp == -1] // 2
        temp = np.array([id3_index.get(v, -1) for v in id2], dtype=int)
    x['where'] = temp

    return x

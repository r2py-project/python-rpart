from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd



def importance(fit: dict) -> pd.Series:
    ff = fit['frame']
    fpri = np.where(ff['var'].values != '<leaf>')[0]
    per_node_count = 1 + ff['ncompete'].values[fpri] + ff['nsurrogate'].values[fpri]
    spri = 1 + np.cumsum(np.concatenate([[0], per_node_count]))
    spri = spri[:len(fpri)]
    spri_py = spri - 1
    nsurr = ff['nsurrogate'].values[fpri]
    sname: list[np.ndarray | None] = [None] * len(fpri)
    sval: list[np.ndarray | None] = [None] * len(fpri)
    splits = fit['splits']
    if isinstance(splits, pd.DataFrame):
        sdim = splits.index.to_numpy().astype(str)
        improve_col = splits['improve'].values
        adj_col = splits['adj'].values
    else:
        raise TypeError('fit["splits"] must be a pandas DataFrame with named index and columns')
    if fit['method'] == 'anova':
        scaled_imp = improve_col[spri_py] * ff['dev'].values[fpri]
    else:
        scaled_imp = improve_col[spri_py]
    for i in range(len(fpri)):
        if nsurr[i] > 0:
            # R: indx <- spri[i] + ncompete[fpri[i]] + seq_len(nsurr[i])  (1-based,
            # offsets 1..nsurr).  spri_py is already spri-1, so the 0-based
            # equivalent keeps the +1..+nsurr offset (NOT 0..nsurr-1, which
            # would shift onto the primary/competitor rows instead of the
            # surrogate rows).
            base_offset = spri_py[i] + ff['ncompete'].values[fpri[i]]
            indx = base_offset + np.arange(1, nsurr[i] + 1)
            sname[i] = sdim[indx]
            sval[i] = scaled_imp[i] * adj_col[indx]
    sval_parts = [v for v in sval if v is not None]
    sname_parts = [v for v in sname if v is not None]
    sval_flat = np.concatenate(sval_parts) if sval_parts else np.array([], dtype=float)
    sname_flat = np.concatenate(sname_parts) if sname_parts else np.array([], dtype=str)
    all_values = np.concatenate([scaled_imp, sval_flat])
    all_keys = np.concatenate([ff['var'].values[fpri].astype(str), sname_flat])
    import_scores = pd.Series(all_values, index=all_keys, dtype=float).groupby(level=0).sum()
    return import_scores.sort_values(ascending=False)

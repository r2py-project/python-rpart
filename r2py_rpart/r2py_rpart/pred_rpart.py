from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy import ndarray



def pred_rpart(fit: dict[str, Any], x: pd.DataFrame) -> ndarray[Any, np.dtype[np.int32]]:
    from r2py_rpart import _pred_rpart_c as _C_pred_rpart
    frame: pd.DataFrame = fit["frame"]
    # Root-only tree: every observation falls in node 1
    if len(frame) == 1:
        result = np.ones(x.shape[0], dtype=np.int32)
        return pd.Series(result, index=x.index, dtype=np.int32).to_numpy()
    # Build frame$index: exclusive prefix sum of per-node split counts
    nc: pd.DataFrame = frame[["ncompete", "nsurrogate"]]
    is_not_leaf: np.ndarray = (frame["var"].to_numpy() != "<leaf>").astype(np.int32)
    per_node: np.ndarray = is_not_leaf + nc["ncompete"].to_numpy(dtype=np.int32) + nc["nsurrogate"].to_numpy(dtype=np.int32)
    # R: 1L + c(0L, cumsum(...))[-(nrow(frame)+1)] -> exclusive prefix sum, 1-based
    frame = frame.copy()
    index_vals: np.ndarray = 1 + np.concatenate([[0], np.cumsum(per_node)])[:-1]
    index_vals = index_vals.astype(np.int32)
    index_vals[frame["var"].to_numpy() == "<leaf>"] = 0
    frame["index"] = index_vals
    # Map split variable names to column positions in x (1-based, as C expects)
    splits = fit["splits"]  # 2D numpy array; row index holds variable names
    if isinstance(splits, pd.DataFrame):
        splits_rownames: list[str] = list(splits.index)
    else:
        splits_rownames = list(getattr(splits, "rownames", []))
    col_index = pd.Index(list(x.columns))
    vnum_0based: np.ndarray = col_index.get_indexer(splits_rownames)
    if np.any(vnum_0based == -1):
        raise ValueError("Tree has variables not found in new data")
    # Convert to 1-based integer positions for the C routine
    vnum_arr: np.ndarray = (vnum_0based + 1).astype(np.int32)
    # Prepare dim arrays
    dimx: np.ndarray = np.array(x.shape, dtype=np.int32)              # [nrow, ncol]
    nnode: int = int(frame.shape[0])                                   # dim(frame)[1L]
    splits_np: np.ndarray = splits if isinstance(splits, np.ndarray) else splits.to_numpy()
    nsplit: int = int(splits_np.shape[0])                              # dim(fit$splits)[1L]
    csplit = fit.get("csplit")  # None or 2D numpy array
    if csplit is None:
        dimc: np.ndarray = np.zeros(2, dtype=np.int32)                 # rep(0L, 2L)
        csplit2: np.ndarray = np.zeros((0, 0), dtype=np.int32)
    else:
        dimc = np.array(csplit.shape, dtype=np.int32)                  # dim(fit$csplit)
        csplit2 = (csplit - 2).astype(np.int32)                        # fit$csplit - 2L
    # row.names(frame) -> integer node IDs
    nnum: np.ndarray = frame.index.to_numpy(dtype=np.int32)            # as.integer(row.names(frame))
    # unlist(frame[, c('n','ncompete','nsurrogate','index')]) col-major
    cols_for_c = ["n", "ncompete", "nsurrogate", "index"]
    nodes2: np.ndarray = frame[cols_for_c].to_numpy(dtype=np.int32).flatten(order="F")
    nodes2_mat: np.ndarray = nodes2.reshape(nnode, 4, order="F")       # nnode x 4 col-major
    # fit$splits as column-major double matrix
    split2: np.ndarray = np.asfortranarray(splits_np, dtype=np.float64)
    # usesurrogate scalar
    usesur: np.ndarray = np.array([int(fit["control"]["usesurrogate"])], dtype=np.int32)
    # Predictor matrix x as column-major double
    xdata2: np.ndarray = np.asfortranarray(x.to_numpy(dtype=np.float64))
    # NA indicator: is.na(x) as int matrix
    xmiss2: np.ndarray = np.asfortranarray(np.isnan(x.to_numpy(dtype=np.float64)).astype(np.int32))
    # Call C extension via the r2py_rpart wrapper
    temp: np.ndarray = _C_pred_rpart(
        dimx,
        nnode,
        nsplit,
        dimc,
        nnum,
        nodes2_mat,
        vnum_arr,
        split2,
        csplit2,
        usesur,
        xdata2,
        xmiss2,
    )
    # Attach row names of x as index (names(temp) <- rownames(x))
    return pd.Series(temp, index=x.index).to_numpy()

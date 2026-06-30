from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd



def _yval2_matrix(frame: pd.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
    # frame['yval2'] is stored as one array per row (see rpart.py's
    # frame["yval2"] = list(np.hstack(...))), so pandas exposes it as a
    # 1-D object-dtype Series; .values would just return that 1-D array
    # of arrays rather than a proper 2-D matrix, so it must go through
    # .tolist() + np.array() to stack the rows.
    return np.array(frame['yval2'].tolist(), dtype=np.float64)


def _naresid(na_action: dict[str, Any] | None, pred: Any) -> Any:
    """Re-insert NA rows removed by na.action, matching R's naresid()."""
    if na_action is None:
        return pred
    dropped = sorted(int(i) for i in na_action.get('indices', []))
    if not dropped:
        return pred
    n_kept = len(pred)
    n_total = n_kept + len(dropped)
    dropped_set = set(dropped)
    keep_positions = np.array([i for i in range(1, n_total + 1) if i not in dropped_set]) - 1

    if isinstance(pred, pd.Categorical):
        codes = np.full(n_total, -1, dtype=pred.codes.dtype)
        codes[keep_positions] = pred.codes
        return pd.Categorical.from_codes(codes, categories=pred.categories, ordered=pred.ordered)
    if isinstance(pred, pd.DataFrame):
        out_df = pd.DataFrame(np.full((n_total, pred.shape[1]), np.nan), columns=pred.columns)
        out_df.iloc[keep_positions, :] = pred.to_numpy()
        return out_df
    out_arr = np.full(n_total, np.nan, dtype=float)
    out_arr[keep_positions] = np.asarray(pred, dtype=float)
    return out_arr


def predict_rpart(object: dict[str, Any], newdata: pd.DataFrame | None = None, type: str | None = None, na_action: Any = None) -> np.ndarray[Any, np.dtype[np.float64]] | pd.DataFrame | pd.Categorical:
    # Validate that object is an rpart model (dict with expected keys)
    if not isinstance(object, dict) or 'frame' not in object:
        raise ValueError('Not a legitimate "rpart" object')
    # missing(type) sentinel: if type is None, record that it was missing
    mtype: bool = (type is None)
    # match.arg(type) with default 'vector'
    valid_types: list[str] = ['vector', 'prob', 'class', 'matrix']
    if type is None:
        type = 'vector'
    elif type not in valid_types:
        # partial matching
        matches: list[str] = [t for t in valid_types if t.startswith(type)]
        if len(matches) == 1:
            type = matches[0]
        else:
            raise ValueError(f"'arg' should be one of {valid_types}")
    # Determine where: node assignments for each observation
    if newdata is None:
        # missing(newdata): use object$where directly
        where: np.ndarray[Any, np.dtype[np.int32]] = object['where']
    else:
        # newdata provided: need to compute node assignments
        # delete.response(object$terms) -> use object['terms'] directly (stub)
        # model.frame stub: apply na_rpart or use newdata directly
        # .checkMFClasses -> no-op stub
        from .rpart_matrix import rpart_matrix
        from .pred_rpart import pred_rpart
        where = pred_rpart(object, rpart_matrix(newdata))
    frame: pd.DataFrame = object['frame']
    # rpart.py stores this as the R-attribute-style key '_ylevels'
    # (mirrors attr(ans, "ylevels") <- init$ylevels in rpart.R).
    ylevels: list[str] | None = object.get('_ylevels', None)
    nclass: int = len(ylevels) if ylevels is not None else 0
    # if type was missing and nclass > 0, use 'prob'
    if mtype and nclass > 0:
        type = 'prob'
    # Extract predictions based on type
    # where is 1-based node index array into frame rows
    where_0: np.ndarray[Any, np.dtype[np.int64]] = np.asarray(where, dtype=np.int64) - 1
    # Compute names(where): observation labels
    if isinstance(where, pd.Series):
        obs_names: list[Any] | None = list(where.index)
    else:
        obs_names = None
    pred: np.ndarray[Any, np.dtype[np.float64]] | pd.DataFrame | pd.Categorical
    if type == 'vector' or (type == 'matrix' and 'yval2' not in frame.columns):
        # pred <- frame$yval[where]; names(pred) <- names(where)
        yval: np.ndarray[Any, np.dtype[np.float64]] = frame['yval'].values
        pred_arr: np.ndarray[Any, np.dtype[np.float64]] = yval[where_0]
        if obs_names is not None:
            pred = pd.Series(pred_arr, index=obs_names).to_numpy()
        else:
            pred = pred_arr
    elif type == 'matrix':
        # pred <- frame$yval2[where, ]
        # dimnames(pred) <- list(names(where), NULL)
        yval2: np.ndarray[Any, np.dtype[np.float64]] = _yval2_matrix(frame)
        pred_mat: np.ndarray[Any, np.dtype[np.float64]] = yval2[where_0, :]
        if obs_names is not None:
            pred = pd.DataFrame(pred_mat, index=obs_names)
        else:
            pred = pd.DataFrame(pred_mat)
    elif type == 'class' and nclass > 0:
        # factor(ylevels[frame$yval[where]], levels=ylevels)
        if ylevels is None or len(ylevels) == 0:
            raise ValueError("type 'class' is only appropriate for classification")
        yval_int: np.ndarray[Any, np.dtype[np.int64]] = frame['yval'].values.astype(np.int64)
        # ylevels[frame$yval[where]] in R is 1-based; frame$yval values are 1-based indices into ylevels
        predicted_labels: list[str] = [ylevels[int(v) - 1] for v in yval_int[where_0]]
        pred = pd.Categorical(predicted_labels, categories=ylevels)
    elif type == 'prob' and nclass > 0:
        # pred <- frame$yval2[where, 1L + nclass + 1L:nclass, drop=FALSE]
        # In R 1-based: columns are (1+nclass+1) to (1+nclass+nclass) = (nclass+2) to (2*nclass+1)
        # In Python 0-based: columns are (nclass+1) to (2*nclass+1) exclusive
        yval2_all: np.ndarray[Any, np.dtype[np.float64]] = _yval2_matrix(frame)
        # R: 1L + nclass + 1L:nclass  -> 1-based columns (nclass+2)..(2*nclass+1)
        # Python 0-based: columns (nclass+1)..(2*nclass+1)
        col_start: int = 1 + nclass
        col_end: int = 1 + 2 * nclass
        pred_prob: np.ndarray[Any, np.dtype[np.float64]] = yval2_all[where_0, col_start:col_end]
        # dimnames(pred) <- list(names(where), ylevels)
        if obs_names is not None:
            pred = pd.DataFrame(pred_prob, index=obs_names, columns=ylevels)
        else:
            pred = pd.DataFrame(pred_prob, columns=ylevels)
    else:
        raise ValueError('Invalid prediction for "rpart" object')
    # Expand out the missing values in the result, but only if operating on
    # the original dataset (matches R's naresid(object$na.action, pred)).
    if newdata is None and object.get('na.action') is not None:
        pred = _naresid(object.get('na.action'), pred)
    return pred

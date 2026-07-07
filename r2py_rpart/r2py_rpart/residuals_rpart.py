from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _frame_column_at_where(
    frame: pd.DataFrame | None, where: Any, column: str
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Replica of R's `frame[[column]][object$where]` (1-based) vector
    indexing, needed because R silently propagates `NULL`/zero-length
    results instead of raising, and out-of-range positions become `NA`
    rather than an error:

      - `frame` missing (R: `object$frame` is `NULL`) -> `NULL[[column]]` is
        `NULL`, and `NULL[idx]` is always `NULL` (length 0), regardless of
        `idx` -- so this always returns a length-0 array.
      - `column` absent from `frame` -> same `NULL` propagation as above.
      - `where` missing (R: `object$where` is `NULL`) -> `v[NULL]` is always
        length 0, regardless of `v`'s length -- so this always returns a
        length-0 array.
      - otherwise: an array the same length as `where`, with `NaN` at any
        position whose (1-based) value falls outside `[1, nrow(frame)]` (R's
        own out-of-range vector indexing yields `NA` there, not an error).
    """
    if frame is None or column not in frame.columns:
        return np.array([], dtype=np.float64)
    if where is None:
        return np.array([], dtype=np.float64)
    where_arr: np.ndarray[Any, np.dtype[np.int64]] = np.asarray(where, dtype=np.int64)
    if where_arr.size == 0:
        return np.array([], dtype=np.float64)
    vals: np.ndarray[Any, np.dtype[np.float64]] = np.asarray(frame[column].values, dtype=np.float64)
    where_0: np.ndarray[Any, np.dtype[np.int64]] = where_arr - 1
    out: np.ndarray[Any, np.dtype[np.float64]] = np.full(where_0.shape, np.nan, dtype=np.float64)
    valid: np.ndarray[Any, np.dtype[np.bool_]] = (where_0 >= 0) & (where_0 < len(vals))
    out[valid] = vals[where_0[valid]]
    return out


def _yval2_rows_at_where(frame: pd.DataFrame | None, where: Any) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Same semantics as `_frame_column_at_where`, but for `frame$yval2`,
    which is stored as one array per row (an object-dtype column -- see
    rpart.py's own `frame["yval2"] = list(np.hstack(...))`), so it must be
    stacked into a proper 2-D array via `.tolist()` first (mirroring
    predict_rpart.py's own `_yval2_matrix()` helper, and print_rpart.py's /
    summary_rpart.py's equivalent fixes for this exact same data-layout
    issue) before it can be row-indexed or cast with `dtype=np.float64`.
    """
    if frame is None or 'yval2' not in frame.columns:
        return np.zeros((0, 0), dtype=np.float64)
    if where is None:
        return np.zeros((0, 0), dtype=np.float64)
    where_arr: np.ndarray[Any, np.dtype[np.int64]] = np.asarray(where, dtype=np.int64)
    if where_arr.size == 0:
        return np.zeros((0, 0), dtype=np.float64)
    mat: np.ndarray[Any, np.dtype[np.float64]] = np.array(frame['yval2'].tolist(), dtype=np.float64)
    where_0: np.ndarray[Any, np.dtype[np.int64]] = where_arr - 1
    out: np.ndarray[Any, np.dtype[np.float64]] = np.full((where_0.shape[0], mat.shape[1]), np.nan, dtype=np.float64)
    valid: np.ndarray[Any, np.dtype[np.bool_]] = (where_0 >= 0) & (where_0 < mat.shape[0])
    out[valid] = mat[where_0[valid]]
    return out


def residuals_rpart(object: dict[str, Any], type: str = 'usual', **kwargs: Any) -> np.ndarray[Any, np.dtype[np.float64]]:
    # Validate that object is (plausibly) an rpart model. R's own check
    # (`inherits(object, "rpart")`) only inspects the class attribute, not the
    # object's content -- a plain python dict has no such attribute, so the
    # closest faithful analogue is to reject only inputs that cannot
    # plausibly be an rpart-like object at all (non-dicts). Missing
    # individual keys (frame/where/etc.) is handled below via R's own
    # NULL-propagation semantics rather than an upfront content check --
    # mirroring R's actual (lack of) validation instead of imposing a
    # stricter, non-R-derived requirement here.
    if not isinstance(object, dict):
        raise ValueError('Not a legitimate "rpart" object')
    # Retrieve response vector; fall back to model.frame extraction stub
    y: np.ndarray[Any, np.dtype[np.float64]] | None = object.get('y')
    if y is None:
        # model.extract(model.frame(object), 'response') stub
        y = object.get('y')
    frame: pd.DataFrame | None = object.get('frame')
    # match.arg(type) — validate type against allowed choices
    valid_types: list[str] = ['usual', 'pearson', 'deviance']
    if type not in valid_types:
        matches: list[str] = [t for t in valid_types if t.startswith(type)]
        if len(matches) == 1:
            type = matches[0]
        else:
            raise ValueError("Invalid type of residual")
    # object$where -- may be absent/None; NULL-propagation handled by the
    # `_frame_column_at_where`/`_yval2_rows_at_where` helpers below rather
    # than eagerly converting/raising here.
    where_raw: Any = object.get('where')
    method: str = object['method']
    if method == 'class':
        ylevels: list[str] = object['_ylevels']
        nclass: int = len(ylevels)
        # y is an integer array of 1-based class labels
        y_int: np.ndarray[Any, np.dtype[np.int64]] = np.asarray(y, dtype=np.int64)
        if type == 'usual':
            # frame$yval[object$where] gives predicted class (1-based integer)
            yhat_vals: np.ndarray[Any, np.dtype[np.float64]] = _frame_column_at_where(frame, where_raw, 'yval')
            if yhat_vals.size == 0:
                resid: np.ndarray[Any, np.dtype[np.float64]] = np.array([], dtype=np.float64)
            else:
                yhat_int: np.ndarray[Any, np.dtype[np.int64]] = yhat_vals.astype(np.int64)
                loss: np.ndarray[Any, np.dtype[np.float64]] = np.asarray(object['parms']['loss'], dtype=np.float64)
                # loss[cbind(y, yhat)] -> loss[y_int - 1, yhat_int - 1] (0-based)
                resid = loss[y_int - 1, yhat_int - 1]
        else:
            # frame$yval2[object$where, 1L+nclass+1L:nclass] -> columns nclass+1 : 2*nclass+1
            yval2_rows: np.ndarray[Any, np.dtype[np.float64]] = _yval2_rows_at_where(frame, where_raw)
            if yval2_rows.size == 0:
                resid = np.array([], dtype=np.float64)
            else:
                yprob: np.ndarray[Any, np.dtype[np.float64]] = yval2_rows[:, nclass + 1: 2 * nclass + 1]
                # cbind(seq(y), unclass(y)) -> yprob[i, class_of_y[i] - 1]
                yhat: np.ndarray[Any, np.dtype[np.float64]] = yprob[np.arange(len(y_int)), y_int - 1]
                if type == 'pearson':
                    resid = (1.0 - yhat) / yhat
                elif type == 'deviance':
                    resid = -2.0 * np.log(yhat)
                else:
                    raise ValueError("Invalid type of residual")
    elif method == 'poisson' or method == 'exp':
        lambda_: np.ndarray[Any, np.dtype[np.float64]] = _frame_column_at_where(frame, where_raw, 'yval')
        if lambda_.size == 0:
            resid = np.array([], dtype=np.float64)
        else:
            y_arr: np.ndarray[Any, np.dtype[np.float64]] = np.asarray(y, dtype=np.float64)
            time: np.ndarray[Any, np.dtype[np.float64]] = y_arr[:, 0]
            events: np.ndarray[Any, np.dtype[np.float64]] = y_arr[:, 1]
            expect: np.ndarray[Any, np.dtype[np.float64]] = lambda_ * time
            # Faithful translation: ifelse(expect == 0, 0.0001, 0) — note: likely a bug in original
            temp: np.ndarray[Any, np.dtype[np.float64]] = np.where(expect == 0, 0.0001, 0).astype(np.float64)
            if type == 'usual':
                resid = events - expect
            elif type == 'pearson':
                resid = (events - expect) / np.sqrt(temp)
            elif type == 'deviance':
                resid = (np.sign(events - expect) *
                         np.sqrt(2.0 * (events * np.log(events / temp) - (events - expect))))
            else:
                raise ValueError("Invalid type of residual")
    else:
        # Default: anova — simple residuals
        yhat_vals = _frame_column_at_where(frame, where_raw, 'yval')
        if yhat_vals.size == 0:
            resid = np.array([], dtype=np.float64)
        else:
            resid = np.asarray(y, dtype=np.float64) - yhat_vals
    # names(resid) <- names(y): propagate index if y is a pandas Series (only
    # when lengths line up -- R's NULL-propagation cases above can legitimately
    # shrink `resid` to length 0 while `y` keeps its original length/index).
    if isinstance(y, pd.Series) and len(resid) == len(y):
        resid = pd.Series(resid, index=y.index)
    # naresid stub: return resid unchanged (na.action handling omitted)
    na_action: Any = object.get('na.action')
    if na_action is not None:
        return resid
    return resid

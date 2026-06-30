from __future__ import annotations

from typing import Any

import re
import numpy as np
import pandas as pd



def rpart_matrix(frame: pd.DataFrame) -> np.ndarray[Any, np.dtype[np.float64]]:
    class RpartMatrix(np.ndarray):
        def __new__(cls, input_array: np.ndarray[Any, np.dtype[np.float64]], col_names: list[str] | None = None) -> 'RpartMatrix':
            obj = np.asarray(input_array, dtype=np.float64).view(cls)
            obj.col_names = col_names if col_names is not None else []
            return obj
        def __array_finalize__(self, obj: object) -> None:
            if obj is None:
                return
            self.col_names = getattr(obj, 'col_names', [])
    if not isinstance(frame, pd.DataFrame) or frame.attrs.get('terms') is None:
        if isinstance(frame, pd.DataFrame):
            return frame.to_numpy(dtype=float)
        return np.atleast_2d(np.array(frame, dtype=float))

    def _encode_col(x: pd.Series) -> np.ndarray[Any, np.dtype[np.float64]]:
        if isinstance(x.dtype, pd.CategoricalDtype):
            # Already a factor: R's as.numeric(x) reuses the existing
            # level -> code mapping (does NOT re-sort levels).
            codes = x.cat.codes.to_numpy().astype(np.float64)
            codes[codes < 0] = np.nan  # NA level, matches R's NA propagation
            return codes + 1.0
        if pd.api.types.is_string_dtype(x) or pd.api.types.is_object_dtype(x):
            # Fresh character data: R's as.numeric(factor(x)) sorts levels.
            cat = pd.Categorical(x, categories=sorted(x.dropna().unique()))
            codes = cat.codes.astype(np.float64)
            codes[codes < 0] = np.nan
            return codes + 1.0
        if not pd.api.types.is_numeric_dtype(x):
            return pd.to_numeric(x, errors='coerce').to_numpy(dtype=np.float64)
        return x.to_numpy(dtype=np.float64)

    # rpart does NOT expand categorical predictors into dummy/contrast
    # columns the way model.matrix() would for ordinary regression models:
    # the tree-building C code natively handles multi-level categorical
    # splits given a single integer-coded column per variable (see the
    # `ncat`/`cats` handling in rpart.R). So unlike a general model.matrix,
    # here every term contributes exactly one numeric column.
    terms = frame.attrs.get('terms')
    term_labels = list(terms.get('term.labels', [])) if isinstance(terms, dict) else list(frame.columns)
    raw_names = [re.sub(r'^`(.*)`$', r'\1', lab) for lab in term_labels]

    cols = []
    for lab, name in zip(term_labels, raw_names):
        colname = lab if lab in frame.columns else name
        cols.append(_encode_col(frame[colname]))
    data = np.column_stack(cols) if cols else np.zeros((len(frame), 0), dtype=np.float64)
    X = RpartMatrix(data, col_names=raw_names)
    return X

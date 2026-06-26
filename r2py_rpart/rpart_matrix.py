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
    def _encode_col(x: pd.Series) -> pd.Series:
        if pd.api.types.is_string_dtype(x) or pd.api.types.is_object_dtype(x):
            cat = pd.Categorical(x, categories=sorted(x.dropna().unique()))
            return pd.Series(cat.codes + 1, index=x.index, dtype=float)
        elif not pd.api.types.is_numeric_dtype(x):
            return pd.to_numeric(x, errors='coerce')
        else:
            return x
    frame = frame.copy()
    for col in frame.columns:
        frame[col] = _encode_col(frame[col])
    terms = frame.attrs.get('terms')
    import patsy
    X_design = patsy.dmatrix(terms, frame, return_type='dataframe')
    X_df = X_design.iloc[:, 1:]
    col_names = [re.sub(r'^`(.*)`$', r'\1', name) for name in X_df.columns.tolist()]
    X = RpartMatrix(X_df.to_numpy(dtype=np.float64), col_names=col_names)
    return X

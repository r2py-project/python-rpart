from __future__ import annotations

from typing import Any

import numpy as np



def formatg(x: np.ndarray[Any, np.dtype[np.number]], digits: int = 7, format: str | None = None) -> np.ndarray[Any, np.dtype[np.str_]]:
    if format is None:
        format = f'%.{digits}g'
    if not (isinstance(x, np.ndarray) and np.issubdtype(x.dtype, np.number)):
        raise TypeError("'x' must be a numeric vector")
    # R's sprintf("%.<digits>g", NA) prints "NA"; Python's "%g" would
    # otherwise print "nan", diverging from R's output. `v != v` is true
    # only for float NaN and is safe on integer dtypes too (always False).
    temp = np.vectorize(lambda v: 'NA' if v != v else format % v)(x)
    if x.ndim == 2:
        return temp.reshape(x.shape, order='F')
    return temp

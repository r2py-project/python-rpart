from __future__ import annotations

from typing import Any

import numpy as np

from .formatg import formatg



def rpart_anova(y: np.ndarray[Any, np.dtype[np.float64]], offset: np.ndarray[Any, np.dtype[np.float64]] | None, parms: Any, wt: np.ndarray[Any, np.dtype[np.float64]]) -> dict[str, Any]:
    if offset is not None:
        y = y - offset
    def summary(yval: np.ndarray[Any, np.dtype[np.float64]] | float, dev: np.ndarray[Any, np.dtype[np.float64]] | float, wt: np.ndarray[Any, np.dtype[np.float64]] | float, ylevel: Any, digits: int) -> np.ndarray[Any, np.dtype[np.str_]]:
        return np.char.add(
            np.char.add('  mean=', formatg(yval, digits)),
            np.char.add(', MSE=',  formatg(dev / wt, digits))
        )
    def text(yval: np.ndarray[Any, np.dtype[np.float64]] | float, dev: np.ndarray[Any, np.dtype[np.float64]] | float, wt: np.ndarray[Any, np.dtype[np.float64]] | float, ylevel: Any, digits: int, n: np.ndarray[Any, np.dtype[np.int_]] | int, use_n: bool) -> np.ndarray[Any, np.dtype[np.str_]]:
        if use_n:
            return np.char.add(
                np.char.add(formatg(yval, digits), '\nn='),
                np.array(n, dtype=str)
            )
        else:
            return formatg(yval, digits)
    return {
        'y': y,
        'parms': None,
        'numresp': 1,
        'numy': 1,
        'summary': summary,
        'text': text,
    }

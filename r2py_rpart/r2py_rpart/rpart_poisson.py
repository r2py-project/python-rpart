from __future__ import annotations

from typing import Any

import numpy as np
from .formatg import formatg



def rpart_poisson(y: np.ndarray[Any, np.dtype[np.float64]], offset: np.ndarray[Any, np.dtype[np.float64]] | None, parms: dict | None, wt: np.ndarray[Any, np.dtype[np.float64]]) -> dict:
    if isinstance(y, np.ndarray) and y.ndim == 2:
        if y.shape[1] != 2:
            raise ValueError("response must be a 2 column matrix or a vector")
        if offset is not None:
            y = y.copy()
            y[:, 0] = y[:, 0] * np.exp(offset)
    else:
        if offset is None:
            y = np.column_stack([np.ones(len(y)), y])
        else:
            y = np.column_stack([np.exp(offset), y])

    if np.any(y[:, 0] <= 0):
        raise ValueError("Observation time must be > 0")
    if np.any(y[:, 1] < 0):
        raise ValueError("Number of events must be >= 0")

    if parms is None:
        parms = {"shrink": 1, "method": 1}
    else:
        if not isinstance(parms, dict):
            parms = dict(parms)
        if len(parms) == 0 or not all(isinstance(k, str) for k in parms.keys()):
            raise ValueError("You must input a named list for parms")
        parms_names = ["method", "shrink"]
        def _pmatch_vec(x_vec, table, nomatch=0):
            # R's pmatch() prefers an exact match over a (unique) partial match.
            result = []
            for x in x_vec:
                exact = [i + 1 for i, s in enumerate(table) if s == x]
                if len(exact) == 1:
                    result.append(exact[0])
                    continue
                matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
                result.append(matches[0] if len(matches) == 1 else nomatch)
            return result
        indx = _pmatch_vec(list(parms.keys()), parms_names, nomatch=0)
        unmatched = [k for k, idx in zip(parms.keys(), indx) if idx == 0]
        if unmatched:
            raise ValueError("'parms' component not matched: %s" % ', '.join(str(u) for u in unmatched))
        parms = {parms_names[idx - 1]: v for (k, v), idx in zip(parms.items(), indx)}

        if parms.get("method") is None:
            method = 1
        else:
            def _pmatch_scalar(x, table, nomatch=None):
                exact = [i + 1 for i, s in enumerate(table) if s == x]
                if len(exact) == 1:
                    return exact[0]
                matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
                if len(matches) == 1:
                    return matches[0]
                return nomatch
            method = _pmatch_scalar(parms["method"], ["deviance", "sqrt"])
            if method is None:
                raise ValueError("Invalid error method for Poisson")

        if parms.get("shrink") is None:
            shrink = 2 - method
        else:
            shrink = parms["shrink"]
        if not isinstance(shrink, (int, float)) or shrink < 0:
            raise ValueError("Invalid shrinkage value")
        parms = {"shrink": shrink, "method": method}

    def _summary(yval, dev, wt, ylevel, digits):
        yval = np.atleast_2d(yval)
        return np.array([
            "  events=" + formatg(yval[:, 1], 7)[i] +
            ",  estimated rate=" + formatg(yval[:, 0], digits)[i] +
            " , mean deviance=" + formatg(dev / wt, digits)[i]
            for i in range(len(yval))
        ])

    def _text(yval, dev, wt, ylevel, digits, n, use_n):
        if not (isinstance(yval, np.ndarray) and yval.ndim == 2):
            yval = np.atleast_2d(yval)
        if use_n:
            return np.array([
                formatg(yval[:, 0], digits)[i] + "\n" +
                formatg(yval[:, 1], 7)[i] + "/" + str(n[i])
                for i in range(len(yval))
            ])
        else:
            return formatg(yval[:, 0], digits)

    return {
        "y": y,
        "parms": parms,
        "numresp": 2,
        "numy": 2,
        "summary": _summary,
        "text": _text,
    }

from __future__ import annotations

from typing import Any

import numpy as np
from .formatg import formatg



def drate2(n: int, ny: int, y: np.ndarray[Any, np.dtype[np.float64]], wt: np.ndarray[Any, np.dtype[np.float64]], itable: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, np.dtype[np.float64]]:
    time = y[:, ny - 2]
    status = y[:, ny - 1]
    ilength = np.diff(itable)
    ngrp = len(ilength)
    index = np.searchsorted(itable[1:], time, side='left')
    index = np.clip(index, 0, ngrp - 1)
    itime = time - itable[index]
    if ny == 3:
        stime = y[:, 0]
        index2 = np.searchsorted(itable[1:], stime, side='left')
        index2 = np.clip(index2, 0, ngrp - 1)
        itime2 = stime - itable[index2]
    tab1 = np.bincount(index, minlength=ngrp)
    temp = np.cumsum(tab1[::-1])[::-1]
    pyears = ilength * np.append(temp[1:], 0) + np.array([itime[index == g].sum() for g in range(ngrp)])
    if ny == 3:
        tab2 = np.bincount(index2, minlength=ngrp)
        temp = np.cumsum(tab2[::-1])[::-1]
        py2 = ilength * np.concatenate([[0], temp[:-1]]) + np.array([itime2[index2 == g].sum() for g in range(ngrp)])
        pyears = pyears - py2
    deaths = np.array([status[index == g].sum() for g in range(ngrp)])
    rate = deaths / pyears
    return rate


def rpart_exp(y: np.ndarray[Any, np.dtype[np.float64]], offset: np.ndarray[Any, np.dtype[np.float64]] | None, parms: dict | None, wt: np.ndarray[Any, np.dtype[np.float64]]) -> dict:
    if not (isinstance(y, np.ndarray) and y.ndim == 2):
        raise ValueError("Response must be a 'survival' object - use the 'Surv()' function")

    ny = y.shape[1]
    n = y.shape[0]

    status = y[:, ny - 1]
    if np.any(y[:, 0] <= 0):
        raise ValueError("Observation time must be > 0")
    if np.all(status == 0):
        raise ValueError("No deaths in data set")
    time = y[:, ny - 2]

    dtimes = np.sort(np.unique(time[status == 1]))
    eps = np.finfo(float).eps
    keep = np.concatenate([[True], np.diff(dtimes) > eps])
    dtimes = dtimes[keep]

    if len(dtimes) > 1000:
        dtimes = np.quantile(dtimes, np.arange(0, 1001) / 1000)

    itable = np.concatenate([[0], dtimes[:-1], [np.max(time)]])

    rate = drate2(n, ny, y, wt, itable)
    cumhaz = np.cumsum(np.concatenate([[0], rate * np.diff(itable)]))
    newy = np.interp(time, itable, cumhaz)
    if ny == 3:
        newy = newy - np.interp(y[:, 0], itable, cumhaz)

    if offset is not None and len(offset) == n:
        newy = newy * np.exp(offset)

    if parms is None:
        parms = {"shrink": 1, "method": 1}
    else:
        if isinstance(parms, dict):
            pass
        else:
            parms = dict(enumerate(parms))
        if len(parms) == 0 or not all(isinstance(k, str) for k in parms.keys()):
            raise ValueError("You must input a named list for parms")
        parms_names = ["method", "shrink"]
        def _pmatch_vec(x_vec, table, nomatch=0):
            result = []
            for x in x_vec:
                matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
                if len(matches) == 1:
                    result.append(matches[0])
                else:
                    exact = [i + 1 for i, s in enumerate(table) if s == x]
                    result.append(exact[0] if len(exact) == 1 else nomatch)
            return result
        indx = _pmatch_vec(list(parms.keys()), parms_names, nomatch=0)
        unmatched = [k for k, idx in zip(parms.keys(), indx) if idx == 0]
        if unmatched:
            raise ValueError(f"'parms' component not matched: {', '.join(str(u) for u in unmatched)}")
        parms = {parms_names[idx - 1]: v for (k, v), idx in zip(parms.items(), indx)}

        if parms.get("method") is None:
            method = 1
        else:
            def _pmatch_scalar(x, table, nomatch=None):
                matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
                if len(matches) == 1:
                    return matches[0]
                exact = [i + 1 for i, s in enumerate(table) if s == x]
                if len(exact) == 1:
                    return exact[0]
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
        return np.array([
            "  events=" + formatg(yval[:, 1], 7)[i] +
            ",  estimated rate=" + formatg(yval[:, 0], digits)[i] +
            " , mean deviance=" + formatg(dev / wt, digits)[i]
            for i in range(len(yval))
        ])

    def _text(yval, dev, wt, ylevel, digits, n, use_n):
        if use_n:
            return np.array([
                formatg(yval[:, 0], digits)[i] + "\n" +
                formatg(yval[:, 1], 7)[i] + "/" + str(n[i])
                for i in range(len(yval))
            ])
        else:
            return " ".join(formatg(yval[:, 0], digits))

    return {
        "y": np.column_stack([newy, y[:, 1]]),
        "parms": parms,
        "numresp": 2,
        "numy": 2,
        "summary": _summary,
        "text": _text,
    }

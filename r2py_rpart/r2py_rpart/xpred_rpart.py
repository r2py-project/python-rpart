from __future__ import annotations

from typing import Any

import numpy as np

from .rpart_matrix import rpart_matrix
from .rpartcallback import rpartcallback

_MISSING = object()


def xpred_rpart(fit: dict[str, Any], xval: int | np.ndarray[Any, np.dtype[np.int32]] = 10, cp: np.ndarray[Any, np.dtype[np.float64]] = _MISSING, return_all: bool = False) -> np.ndarray[Any, np.dtype[np.float64]]:
    if not (isinstance(fit, dict) and fit.get('_rpart_class') == 'rpart'):
        raise ValueError('Invalid fit object')

    # --- pmatch(method, c('anova','poisson','class','user','exp')) ---
    method = fit['method']
    _xpred_methods = ['anova', 'poisson', 'class', 'user', 'exp']
    def _pmatch(x: str, table: list[str]) -> int | None:
        # R's pmatch() prefers an exact match over a (unique) partial match.
        exact = [i + 1 for i, s in enumerate(table) if s == x]
        if len(exact) == 1:
            return exact[0]
        matches = [i + 1 for i, s in enumerate(table) if s.startswith(x)]
        if len(matches) == 1:
            return matches[0]
        return None
    method_int = _pmatch(method, _xpred_methods)
    if method_int == 5:
        method_int = 2

    Terms = fit.get('terms')
    Y = fit.get('y')
    X = fit.get('x')
    wt = fit.get('wt')
    numresp = fit['numresp']

    if Y is None or X is None:
        m = fit.get('model')
        if m is None:
            # eval.parent(model.frame(...)) is not reproducible in Python
            raise NotImplementedError(
                'xpred_rpart: fit does not contain cached x/y and model frame '
                'cannot be re-evaluated in Python. Re-fit with x=True, y=True.'
            )
        if X is None:
            X = rpart_matrix(m)
        if wt is None:
            wt = m.attrs.get('weights')
        if Y is None:
            yflag = True
            Y = m.attrs.get('response')
            offset = Terms.attrs.get('offset') if Terms is not None else None
            if method != 'user':
                _method_fns: dict[str, Any] = {
                    'anova':   rpart_anova,
                    'class':   rpart_class,
                    'poisson': rpart_poisson,
                    'exp':     rpart_exp,
                }
                init_fn = _method_fns[method]
                init = init_fn(Y, offset, None, None)
                Y = init['y']
                numy = int(Y.shape[1]) if (isinstance(Y, np.ndarray) and Y.ndim == 2) else 1
        else:
            yflag = False
            numy = int(Y.shape[1]) if (isinstance(Y, np.ndarray) and Y.ndim == 2) else 1
    else:
        yflag = False
        numy = int(Y.shape[1]) if (isinstance(Y, np.ndarray) and Y.ndim == 2) else 1
        offset = 0

    nobs = int(X.shape[0])
    nvar = int(X.shape[1])
    if wt is None or len(wt) == 0:
        wt = np.ones(nobs, dtype=np.float64)

    # --- cats vector: number of levels per predictor variable ---
    cats = np.zeros(nvar, dtype=np.int32)
    xlevels = fit.get('_xlevels')
    if xlevels is not None:
        col_names = list(X.col_names) if hasattr(X, 'col_names') else list(range(nvar))
        # filter xlevels to only those present in X columns
        xlevels_filtered = {k: v for k, v in xlevels.items() if k in col_names}
        for name, levels in xlevels_filtered.items():
            if name in col_names:
                idx = col_names.index(name)
                cats[idx] = len(levels)

    controls = fit['control']

    # --- cp default: derive geometric-mean cp values from cptable ---
    if cp is _MISSING:
        _cptable = fit['cptable']
        _cptable = _cptable.to_numpy() if hasattr(_cptable, 'to_numpy') else _cptable
        cptable_col0 = np.array(_cptable[:, 0], dtype=np.float64)
        cp_arr = np.sqrt(cptable_col0 * np.concatenate([[10.0], cptable_col0[:-1]]))
        cp_arr[0] = (1.0 + float(_cptable[0, 0])) / 2.0
    else:
        cp_arr = np.asarray(cp, dtype=np.float64)

    # --- xgroups assignment ---
    if np.isscalar(xval) or (isinstance(xval, np.ndarray) and xval.ndim == 0):
        xval_int = int(xval)
        fold_labels = np.resize(np.arange(1, xval_int + 1, dtype=np.int32), nobs)
        xgroups = np.random.permutation(fold_labels).astype(np.int32)
    elif hasattr(xval, '__len__') and len(xval) == X.shape[0]:
        xgroups = np.asarray(xval, dtype=np.int32)
        xval_int = int(len(np.unique(xgroups)))
    else:
        na_action = fit.get('na.action')
        if na_action is not None:
            temp_idx = np.asarray(na_action.get('indices', []), dtype=np.int32) - 1
            xval_arr = np.asarray(xval)
            mask = np.ones(len(xval_arr), dtype=bool)
            mask[temp_idx] = False
            xval_filtered = xval_arr[mask]
            if len(xval_filtered) == nobs:
                xgroups = np.asarray(xval_filtered, dtype=np.int32)
                xval_int = int(len(np.unique(xgroups)))
            else:
                raise ValueError("Wrong length for 'xval'")
        else:
            raise ValueError("Wrong length for 'xval'")

    # --- costs ---
    costs_val = fit.get('call', {}).get('costs')
    if costs_val is None:
        costs = np.ones(nvar, dtype=np.float64)
    else:
        costs = np.asarray(costs_val, dtype=np.float64)

    parms = fit.get('parms', {})
    if parms is None:
        parms = {}

    # --- user method ---
    if method == 'user':
        mlist = fit['functions']
        if yflag:
            if len(parms) == 0:
                init = mlist['init'](Y, offset, None, wt)
            else:
                init = mlist['init'](Y, offset, parms, wt)
            Y = init['Y']
            numy = int(init['numy'])
            parms = init['parms']
        else:
            numy = int(Y.shape[1]) if (isinstance(Y, np.ndarray) and Y.ndim == 2) else 1
            init = {'numresp': numresp, 'numy': numy, 'parms': parms}
        keep = rpartcallback(mlist, nobs, init)
        method_int = 4

    # --- coerce Y, X, wt to float64 ---
    # R: `if (is.matrix(Y)) Y <- as.double(t(Y))`. R matrices are stored
    # column-major, so flattening t(Y) (shape (ny, n)) column-major is
    # equivalent to flattening Y (shape (n, ny)) row-major -- i.e. each
    # observation's ny response values consecutive, exactly what the C code
    # expects ("y is in row major order", see xpred.c). A plain
    # Y.T.ravel() (C-order ravel of the transpose) is instead equivalent to
    # a *column-major* ravel of Y itself, which transposes the per-
    # observation response layout the C code expects whenever ny > 1 --
    # mirrors the identical, already-fixed pattern in rpart.py's own
    # `as.double(t(init$y))` translation (see its comment there).
    if isinstance(Y, np.ndarray) and Y.ndim == 2:
        Y_flat = np.ascontiguousarray(Y, dtype=np.float64).ravel()
    else:
        Y_flat = np.asarray(Y, dtype=np.float64).ravel()
    X_f64 = np.asarray(X, dtype=np.float64)
    wt_f64 = np.asarray(wt, dtype=np.float64)

    # --- parms to flat float64 array ---
    # R's unlist(init$parms) flattens each component (prior/loss/split, etc.)
    # in turn; a plain np.array(list(parms.values())) fails whenever the
    # components have different shapes (e.g. classification's prior vector
    # + loss matrix + scalar split code), so ravel-and-concatenate instead.
    # `parms` may also be a bare scalar/array (e.g. a user-defined method's
    # init() returning `parms=0`, as in rpart/tests/usersplits.R) rather than
    # a dict -- R's unlist() accepts that too (returning it as a length-1+
    # vector unchanged), but `list(0)` raises TypeError since a Python int
    # isn't iterable. Mirror rpart.py's identical (dict / None / else)
    # three-way parms-flattening branch here so both entry points agree.
    if parms is None:
        parms_flat = np.array([0.0], dtype=np.float64)
    elif isinstance(parms, dict):
        parms_source = list(parms.values())
        _flat: list[float] = []
        for v in parms_source:
            _flat.extend(np.asarray(v, dtype=np.float64).ravel().tolist())
        parms_flat = np.array(_flat, dtype=np.float64) if _flat else np.array([0.0], dtype=np.float64)
    else:
        parms_flat = np.asarray(parms, dtype=np.float64).ravel()
        if len(parms_flat) == 0:
            parms_flat = np.array([0.0], dtype=np.float64)

    # --- controls to flat float64 array ---
    # Mirrors R's `as.double(unlist(controls))`: `controls$xval` here is the
    # *stored* fitted-object control list, whose `xval` element may still be
    # the full array the caller originally passed to rpart() (e.g. explicit
    # xgroups) rather than a scalar fold-count -- unlist()/ravel()ing it
    # keeps parity with R and avoids a hard failure from `float()` on an
    # array-valued entry (see rpart.py's identical fix/comment for the main
    # rpart() flattening of `controls`). The C entry point only reads the
    # first 8 slots (minsplit..maxdepth) in any case.
    if isinstance(controls, dict):
        _ctrl_values = controls.values()
    else:
        _ctrl_values = np.atleast_1d(controls)
    _flat_ctrl: list[float] = []
    for v in _ctrl_values:
        _flat_ctrl.extend(np.atleast_1d(np.asarray(v, dtype=np.float64)).ravel().tolist())
    controls_flat = np.array(_flat_ctrl, dtype=np.float64)

    # --- ncat: cats * !fit$ordered ---
    ordered = fit.get('ordered')
    if ordered is not None:
        ordered_arr = np.asarray(ordered, dtype=bool)
        ncat_arr = (cats * (~ordered_arr)).astype(np.int32)
    else:
        ncat_arr = cats.astype(np.int32)

    # --- toprisk: fit$frame[1, 'dev'] (0-based row 0) ---
    toprisk = float(fit['frame']['dev'].iloc[0])

    # --- call C extension xpred ---
    try:
        from r2py_rpart import _xpred_c as _C_xpred
    except ImportError:
        raise NotImplementedError('r2py_rpart._rpart_core is not available')

    pred = _C_xpred(
        ncat=ncat_arr,
        method=int(method_int),
        opt=controls_flat,
        parms=parms_flat,
        xvals=int(xval_int),
        xgrp=xgroups,
        ymat=Y_flat,
        xmat=X_f64,
        wt=wt_f64,
        ny=int(numy),
        cost=costs,
        return_all=int(return_all),
        cp=cp_arr,
        toprisk=toprisk,
        numresp=int(numresp),
    )

    # --- reshape output ---
    nrow_X = int(X.shape[0])
    n_cp = len(cp_arr)
    cp_formatted = [format(v) for v in cp_arr]
    obs_names = list(range(nrow_X))
    if hasattr(X, 'index') or hasattr(X, 'rownames'):
        pass  # row names not tracked in plain ndarray

    if return_all and numresp > 1:
        temp = np.asarray(pred, dtype=np.float64).reshape((numresp, n_cp, nrow_X), order='F')
        return np.transpose(temp)
    else:
        return np.asarray(pred, dtype=np.float64).reshape((nrow_X, n_cp), order='C')

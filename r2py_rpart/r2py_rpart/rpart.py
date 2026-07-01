from __future__ import annotations

from typing import Any

import re
import inspect
import numpy as np
import pandas as pd

from .importance import importance
from .model_frame_rpart import _build_model_frame
from .rpart_anova import rpart_anova
from .rpart_class import rpart_class
from .rpart_control import rpart_control
from .rpart_exp import rpart_exp
from .rpart_matrix import rpart_matrix
from .rpart_poisson import rpart_poisson
from .rpartcallback import rpartcallback

_MISSING = object()


def rpart(formula: Any, data: pd.DataFrame | None = None, weights: np.ndarray[Any, np.dtype[np.float64]] | None = _MISSING, subset: np.ndarray[Any, np.dtype[np.bool_]] | None = _MISSING, na_action: Any = _MISSING, method: str | dict[str, Any] = _MISSING, model: bool | pd.DataFrame = False, x: bool = False, y: bool = True, parms: Any = _MISSING, control: dict[str, Any] = _MISSING, cost: np.ndarray[Any, np.dtype[np.float64]] = _MISSING, **kwargs: Any) -> dict[str, Any]:
    # Store call info as a dict (match.call() equivalent); only arguments
    # actually supplied are recorded, mirroring R's match.call().
    Call: dict[str, Any] = {
        "formula": formula,
        "data": data,
        "weights": None if weights is _MISSING else weights,
        "subset": None if subset is _MISSING else subset,
    }

    # Check if model is a DataFrame (pre-built model frame)
    if isinstance(model, pd.DataFrame):
        m: pd.DataFrame = model
        model = False
    else:
        # Equivalent of R's:
        #   temp <- Call[c(1L, indx)]; temp$na.action <- na.action
        #   temp[[1L]] <- quote(stats::model.frame); m <- eval.parent(temp)
        if not isinstance(formula, str):
            raise NotImplementedError(
                "rpart() requires either a string formula with 'data=' or a "
                "pre-built model frame passed via model="
            )
        m = _build_model_frame(
            formula,
            data,
            weights=None if weights is _MISSING else weights,
            subset=None if subset is _MISSING else subset,
            na_action=None if na_action is _MISSING else na_action,
        )

    Terms: dict[str, Any] | None = m.attrs.get("terms")
    if Terms is None:
        Terms = {}

    # Check for interaction terms
    order_vals = Terms.get("order", []) if isinstance(Terms, dict) else []
    if any(o > 1 for o in order_vals):
        raise ValueError("Trees cannot handle interaction terms")

    # Extract response, weights, offset
    Y: Any = m.attrs.get("response") if m.attrs.get("response") is not None else m.iloc[:, 0]
    wt: np.ndarray[Any, np.dtype[np.float64]] | None = m.attrs.get("weights")
    if wt is not None and np.any(np.asarray(wt) < 0):
        raise ValueError("negative weights not allowed")
    if wt is None or len(wt) == 0:
        wt = np.ones(len(m), dtype=np.float64)
    else:
        wt = np.asarray(wt, dtype=np.float64)
    offset: np.ndarray[Any, np.dtype[np.float64]] | None = m.attrs.get("offset")

    X: np.ndarray[Any, np.dtype[np.float64]] = rpart_matrix(m)
    nobs: int = X.shape[0]
    nvar: int = X.shape[1]

    # Determine method
    if method is _MISSING:
        if isinstance(Y, pd.Categorical) or (hasattr(Y, 'dtype') and hasattr(Y.dtype, 'categories')):
            method = "class"
        elif isinstance(Y, pd.Series) and pd.api.types.is_categorical_dtype(Y):
            method = "class"
        elif isinstance(Y, np.ndarray) and Y.dtype.kind in ('U', 'S', 'O'):
            method = "class"
        elif isinstance(Y, pd.Series) and Y.dtype.kind in ('U', 'S', 'O'):
            method = "class"
        elif isinstance(Y, np.ndarray) and Y.ndim == 2 and Y.shape[1] >= 2 and getattr(Y, '_surv', False):
            method = "exp"
        elif isinstance(Y, np.ndarray) and Y.ndim == 2:
            method = "poisson"
        else:
            method = "anova"

    keep: dict[str, Any] | None = None
    if isinstance(method, dict):
        # User-written split methods
        mlist: dict[str, Any] = method
        method = "user"

        # Set up C callback
        if parms is _MISSING:
            init: dict[str, Any] = mlist["init"](Y, offset, wt=wt)
        else:
            init = mlist["init"](Y, offset, parms, wt)
        keep: dict[str, Any] = rpartcallback(mlist, nobs, init)

        method_int: int = 4  # the fourth entry in func_table.h
        parms = init["parms"]
    else:
        # Partial match method string. R's pmatch() prefers an exact match
        # over a (unique) partial match.
        _method_table = ["anova", "poisson", "class", "exp"]
        _exact = [i + 1 for i, s in enumerate(_method_table) if s == method]
        if len(_exact) == 1:
            method_int = _exact[0]
        else:
            _matches = [i + 1 for i, s in enumerate(_method_table) if s.startswith(method)]
            method_int = _matches[0] if len(_matches) == 1 else None
        if method_int is None:
            raise ValueError("Invalid method")
        method = _method_table[method_int - 1]
        if method_int == 4:
            method_int = 2

        _METHOD_INITS: dict[str, Any] = {
            "anova": rpart_anova,
            "poisson": rpart_poisson,
            "class": rpart_class,
            "exp": rpart_exp,
        }
        init_fn = _METHOD_INITS[method]
        if parms is _MISSING:
            init = init_fn(Y, offset, None, wt)
        else:
            init = init_fn(Y, offset, parms, wt)
        # Skip asNamespace / environment reassignment (no-op in Python)
        mlist = {}

    Y = init["y"]

    # Get x-levels for categorical variables
    xlevels: dict[str, list[Any]] | None = Terms.get("xlevels", None) if isinstance(Terms, dict) else None
    cats: np.ndarray[Any, np.dtype[np.int_]] = np.zeros(nvar, dtype=int)
    if xlevels is not None:
        _col_names = list(getattr(X, 'col_names', [])) if hasattr(X, 'col_names') else list(m.columns)
        for xname, xlev in xlevels.items():
            _matches_idx = [j for j, cn in enumerate(_col_names) if cn == xname]
            for j in _matches_idx:
                cats[j] = len(xlev)

    # Validate extra kwargs against rpart_control formals
    if kwargs:
        _control_params = list(inspect.signature(rpart_control).parameters.keys())
        _unmatched = [k for k in kwargs if k not in _control_params]
        if _unmatched:
            raise ValueError(f"Argument {_unmatched[0]} not matched")

    controls: dict[str, Any] = rpart_control(**kwargs)
    if control is not _MISSING:
        _control_dict = control if isinstance(control, dict) else dict(control)
        if not all(k in controls for k in _control_dict):
            raise ValueError("unkown named elements in 'control'")
        controls = rpart_control(**_control_dict)

    xval: int | np.ndarray[Any, np.dtype[np.int_]] = controls["xval"]
    xgroups: np.ndarray[Any, np.dtype[np.int_]]
    if xval is None or (np.ndim(xval) == 0 and int(xval) == 0) or method == "user":
        xgroups = np.zeros(nobs, dtype=np.int32)
        xval = 0
    elif np.ndim(xval) == 0 and int(xval) >= 1:
        _xval_int = int(xval)
        xgroups = np.random.permutation(np.resize(np.arange(1, _xval_int + 1), nobs))
        xval = _xval_int
    elif hasattr(xval, '__len__') and len(xval) == nobs:
        xgroups = np.asarray(xval, dtype=np.int32)
        xval = int(len(np.unique(xgroups)))
    else:
        # Check if na.action removed observations
        na_act = m.attrs.get("na.action")
        if na_act is not None:
            _removed = np.asarray(na_act.get("indices", []), dtype=int) - 1  # convert to 0-based
            _xval_arr = np.asarray(xval)
            _mask = np.ones(len(_xval_arr), dtype=bool)
            _mask[_removed] = False
            _xval_trimmed = _xval_arr[_mask]
            if len(_xval_trimmed) == nobs:
                xgroups = _xval_trimmed.astype(np.int32)
                xval = int(len(np.unique(xgroups)))
            else:
                raise ValueError("Wrong length for 'xval'")
        else:
            raise ValueError("Wrong length for 'xval'")

    if cost is _MISSING:
        cost_arr: np.ndarray[Any, np.dtype[np.float64]] = np.ones(nvar, dtype=np.float64)
    else:
        cost_arr = np.asarray(cost, dtype=np.float64)
        if len(cost_arr) != nvar:
            raise ValueError("Cost vector is the wrong length")
        if np.any(cost_arr <= 0):
            raise ValueError("Cost vector must be positive")

    # Build isord: is each variable an ordered factor?
    def _tfun(col: Any) -> bool | list[bool]:
        if isinstance(col, np.ndarray) and col.ndim == 2:
            is_ord: bool = hasattr(col, 'cat') and col.cat.ordered
            return [is_ord] * col.shape[1]
        else:
            if isinstance(col, pd.Series):
                return hasattr(col, 'cat') and col.cat.ordered
            return False

    _term_labels: list[str] = Terms.get("term.labels", []) if isinstance(Terms, dict) else []
    labs: list[str] = [re.sub(r'^`(.*)`$', r'\1', lab) for lab in _term_labels]
    _isord_list: list[bool] = []
    for lab in labs:
        if lab in m.columns:
            _val = _tfun(m[lab])
            if isinstance(_val, list):
                _isord_list.extend(_val)
            else:
                _isord_list.append(bool(_val))
        else:
            _isord_list.append(False)
    # Ensure isord has length nvar
    if len(_isord_list) < nvar:
        _isord_list.extend([False] * (nvar - len(_isord_list)))
    isord: np.ndarray[Any, np.dtype[np.bool_]] = np.array(_isord_list[:nvar], dtype=bool)

    # Prepare arrays for C call
    X_double: np.ndarray[Any, np.dtype[np.float64]] = np.asarray(X, dtype=np.float64)
    wt_double: np.ndarray[Any, np.dtype[np.float64]] = np.asarray(wt, dtype=np.float64)
    if init["parms"] is None:
        _parms_flat = np.array([0.0], dtype=np.float64)
    elif isinstance(init["parms"], dict):
        # Flatten like R's unlist(): concatenate all values in insertion order.
        # R matrices (e.g. parms$loss) are always stored column-major, so
        # unlist() on a list containing a matrix yields that matrix's
        # underlying column-major storage vector directly. A 2-D numpy array
        # here represents the same matrix but is stored row-major, so it must
        # be raveled in Fortran (column-major) order to match R's unlist()
        # byte-for-byte -- a plain (row-major) ravel() would transpose the
        # matrix's flattened layout for any non-symmetric matrix (e.g. a
        # classification loss matrix), corrupting what the C code receives.
        _flat: list[float] = []
        for v in init["parms"].values():
            _arr = np.asarray(v, dtype=np.float64)
            _order = 'F' if _arr.ndim >= 2 else 'C'
            _flat.extend(_arr.ravel(order=_order).tolist())
        _parms_flat = np.array(_flat, dtype=np.float64) if _flat else np.array([0.0], dtype=np.float64)
    else:
        _parms_flat = np.asarray(init["parms"], dtype=np.float64).ravel()
        if len(_parms_flat) == 0:
            _parms_flat = np.array([0.0], dtype=np.float64)

    # Flatten controls to double array (order matches rpart.control return keys).
    # Mirrors R's `as.double(unlist(controls))`: `controls` here is the
    # *original* rpart.control() list (never mutated -- only the separate
    # local `xval` variable above is reassigned to a scalar fold-count), so
    # `controls$xval`/`controls["xval"]` can still be the full array the
    # caller passed in (e.g. explicit xgroups). The C entry point
    # (rpart.c) only ever reads opt[0..7] (minsplit..maxdepth) -- the
    # trailing xval slot(s) are unused padding in both R and here -- so it
    # is safe to append whatever `controls["xval"]` unlist()s to without
    # needing it to be a single scalar.
    _controls_flat = np.concatenate([
        np.array([
            float(controls["minsplit"]),
            float(controls["minbucket"]),
            float(controls["cp"]),
            float(controls["maxcompete"]),
            float(controls["maxsurrogate"]),
            float(controls["usesurrogate"]),
            float(controls["surrogatestyle"]),
            float(controls["maxdepth"]),
        ], dtype=np.float64),
        np.atleast_1d(np.asarray(controls["xval"], dtype=np.float64)),
    ])

    # as.double(t(init$y)): R matrices are stored column-major, so
    # flattening t(Y) (shape (ny, n)) column-major is equivalent to
    # flattening Y (shape (n, ny)) row-major -- i.e. each observation's
    # ny response values consecutive, exactly what the C code expects
    # ("y is in row major order", see rpart.c). For ny==1 this collapses
    # to a no-op ravel either way, which is why a previous transposed
    # version of this line went unnoticed for single-column responses.
    _y_arr = np.asarray(Y, dtype=np.float64)
    if _y_arr.ndim == 1:
        _y_arr = _y_arr.reshape(-1, 1)
    _y_t: np.ndarray[Any, np.dtype[np.float64]] = np.ascontiguousarray(_y_arr).ravel()

    # ncat * !isord  (ordered factor cols treated as continuous by C)
    _ncat_arr: np.ndarray[Any, np.dtype[np.int32]] = np.asarray(cats * (~isord), dtype=np.int32)

    # Import and call the C extension
    try:
        from r2py_rpart import _rpart_c
    except ImportError:
        raise NotImplementedError("r2py_rpart C extension is not available")

    rpfit: dict[str, Any] = _rpart_c(
        ncat=_ncat_arr,
        method=int(method_int),
        opt=_controls_flat,
        parms=_parms_flat,
        xvals=int(xval),
        xgrp=np.asarray(xgroups, dtype=np.int32),
        ymat=_y_t,
        xmat=X_double,
        wt=wt_double,
        ny=int(init["numy"]),
        cost=cost_arr,
    )

    # method=4 (user-defined splits): if the user's split/eval callback
    # raised or returned malformed data during the C fit, rpartcallback()
    # substituted a harmless placeholder so the C call could return safely
    # instead of crashing on a null SEXP -- the resulting rpfit is
    # meaningless in that case, so surface the original error now instead.
    if keep is not None:
        _pending = keep.get("_pending_exception")
        if _pending is not None and _pending[0] is not None:
            raise _pending[0]

    nsplit: int = rpfit["isplit"].shape[0]  # total number of splits, primary and surrogate
    ncat_count: int = rpfit["csplit"].shape[0] if "csplit" in rpfit else 0
    if nsplit == 0:
        xval = 0  # No xvals were done if no splits were found

    # Set up cptable with row/column names
    numcp: int = rpfit["cptable"].shape[1] if rpfit["cptable"].ndim == 2 else 1
    _nrow_cp: int = rpfit["cptable"].shape[0] if rpfit["cptable"].ndim == 2 else rpfit["cptable"].shape[0]
    if _nrow_cp == 3:
        _temp_labels: list[str] = ["CP", "nsplit", "rel error"]
    else:
        _temp_labels = ["CP", "nsplit", "rel error", "xerror", "xstd"]
    cptable_df = pd.DataFrame(rpfit["cptable"].T, columns=_temp_labels)
    cptable_df.index = list(range(1, numcp + 1))

    # Build splits DataFrame
    tname: list[str] = ["<leaf>"] + list(getattr(X, 'col_names', []) if hasattr(X, 'col_names') else ([c for c in m.columns if c != m.columns[0]]))
    # Pad tname to cover all variable indices
    while len(tname) <= nvar:
        tname.append(f"V{len(tname)}")

    if nsplit > 0:
        _isplit_cols: np.ndarray[Any, np.dtype[np.float64]] = rpfit["isplit"][:, 1:3].astype(float)
        _dsplit: np.ndarray[Any, np.dtype[np.float64]] = rpfit["dsplit"]
        _splits_data = np.column_stack([_isplit_cols, _dsplit])
        _row_idx = rpfit["isplit"][:, 0].astype(int)  # 1-based variable indices from C
        _split_row_names: list[str] = [tname[i] if i < len(tname) else tname[0] for i in _row_idx]
        splits_df = pd.DataFrame(
            _splits_data,
            index=_split_row_names,
            columns=["count", "ncat", "improve", "index", "adj"],
        )
    else:
        splits_df = pd.DataFrame(columns=["count", "ncat", "improve", "index", "adj"])

    index_vec: np.ndarray[Any, np.dtype[np.int_]] = rpfit["inode"][:, 1]  # points to first split for each node (1-based in C)

    # Handle ordered factor splits
    _isord_arr = isord.astype(bool)
    if nsplit > 0:
        _cvar = rpfit["isplit"][:, 0].astype(int) - 1  # convert 1-based to 0-based
        nadd: int = int(np.sum(_isord_arr[_cvar]))
    else:
        nadd = 0

    catmat: np.ndarray[Any, np.dtype[np.int_]] | None
    if nadd > 0:
        _max_cats = int(np.max(cats)) if np.max(cats) > 0 else 1
        newc: np.ndarray[Any, np.dtype[np.int_]] = np.zeros((nadd, _max_cats), dtype=int)
        _indx_bool: np.ndarray[Any, np.dtype[np.bool_]] = _isord_arr[_cvar]  # True where variable is ordered
        _cdir = splits_df.iloc[np.where(_indx_bool)[0], 1].values  # ncat column → direction
        _ccut = np.floor(splits_df.iloc[np.where(_indx_bool)[0], 3].values)  # index column → cut point
        # Update splits: ncat col → number of categories, index col → row in catmat
        _ordered_split_rows = np.where(_indx_bool)[0]
        splits_df.iloc[_ordered_split_rows, 1] = cats[_cvar[_indx_bool]]
        splits_df.iloc[_ordered_split_rows, 3] = np.arange(ncat_count + 1, ncat_count + nadd + 1)
        for i in range(nadd):
            _col_count = int(cats[((_cvar[_indx_bool])[i])])
            newc[i, :_col_count] = -int(_cdir[i])
            newc[i, :int(_ccut[i])] = int(_cdir[i])
        if ncat_count == 0:
            catmat = newc
        else:
            _cs = rpfit["csplit"].copy()
            _ncs = _cs.shape[1]
            _ncc = newc.shape[1]
            if _ncs < _ncc:
                _cs = np.hstack([_cs, np.zeros((_cs.shape[0], _ncc - _ncs), dtype=int)])
            catmat = np.vstack([_cs, newc])
        ncat_count = ncat_count + nadd
    else:
        catmat = rpfit.get("csplit", None)

    # Build frame DataFrame
    if nsplit == 0:
        frame: pd.DataFrame = pd.DataFrame(
            {
                "var": ["<leaf>"],
                "n": rpfit["inode"][:, 4],
                "wt": rpfit["dnode"][:, 2],
                "dev": rpfit["dnode"][:, 0],
                "yval": rpfit["dnode"][:, 3],
                "complexity": rpfit["dnode"][:, 1],
                "ncompete": np.zeros(rpfit["inode"].shape[0], dtype=int),
                "nsurrogate": np.zeros(rpfit["inode"].shape[0], dtype=int),
            },
            index=[1],
        )
    else:
        _temp_index = np.where(index_vec == 0, 1, index_vec).astype(int)  # safe fallback (1-based)
        # svar: variable index for each node (0 means leaf)
        _svar = np.where(
            index_vec == 0,
            0,
            rpfit["isplit"][_temp_index - 1, 0]  # 1-based variable indices from C; 0 = leaf
        ).astype(int)
        _var_names: list[str] = [tname[sv] if sv < len(tname) else "<leaf>" for sv in _svar]
        frame = pd.DataFrame(
            {
                "var": _var_names,
                "n": rpfit["inode"][:, 4],
                "wt": rpfit["dnode"][:, 2],
                "dev": rpfit["dnode"][:, 0],
                "yval": rpfit["dnode"][:, 3],
                "complexity": rpfit["dnode"][:, 1],
                "ncompete": np.maximum(0, rpfit["inode"][:, 2] - 1),
                "nsurrogate": rpfit["inode"][:, 3],
            },
            index=rpfit["inode"][:, 0].astype(int),
        )

    # Add yval2 for classification or multi-response methods
    if method_int == 3:
        numclass: int = init["numresp"] - 2
        nodeprob: np.ndarray[Any, np.dtype[np.float64]] = rpfit["dnode"][:, numclass + 4] / np.sum(wt)
        _temp_counts = np.maximum(1, init["counts"])
        _temp_mat = rpfit["dnode"][:, 4:(4 + numclass)] @ np.diag(
            np.asarray(init["parms"]["prior"], dtype=float) / _temp_counts.astype(float)
        )
        _row_sums = _temp_mat.sum(axis=1, keepdims=True)
        yprob: np.ndarray[Any, np.dtype[np.float64]] = _temp_mat / np.where(_row_sums == 0, 1, _row_sums)
        yval2: np.ndarray[Any, np.dtype[np.float64]] = rpfit["dnode"][:, 3:(4 + numclass)]
        frame["yval2"] = list(np.hstack([yval2, yprob, nodeprob.reshape(-1, 1)]))
    elif init["numresp"] > 1:
        frame["yval2"] = list(rpfit["dnode"][:, 3:])  # drop first 3 cols (0-based: drop 0,1,2)

    # Build functions dict
    if init.get("summary") is None:
        raise ValueError("Initialization routine is missing the 'summary' function")
    functions: dict[str, Any] = {"summary": init["summary"]}
    if init.get("print") is not None:
        functions["print"] = init["print"]
    if init.get("text") is not None:
        functions["text"] = init["text"]
    if method == "user":
        functions.update(mlist)

    where: np.ndarray[Any, np.dtype[np.int_]] = rpfit["which"]
    _where_names: list[str] = list(m.index.astype(str))
    # Store where as array; names attached as separate attribute if needed

    ans: dict[str, Any] = {
        "frame": frame,
        "where": where,
        "call": Call,
        "terms": Terms,
        "cptable": cptable_df,
        "method": method,
        "parms": init["parms"],
        "control": controls,
        "functions": functions,
        "numresp": init["numresp"],
    }
    if nsplit:
        ans["splits"] = splits_df
    if ncat_count > 0 and catmat is not None:
        ans["csplit"] = catmat + 2
    if nsplit:
        ans["variable.importance"] = importance(ans)
    if model is not False and isinstance(model, bool) and model:
        ans["model"] = m
        if y is _MISSING:
            y = False
    if y is not _MISSING and y:
        ans["y"] = Y
    elif y is _MISSING or (not isinstance(y, bool)):
        ans["y"] = Y
    if x:
        ans["x"] = X
        ans["wt"] = wt
    ans["ordered"] = isord
    _na_action = m.attrs.get("na.action")
    if _na_action is not None:
        ans["na.action"] = _na_action
    if xlevels is not None:
        ans["_xlevels"] = xlevels
    if method == "class":
        ans["_ylevels"] = init["ylevels"]
    ans["_rpart_class"] = "rpart"
    return ans


def tfun(x: np.ndarray[Any, np.dtype[Any]] | pd.Series) -> list[bool] | bool:
    if isinstance(x, np.ndarray) and x.ndim == 2:
        is_ord: bool = hasattr(x, 'cat') and x.cat.ordered
        return [is_ord] * x.shape[1]
    else:
        if isinstance(x, pd.Series):
            return hasattr(x, 'cat') and x.cat.ordered
        return False

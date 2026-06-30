from __future__ import annotations

from typing import Any

import re

import numpy as np
import pandas as pd

from .na_rpart import na_rpart


def _strip_backtick(name: str) -> str:
    return re.sub(r'^`(.*)`$', r'\1', name.strip())


def _parse_formula_terms(formula: str, data: pd.DataFrame) -> tuple[str, list[str], list[int]]:
    """Parse a simple R-style formula 'y ~ x1 + x2' or 'y ~ .'.

    Only main-effects formulas are supported (matching what rpart itself
    accepts); ':'/'*' interaction terms are flagged via order=2 so the
    caller can raise "Trees cannot handle interaction terms", exactly as
    rpart.R does after building the terms object.
    """
    if '~' not in formula:
        raise ValueError("a 'formula' argument is required")
    lhs, rhs = formula.split('~', 1)
    response_name = _strip_backtick(lhs)
    rhs = rhs.strip()
    if rhs == '.':
        term_labels = [c for c in data.columns if c != response_name]
        order = [1] * len(term_labels)
        return response_name, term_labels, order

    raw_terms = [t.strip() for t in rhs.split('+')]
    raw_terms = [t for t in raw_terms if t and t != '1']
    term_labels = []
    order = []
    for t in raw_terms:
        order.append(2 if (':' in t or '*' in t) else 1)
        term_labels.append(_strip_backtick(t))
    return response_name, term_labels, order


def _build_model_frame(
    formula: str,
    data: pd.DataFrame | None,
    weights: Any = None,
    subset: Any = None,
    na_action: Any = None,
) -> pd.DataFrame:
    """Python equivalent of R's eval.parent(stats::model.frame(...)) call
    inside rpart.R: build a model frame from a formula string and a data
    frame, recording the same metadata (.attrs['terms']/'response'/'weights')
    that the rest of the package (rpart.py, rpart_matrix.py, na_rpart.py)
    expects.
    """
    if not isinstance(data, pd.DataFrame):
        raise ValueError("a 'data' argument is required when 'model' is not a DataFrame")

    response_name, term_labels, order = _parse_formula_terms(formula, data)
    missing_vars = [v for v in [response_name] + term_labels if v not in data.columns]
    if missing_vars:
        raise KeyError(f"variable(s) {missing_vars!r} not found in data")

    work = data
    weights_arr: np.ndarray[Any, np.dtype[np.float64]] | None = None
    if weights is not None:
        if isinstance(weights, str):
            if weights not in data.columns:
                raise KeyError(f"weights variable {weights!r} not found in data")
            weights_arr = data[weights].to_numpy(dtype=float)
        else:
            weights_arr = np.asarray(weights, dtype=float)

    if subset is not None:
        subset_arr = np.asarray(subset)
        if subset_arr.dtype == bool:
            mask = subset_arr
        else:
            mask = np.zeros(len(data), dtype=bool)
            mask[subset_arr.astype(int)] = True
        work = data.loc[mask]
        if weights_arr is not None and len(weights_arr) == len(data):
            weights_arr = weights_arr[mask]

    cols: dict[str, Any] = {response_name: work[response_name]}
    for lab in term_labels:
        cols[lab] = work[lab]
    m = pd.DataFrame(cols, index=work.index)

    # .getXlevels(Terms, m) equivalent: only columns that are ALREADY a
    # pandas categorical ("factor") contribute xlevels; bare strings are
    # coerced to numeric codes later in rpart.matrix but do not get an
    # xlevels entry, matching R's is.factor()-only behaviour.
    xlevels: dict[str, list[Any]] = {}
    for lab in term_labels:
        col = m[lab]
        if isinstance(col.dtype, pd.CategoricalDtype):
            xlevels[lab] = list(col.cat.categories)

    terms_meta: dict[str, Any] = {
        "order": order,
        "term.labels": term_labels,
        "variables": [response_name] + term_labels,
        "response": 1,
    }
    if xlevels:
        terms_meta["xlevels"] = xlevels

    m.attrs["terms"] = terms_meta
    response_col = m[response_name]
    m.attrs["response"] = (
        response_col if isinstance(response_col.dtype, pd.CategoricalDtype) else response_col.to_numpy()
    )
    if weights_arr is not None:
        m.attrs["weights"] = np.asarray(weights_arr, dtype=float)

    na_fn = na_action if na_action is not None else na_rpart
    m = na_fn(m)
    return m


def model_frame_rpart(formula: dict[str, Any], **kwargs: Any) -> Any:
    m: pd.DataFrame | None = formula.get('model')
    if m is not None:
        return m
    oc: dict[str, Any] = formula['call']
    if str(oc.get('func_name', ''))[:7] == 'predict':
        m = oc['newdata']
        if m.attrs.get('terms') is None:
            m = na_rpart(m)
        return m

    # Equivalent of R's eval(oc): re-run the original rpart() call recorded
    # on the fitted object, overriding subset/method exactly as
    # model.frame.rpart.R does.  (R's implementation likewise re-invokes
    # rpart() here rather than returning a bare data.frame -- preserved
    # for logical equivalence with the original package.)
    oc = dict(oc)
    if 'subset' not in oc or oc.get('subset') is None:
        where = formula.get('where')
        if where is not None and hasattr(where, 'index'):
            oc['subset'] = list(where.index)
    oc['method'] = formula.get('method')

    from .rpart import rpart as _rpart_fit

    call_kwargs: dict[str, Any] = {"data": oc.get('data')}
    if oc.get('weights') is not None:
        call_kwargs['weights'] = oc['weights']
    if oc.get('subset') is not None:
        call_kwargs['subset'] = oc['subset']
    if oc.get('method') is not None:
        call_kwargs['method'] = oc['method']
    return _rpart_fit(oc.get('formula'), **call_kwargs)

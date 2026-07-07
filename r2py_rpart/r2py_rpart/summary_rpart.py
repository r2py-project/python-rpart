from __future__ import annotations

from typing import Any

import builtins
import sys
import contextlib
import decimal
import math
import numpy as np

from .plotcp import r_format_double

_MISSING = object()


def _r_signif(x: float, digits: int) -> float:
    """Python port of R's ``signif(x, digits)``: round ``x`` to ``digits``
    significant decimal figures."""
    x = float(x)
    if x == 0 or not math.isfinite(x):
        return x
    exp = math.floor(math.log10(abs(x)))
    d = int(digits) - int(exp) - 1
    return round(x, d)


def _r_format_signif(x: float, digits: int) -> str:
    """Equivalent of R's ``format(signif(x, digits))`` for a single scalar.

    summary.rpart.R calls ``format(signif(value, digits))`` scalar-by-
    scalar (inside `for` loops, once per cut-point/complexity-param/
    improve= value) -- never on a whole vector at once -- so each value's
    fixed-vs-scientific notation decision is independent of every other
    value's. ``r_format_double`` (plotcp.py) already implements that
    per-value fixed-vs-scientific character-width decision for an
    already-rounded double; this just supplies the ``signif()`` rounding
    step R performs first.
    """
    return r_format_double(_r_signif(x, digits))


def _sig_info(x: float, digits: int) -> tuple[int, int]:
    """Return ``(nsig, e)`` for ``x`` rounded to ``digits`` significant
    figures: ``nsig`` is the number of significant digits actually present
    after rounding (trailing zeros trimmed -- e.g. ``signif(0.001, 5)`` has
    only 1, not 5), and ``e`` is the base-10 exponent of its leading
    significant digit. ``x`` must be nonzero and finite.
    """
    r = abs(_r_signif(x, digits))
    _sign, ds, exponent = decimal.Decimal(repr(r)).normalize().as_tuple()
    if ds == (0,):
        return 1, 0
    nsig = len(ds)
    e = exponent + nsig - 1
    return nsig, e


def _format_scientific(v: float, mantissa_dec: int) -> str:
    """Format ``v`` in scientific notation with a fixed ``mantissa_dec``
    mantissa-decimal width and a (>=2-digit) exponent, R-style."""
    if v != v:
        return 'NaN'
    if v in (float('inf'), float('-inf')):
        return '-Inf' if v < 0 else 'Inf'
    sign = '-' if v < 0 else ''
    a = abs(v)
    if a == 0:
        mant = '0' if mantissa_dec == 0 else '0.' + '0' * mantissa_dec
        return f'{sign}{mant}e+00'
    e = math.floor(math.log10(a))
    mantissa = a / (10.0 ** e)
    mant_str = f'{mantissa:.{mantissa_dec}f}'
    if float(mant_str) >= 10:
        mantissa /= 10
        e += 1
        mant_str = f'{mantissa:.{mantissa_dec}f}'
    exp_sign = '+' if e >= 0 else '-'
    return f'{sign}{mant_str}e{exp_sign}{abs(int(e)):02d}'


def _r_format_matrix_column(values: Any, digits: int) -> list[str]:
    """Reproduce R's ``format()``/``print.default(matrix, digits=)`` rule
    for *one column* of a numeric matrix: a shared number of decimal
    places (fixed notation) or a shared scientific-notation mantissa
    width, chosen once for the whole column by comparing total character
    width (narrower wins; ties favor fixed -- the same rule
    ``r_format_double`` uses for a single value, but here applied
    collectively across every element of the column, since R's
    ``print.default`` computes one shared format per matrix column rather
    than formatting each cell independently). This is deliberately
    *different* from ``_r_format_signif`` (used for the per-node cut-
    point/complexity-param/improve= values), which formats one scalar at a
    time with no cross-element alignment -- matching summary.rpart.R's own
    call sites exactly (``print(x$cptable, ...)`` on a whole matrix vs.
    ``format(signif(x$splits[i, ...], digits))`` inside a `for` loop).
    """
    arr = np.asarray(values, dtype=float)
    finite_nonzero = [float(v) for v in arr if math.isfinite(v) and v != 0]
    if finite_nonzero:
        infos = [_sig_info(v, digits) for v in finite_nonzero]
        dec = max(0, max(nsig - 1 - e for nsig, e in infos))
        mantissa_dec = max(0, max(nsig - 1 for nsig, e in infos))
    else:
        dec = 0
        mantissa_dec = 0

    def _fixed(v: float) -> str:
        if v != v:
            return 'NaN'
        if v in (float('inf'), float('-inf')):
            return '-Inf' if v < 0 else 'Inf'
        return f'{v:.{dec}f}'

    fixed_strs = [_fixed(float(v)) for v in arr]
    sci_strs = [_format_scientific(float(v), mantissa_dec) for v in arr]
    fixed_width = max((len(s) for s in fixed_strs), default=0)
    sci_width = max((len(s) for s in sci_strs), default=0)
    strs = sci_strs if sci_width < fixed_width else fixed_strs
    width = max((len(s) for s in strs), default=0)
    return [s.rjust(width) for s in strs]


def _r_format_cptable(cptable: Any, digits: int) -> str:
    """Render ``cptable`` (a pandas DataFrame mirroring R's numeric
    ``cptable`` matrix) the way R's ``print.default(x$cptable,
    digits=digits)`` would: each column formatted as a shared-precision
    unit (see ``_r_format_matrix_column``), right-justified to
    ``max(header, data)`` width, columns separated by a single space, and
    integer row labels left-justified in their own unlabeled column --
    replicating ``print.default``'s matrix layout in full, rather than
    ``pandas.DataFrame.to_string()``'s independent per-column default
    precision (which ignores ``digits`` entirely).
    """
    columns = [str(c) for c in cptable.columns]
    row_labels = [str(v) for v in cptable.index]
    col_blocks = []
    for col_name, orig_col in zip(columns, cptable.columns):
        formatted = _r_format_matrix_column(cptable[orig_col].to_numpy(dtype=float), digits)
        width = max([len(col_name)] + [len(s) for s in formatted])
        header = col_name.rjust(width)
        cells = [s.rjust(width) for s in formatted]
        col_blocks.append((header, cells))
    rowlabel_width = max((len(r) for r in row_labels), default=0)
    lines = [' ' * rowlabel_width + ''.join(' ' + h for h, _ in col_blocks)]
    for i in range(len(row_labels)):
        row = row_labels[i].ljust(rowlabel_width) + ''.join(' ' + cells[i] for _, cells in col_blocks)
        lines.append(row)
    return '\n'.join(lines)


def _print_r_named_vector(names: list[str], values: list[str], width: int = 80) -> None:
    """Print ``names``/``values`` (already stringified) the way R's own
    ``print.default`` renders a named numeric vector -- e.g.
    ``print(temp[temp > 0])`` in summary.rpart.R -- as a shared column
    width (max over every name's/value's own width), entries
    right-justified, separated by a single space, with a trailing space
    on each line, wrapping across successive (names-line, values-line)
    pairs once a line would exceed ``width`` characters (mirroring R's
    console default, ``getOption("width")``).
    """
    if not names:
        return
    col_w = max(max(len(n) for n in names), max(len(v) for v in values))
    per_line = max(1, width // (col_w + 1))
    for start in range(0, len(names), per_line):
        chunk_n = names[start:start + per_line]
        chunk_v = values[start:start + per_line]
        print(' '.join(n.rjust(col_w) for n in chunk_n) + ' ')
        print(' '.join(v.rjust(col_w) for v in chunk_v) + ' ')


def _cp_gt(a: Any, b: Any) -> Any:
    """``a > b``, mirroring R's own ``>`` semantics when ``b`` (the
    user-supplied ``cp=``) is a non-numeric *string*: R silently coerces
    the numeric side to character and does a (nonsensical, but
    non-erroring) lexicographic comparison, rather than raising. numpy
    instead raises ``UFuncTypeError`` (a ``TypeError`` subclass) for a
    float64-vs-str comparison -- fall back to R's own coercion behavior
    only in that specific case, so python doesn't raise where R wouldn't
    (see test_summary_rpart_cp_non_numeric_string_known_gap). Any other
    comparison failure (e.g. ``cp=None``, which both R and python legitimately
    raise for -- see test_summary_rpart_cp_none_raises) is left to propagate
    normally, unlike the string case.
    """
    if not isinstance(b, str):
        return a > b
    if np.ndim(a) == 0:
        return str(a) > b
    return np.array([str(v) > b for v in np.asarray(a)])


def _cp_lt(a: Any, b: Any) -> Any:
    """See ``_cp_gt``; the ``<`` counterpart."""
    if not isinstance(b, str):
        return a < b
    if np.ndim(a) == 0:
        return str(a) < b
    return np.array([str(v) < b for v in np.asarray(a)])


def summary_rpart(object: dict[str, Any], cp: float = 0, digits: int | None = None, file: str | object = _MISSING, **kwargs) -> dict[str, Any]:
    if not isinstance(object, dict) or 'frame' not in object:
        raise ValueError('Not a legitimate "rpart" object')
    x = object
    if digits is None:
        digits = 7
    # R's print.default (reached via `print(x$cptable, digits=digits)`,
    # the first digits-driven formatting call in summary.rpart.R) rejects
    # digits < 1 outright ("invalid printing digits N"); python's
    # `f'{v:.{digits}g}'`-style formatting used to treat digits=0 as a
    # silently-valid precision-1 request, so mirror R's validation
    # explicitly here (see test_summary_rpart_digits_zero_known_gap).
    if isinstance(digits, (int, float)) and not isinstance(digits, bool):
        if digits != digits:  # NaN
            raise ValueError('invalid printing digits NA')
        if digits < 1:
            raise ValueError(f'invalid printing digits {int(digits)}')
    # R's `ff$complexity[i] < cp`/`parent.cp > cp` comparisons against
    # `cp=NA` produce NA logical values, and R's scalar `if (NA)` then
    # raises "missing value where TRUE/FALSE needed"; python's NaN
    # comparisons are simply always False (no exception), so without this
    # explicit check summary_rpart would silently run to completion
    # instead (see test_summary_rpart_cp_nan_known_gap).
    if isinstance(cp, float) and cp != cp:
        raise ValueError('missing value where TRUE/FALSE needed')
    def _do_summary():
        if x.get('call') is not None:
            print('Call:')
            print(repr(x.get('call')))
        omit = x.get('na.action')
        ff = x['frame']
        n = ff['n'].values
        # `na.action` here is a dict with keys {'indices', 'names', 'class'}
        # (see na_rpart.py) mirroring R's na.action "omit" object, whose
        # *R*-side length() is the count of dropped observations -- not
        # the (fixed, ==3) number of dict keys, which `len(omit)` would
        # wrongly report on the dict itself.
        _n_omit = len(omit['indices']) if omit is not None else 0
        if omit is not None and _n_omit > 0:
            _noun = 'observation' if _n_omit == 1 else 'observations'
            _naprint_str = f'{_n_omit} {_noun} deleted due to missingness'
            print(f'  n={n[0]} ({_naprint_str})\n')
        else:
            print(f'  n={n[0]}\n')
        _cptable = x.get('cptable')
        if _cptable is None:
            # In R, `bad$cptable <- NULL` removes the list element, so
            # `x$cptable` evaluates to NULL and `print(NULL, digits=...)`
            # prints the literal text "NULL" without error; mirror that
            # instead of letting a plain dict subscript raise KeyError
            # (see test_summary_rpart_missing_cptable_key_known_gap).
            print('NULL')
        else:
            print(_r_format_cptable(_cptable, digits))
        temp_vi = x.get('variable.importance')
        if temp_vi is not None:
            temp_vi_rounded = np.round(100 * temp_vi / temp_vi.sum()).astype(int)
            if hasattr(temp_vi_rounded, 'values'):
                _arr = temp_vi_rounded.values
                _idx = temp_vi_rounded.index
            else:
                _arr = temp_vi_rounded
                _idx = np.arange(len(_arr))
            if np.any(_arr > 0):
                print('\nVariable importance')
                _mask = _arr > 0
                _names = [str(n) for n in np.asarray(_idx)[_mask]]
                _values = [str(int(v)) for v in _arr[_mask]]
                _print_r_named_vector(_names, _values)
        ff = x['frame']
        ylevel = object.get('_ylevels')
        id = ff.index.astype(int).values
        parent_id = np.where(id == 1, 1, id // 2)
        _id_to_pos = {v: i for i, v in enumerate(id)}
        parent_cp = np.array([ff['complexity'].values[_id_to_pos[pid]] for pid in parent_id])
        _rows_candidates = np.where(_cp_gt(parent_cp, cp))[0]
        if len(_rows_candidates) > 0:
            rows = _rows_candidates[np.argsort(id[_rows_candidates])]
        else:
            rows = np.array([0], dtype=int)
        is_leaf = ff['var'].values == '<leaf>'
        index = np.cumsum(np.concatenate([[1], ff['ncompete'].values + ff['nsurrogate'].values + (~is_leaf).astype(int)])) - 1
        if not np.all(is_leaf):
            sname = list(x['splits'].index) if hasattr(x['splits'], 'index') else [str(i) for i in range(x['splits'].shape[0])]
            splits_arr = np.asarray(x['splits'])
            temp_col = splits_arr[:, 1].astype(float)
            cuts = [''] * splits_arr.shape[0]
            for i in range(len(cuts)):
                _tc = temp_col[i]
                if _tc == -1:
                    _val = splits_arr[i, 3]
                    _val_fmt = _r_format_signif(_val, digits)
                    cuts[i] = f'< {_val_fmt}'
                elif _tc == 1:
                    _val = splits_arr[i, 3]
                    _val_fmt = _r_format_signif(_val, digits)
                    cuts[i] = f'< {_val_fmt}'
                else:
                    _ncat = int(_tc)
                    _csplit_idx = int(splits_arr[i, 3]) - 1
                    _csplit_vals = x['csplit'][_csplit_idx, :_ncat]
                    _lut = ['L', '-', 'R']
                    _letters = ''.join(_lut[int(v) - 1] for v in _csplit_vals)
                    cuts[i] = f'splits as {_letters}'
            # NB: `object` here must be builtins.object -- the `object`
            # parameter name shadows the builtin type in this function's scope.
            cuts = np.array(cuts, dtype=builtins.object)
            _continuous_mask = temp_col < 2
            if np.any(_continuous_mask):
                _widths = np.array([len(s) for s in cuts[_continuous_mask]])
                _max_w = int(_widths.max()) if len(_widths) > 0 else 0
                _formatted = np.array([s.ljust(_max_w) for s in cuts[_continuous_mask]])
                cuts_copy = cuts.copy()
                cuts_copy[_continuous_mask] = _formatted
                cuts = cuts_copy
            cuts = np.array([
                s + (',') if temp_col[_ci] >= 2 else
                s + (' to the right,') if temp_col[_ci] == 1 else
                s + (' to the left, ')
                for _ci, s in enumerate(cuts)
            ], dtype=builtins.object)
        else:
            sname = []
            cuts = np.array([], dtype=builtins.object)
            temp_col = np.array([], dtype=float)
        if 'yval2' in ff.columns:
            # ff['yval2'] holds one array per row (object-dtype column);
            # stack the selected rows into a true 2-D matrix, since
            # summary_func implementations index yval.shape[1].
            _tmp = np.array([np.asarray(v, dtype=float) for v in ff['yval2'].values[rows]])
        else:
            _tmp = ff['yval'].values[rows]
        tprint = x['functions']['summary'](_tmp, ff['dev'].values[rows], ff['wt'].values[rows], ylevel, digits)
        for ii in range(len(rows)):
            i = rows[ii]
            nn = ff['n'].values[i]
            print(f'\nNode number {id[i]}: {nn} observations', end='')
            if _cp_lt(ff['complexity'].values[i], cp) or is_leaf[i]:
                print()
            else:
                _cp_fmt = _r_format_signif(ff['complexity'].values[i], digits)
                print(f',    complexity param={_cp_fmt}')
            _tp = tprint[ii] if hasattr(tprint, '__getitem__') else str(tprint)
            print(f'{_tp}')
            if _cp_gt(ff['complexity'].values[i], cp) and not is_leaf[i]:
                sons = np.array([2 * id[i], 2 * id[i] + 1], dtype=int)
                sons_n = np.array([ff['n'].values[_id_to_pos[s]] if s in _id_to_pos else np.nan for s in sons])
                print(f'  left son={sons[0]} ({int(sons_n[0])} obs) right son={sons[1]} ({int(sons_n[1])} obs)', end='')
                j_miss = nn - (sons_n[0] + sons_n[1])
                if j_miss > 1:
                    print(f', {int(j_miss)} observations remain')
                elif j_miss == 1:
                    print(', 1 observation remains')
                else:
                    print()
                print('  Primary splits:')
                _ncompete_i = ff['ncompete'].values[i]
                j = np.arange(index[i], index[i] + 1 + _ncompete_i, dtype=int)
                _cuts_j = cuts[j]
                _widths_j = np.array([len(s) for s in _cuts_j])
                if np.all(_widths_j < 25):
                    _max_w_j = int(_widths_j.max()) if len(_widths_j) > 0 else 0
                    _temp_j = np.array([s.ljust(_max_w_j) for s in _cuts_j])
                else:
                    _temp_j = _cuts_j
                _snames_j = [sname[jj] for jj in j]
                _max_name_w = max((len(s) for s in _snames_j), default=0)
                _improve_arr = splits_arr[j, 2]
                _missing_arr = nn - splits_arr[j, 0]
                for _k in range(len(j)):
                    _sn = _snames_j[_k].ljust(_max_name_w)
                    _ct = _temp_j[_k]
                    _imp_fmt = _r_format_signif(_improve_arr[_k], digits)
                    _miss_int = int(_missing_arr[_k])
                    print(f'      {_sn} {_ct} improve={_imp_fmt}, ({_miss_int} missing)')
                _nsurrogate_i = ff['nsurrogate'].values[i]
                if _nsurrogate_i > 0:
                    print('  Surrogate splits:')
                    j2 = np.arange(1 + index[i] + _ncompete_i, 1 + index[i] + _ncompete_i + _nsurrogate_i, dtype=int)
                    _agree = splits_arr[j2, 2]
                    _cuts_j2 = cuts[j2]
                    _widths_j2 = np.array([len(s) for s in _cuts_j2])
                    if np.all(_widths_j2 < 25):
                        _max_w_j2 = int(_widths_j2.max()) if len(_widths_j2) > 0 else 0
                        _temp_j2 = np.array([s.ljust(_max_w_j2) for s in _cuts_j2])
                    else:
                        _temp_j2 = _cuts_j2
                    _snames_j2 = [sname[jj] for jj in j2]
                    _max_name_w2 = max((len(s) for s in _snames_j2), default=0)
                    _adj = splits_arr[j2, 4]
                    _split_count = splits_arr[j2, 0]
                    for _k in range(len(j2)):
                        _sn2 = _snames_j2[_k].ljust(_max_name_w2)
                        _ct2 = _temp_j2[_k]
                        _agree_fmt = f'{round(float(_agree[_k]), 3)}'
                        _adj_fmt = f'{round(float(_adj[_k]), 3)}'
                        _sc_int = int(_split_count[_k])
                        print(f'      {_sn2} {_ct2} agree={_agree_fmt}, adj={_adj_fmt}, ({_sc_int} split)')
        print()
    if file is not _MISSING:
        with open(file, 'w') as _fh, contextlib.redirect_stdout(_fh):
            _do_summary()
    else:
        _do_summary()
    return x

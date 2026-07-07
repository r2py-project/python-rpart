from __future__ import annotations

import decimal
from typing import Any

import numpy as np
import pandas as pd


def _validate_digits(digits: Any) -> int:
    """Mirror R's ``format()``/``print()`` validation of the ``digits=``
    argument. R's C-level formatter requires ``digits`` to coerce to a
    whole number ``>= 1``: a non-numeric value coerces to ``NA`` via
    ``as.integer()``, and both ``NA`` and any value ``< 1`` (including 0)
    raise "invalid value ... for 'digits' argument". This is stricter than
    Python's own ``'%g'``-style format-spec mini-language, which happily
    accepts (and silently clamps) a requested precision of 0.
    """
    try:
        digits_f = float(digits)
    except (TypeError, ValueError):
        raise ValueError(f"invalid 'digits' value: {digits!r}") from None
    if digits_f != digits_f:  # NaN
        raise ValueError(f"invalid 'digits' value: {digits!r}")
    digits_int = int(digits_f)
    if digits_int < 1:
        raise ValueError(f"invalid 'digits' value: {digits_int}")
    return digits_int


def _r_format(v: float, digits: int) -> str:
    """Render a single double the way R's ``format(x, digits=N)`` would,
    reproducing R's fixed-vs-scientific notation decision.

    This is a digits-parameter variant of the width-comparison technique
    used by ``r_format_double`` in ``plotcp.py`` (R picks whichever of the
    two candidate renderings is narrower -- governed by ``options(scipen)``,
    default 0 -- with ties favoring fixed notation). It cannot simply reuse
    that helper as-is: ``r_format_double`` assumes its input has already
    been rounded upstream (via ``signif()``, as ``plotcp.R`` does) and
    derives its significant-digit count from Python's own shortest
    round-trip ``repr()``. Here we must instead reproduce R's
    ``format(x, digits=N)`` semantics on a value that has *not* been
    pre-rounded: R never hides/truncates the integer part to fit within
    ``digits`` significant figures (e.g. ``format(1355, digits=1)`` is
    ``"1355"``, not ``"1000"`` or scientific ``"1e+03"``), while it still
    trims insignificant trailing (fractional) zeros a plain
    round-to-N-decimal-places would otherwise introduce (e.g.
    ``format(1, digits=5)`` is ``"1"``, not ``"1.0000"``).

    Concretely: the *fixed* candidate rounds to ``max(digits - left, 0)``
    decimal places, where ``left`` is the number of digits left of the
    decimal point -- this never reduces the integer part -- and then trims
    trailing fractional zeros. The *scientific* candidate rounds to exactly
    ``digits`` significant figures and trims trailing zeros from the
    mantissa (via ``Decimal.normalize()``). Whichever rendering is narrower
    (character-width-wise) wins; ties favor fixed.
    """
    v = float(v)  # normalize numpy scalar types (e.g. np.float64) to plain
    # python float, since their repr() (e.g. "np.float64(0.0003)" on
    # numpy>=2.0) is not a valid decimal.Decimal literal.
    if v != v:  # NaN
        return "NaN"
    if v in (float("inf"), float("-inf")):
        return "-Inf" if v < 0 else "Inf"
    if v == 0:
        return "0"

    sign = "-" if v < 0 else ""
    a = abs(v)

    with decimal.localcontext() as ctx:
        ctx.prec = 60  # plenty of headroom for wide decimal-place rounding

        d = decimal.Decimal(repr(a))
        d_norm = d.normalize()
        _sign0, digits0, exp0 = d_norm.as_tuple()
        if digits0 == (0,):
            return "0"
        nsig0 = len(digits0)
        lead_exp = exp0 + nsig0 - 1  # power of ten of the leading sig. digit
        left = lead_exp + 1  # count of digits left of the decimal point

        # -- fixed candidate: round to `max(digits - left, 0)` decimal
        #    places (never truncates the integer part), then trim any
        #    trailing fractional zeros the rounding introduced.
        rgt = max(digits - left, 0)
        quant = decimal.Decimal(1).scaleb(-rgt)
        fixed_dec = d.quantize(quant, rounding=decimal.ROUND_HALF_EVEN)
        fixed_str = format(fixed_dec, "f")
        if "." in fixed_str:
            fixed_str = fixed_str.rstrip("0").rstrip(".")

        # -- scientific candidate: round to exactly `digits` significant
        #    figures, then normalize away trailing mantissa zeros -- this
        #    is why e.g. format(100000, digits=6) is "1e+05", not
        #    "1.00000e+05".
        sci_exp = lead_exp - (digits - 1)
        squant = decimal.Decimal(1).scaleb(sci_exp)
        sci_dec = d.quantize(squant, rounding=decimal.ROUND_HALF_EVEN).normalize()
        _sign1, sdigits, sexp = sci_dec.as_tuple()
        if sdigits == (0,):
            sci = "0e+00"
        else:
            nsig = len(sdigits)
            sci_lead_exp = sexp + nsig - 1
            digit_str = "".join(str(dd) for dd in sdigits)
            mantissa = digit_str if nsig == 1 else f"{digit_str[0]}.{digit_str[1:]}"
            exp_sign = "+" if sci_lead_exp >= 0 else "-"
            sci = f"{mantissa}e{exp_sign}{abs(sci_lead_exp):02d}"

    # Narrower representation wins; ties favor fixed (R's scipen=0 default).
    return sign + (fixed_str if len(fixed_str) <= len(sci) else sci)


def _format_cptable_lines(cptable: Any, digits: int) -> str:
    """Render the cp-table the way R's ``print(x$cptable, digits=digits)``
    (R's plain matrix printer, ``print.default``) does: each column is
    right-justified to a width equal to the wider of its header label and
    its widest formatted value, columns are separated by a single space,
    and row labels form their own (also right-justified) leading column.

    Each value is formatted independently via ``_r_format`` (matching
    printcp.py's pre-existing per-value approach) -- R's ``format()``
    applied to a >1-row column instead aligns decimal places *across* all
    of that column's rows, which is a distinct, documented, permanent
    formatting gap (see test_printcp_positive.py's module docstring, gap
    4) that this does not attempt to close. What this function does fix is
    the column *padding*/layout convention itself, which -- as demonstrated
    by a single-row cptable, where there is nothing to cross-row
    decimal-align -- previously differed from R's even when every printed
    value was textually identical.
    """
    if isinstance(cptable, pd.DataFrame):
        col_names = [str(c) for c in cptable.columns]
        row_names = [str(i) for i in cptable.index]
        values = cptable.to_numpy(dtype=float)
    else:
        arr = np.asarray(cptable, dtype=float)
        all_cols = ['CP', 'nsplit', 'rel error', 'xerror', 'xstd']
        col_names = all_cols[:arr.shape[1]]
        row_names = [str(i + 1) for i in range(arr.shape[0])]
        values = arr

    nrow, ncol = values.shape
    cells = [[_r_format(values[i, j], digits) for j in range(ncol)] for i in range(nrow)]
    col_widths = [
        max([len(col_names[j])] + [len(cells[i][j]) for i in range(nrow)])
        for j in range(ncol)
    ]
    row_width = max((len(r) for r in row_names), default=0)

    header = " " * row_width + "".join(
        " " + col_names[j].rjust(col_widths[j]) for j in range(ncol)
    )
    lines = [header]
    for i in range(nrow):
        line = row_names[i].rjust(row_width) + "".join(
            " " + cells[i][j].rjust(col_widths[j]) for j in range(ncol)
        )
        lines.append(line)
    return "\n".join(lines)


def printcp(x: dict, digits: int = 5) -> np.ndarray | pd.DataFrame:
    # R's default is `getOption("digits") - 2L`; in a stock R session
    # `getOption("digits")` is 7, so the effective default is 5 (not the
    # previously-hardcoded 2).
    if not (isinstance(x, dict) and x.get('_rpart_class') == 'rpart'):
        raise TypeError('x must be an "rpart" object')
    digits = _validate_digits(digits)
    _METHOD_HEADER = {
        'anova':   '\nRegression tree:\n',
        'class':   '\nClassification tree:\n',
        'poisson': '\nRates regression tree:\n',
        'exp':     '\nSurvival regression tree:\n',
    }
    print(_METHOD_HEADER[x['method']], end='')
    cl = x.get('call')
    if cl is not None:
        print(repr(cl))
        print()
    frame = x['frame']
    leaves = frame['var'] == '<leaf>'
    used = frame['var'][~leaves].unique()
    # R's `used <- unique(frame$var[!leaves])` is `character(0)` (not NULL)
    # for a root-only/no-split tree, and `is.null(character(0))` is FALSE --
    # so R always prints this header (with an empty body for a root-only
    # tree). Only skip the block when `used` itself is genuinely absent.
    if used is not None:
        print('Variables actually used in tree construction:')
        print(sorted(str(v) for v in used))
        print()
    dev0 = frame['dev'].iloc[0]
    n0 = frame['n'].iloc[0]
    print(
        f'Root node error: {_r_format(dev0, digits)}/{n0} = '
        f'{_r_format(dev0 / n0, digits)}',
    )
    print()
    n = x['frame']['n']
    omit = x.get('na.action')
    # `na.action` is a dict {'indices', 'names', 'class'} (see na_rpart.py);
    # the observation count is len(omit['indices']), not len(omit) (which
    # would wrongly always be 3, the fixed number of dict keys).
    n_omit = len(omit['indices']) if omit is not None else 0
    if omit is not None and n_omit > 0:
        noun = 'observation' if n_omit == 1 else 'observations'
        naprint_str = f'{n_omit} {noun} deleted due to missingness'
        print(f'n={n.iloc[0]} ({naprint_str})', end='\n\n')
    else:
        print(f'n={n.iloc[0]}', end='\n\n')
    cptable = x['cptable']
    print(_format_cptable_lines(cptable, digits))
    return x['cptable']

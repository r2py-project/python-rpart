from __future__ import annotations

import decimal
from typing import Any

import numpy as np

from .labels_rpart import labels_rpart
from .prune_rpart import prune_rpart
from .zzz import tree_depth

_print_rpart_MISSING = object()

# R's format()/print() functions default their own `digits=` argument to
# `getOption("digits")`, which is 7 in a stock R session (and is what every
# test in this suite runs under -- none of them call `options(digits=...)`).
# print.rpart.R's generic (non-classification) branch calls
# `format(signif(frame$dev, digits))` / `format(signif(frame$yval, digits))`
# -- note that `digits` (the *user-supplied* print.rpart argument) is only
# ever passed to `signif()`, never to the outer `format()` call, so the
# vector-alignment step below always uses R's *session* digits option (7),
# regardless of what digits= the caller passed to print_rpart(). This is
# why, e.g., `print(z, digits=15)` still only ever shows 5 aligned decimals
# for a `dev` column that needs 5 decimals at digits=7: signif() gets 15
# sig figs, but format()'s own alignment/decimal-count logic is capped at 7.
_R_FORMAT_DEFAULT_DIGITS = 7


def _nsig_and_lead_exp(a: float, digits: int) -> tuple[int, int]:
    """For a positive finite value `a`, return `(nsig, lead_exp)`: the
    number of significant digits needed to exactly round-trip `a` (capped
    at `digits`), and the base-10 exponent of `a`'s leading significant
    digit.

    This is the per-element primitive R's `format()` uses (see
    `r_format_vector` below): rather than always showing exactly `digits`
    significant figures, R shows *fewer* whenever a value's shortest
    round-trip decimal representation already needs fewer (e.g. a value
    that has just been `signif()`-rounded to a "clean" decimal, or an
    already-integral value) -- this mirrors plotcp.py's `r_format_double`,
    which makes the same "shortest round-trip repr, via Python's own
    shortest-round-trip `repr()`" choice for a single value; here it's
    reused across a whole vector so every element can be aligned to a
    shared number of decimal places (see `r_format_vector`).
    """
    d = decimal.Decimal(repr(a)).normalize()
    _sign_d, digits_tuple, exponent = d.as_tuple()
    if digits_tuple == (0,):
        return 0, 0
    nsig_natural = len(digits_tuple)
    lead_exp = exponent + nsig_natural - 1
    return min(nsig_natural, digits), lead_exp


def r_format_vector(values: 'list[float] | np.ndarray[Any, np.dtype[np.float64]]', digits: int, nsmall: int = 0) -> list[str]:
    """Reimplement R's `format(x, digits=, nsmall=)` for a 1-D sequence of
    doubles, the way print.rpart.R's generic (non-classification) `yval`/
    `dev` columns rely on: pick *one* common number of decimal places for
    the *whole* vector (so every value's decimal point lines up), rather
    than formatting each element independently and merely right-justifying
    by string width (which is all `f'{v:.{digits}g}'` + `.rjust()` gives
    you, and is what this Python port used to do -- see print_rpart.py's
    git history / the test suite's documented "gap (a)").

    Per element, the number of decimal places *needed* is derived from the
    minimal significant-digit count required to round-trip that element
    (capped at `digits`) via `_nsig_and_lead_exp` -- not simply `digits`
    itself, since e.g. an already-"clean" value like 1000.0 or 23.5 needs
    fewer decimals than a value like 0.8695652 does at the same `digits`.
    The common decimal count is the max of all per-element needs (and of
    `nsmall`, a hard floor); every element is then re-rounded from its
    *original* (not pre-truncated) value at that common decimal count, so
    values with more inherent precision than their own per-element need
    still gain the correct extra digits from alignment (verified against
    R's `format()` directly -- see e.g. `format(c(1355.23456789, 0.001),
    digits=3)` => `"1355.235    0.001"`, not `"1355.000    0.001"`).

    Finally, as a whole-vector decision (R's `scipen=0` default), if the
    fixed-notation candidate above would be *wider* (its longest formatted
    element) than a shared scientific-notation candidate -- one common
    mantissa-decimal count (`max(nsig) - 1` across the vector) and a
    common >=2-digit exponent width, the same "narrower wins, ties favor
    fixed" rule `plotcp.py`'s `r_format_double` applies to a single value
    -- every element switches to scientific notation instead. This is
    needed e.g. for a `dev` column spanning ~7e-4 to ~2e2: aligning that
    many orders of magnitude in fixed notation needs 10 decimal places
    (14-character values like "170.9327000000"), wider than the 12-
    character scientific form ("1.709327e+02"), so R (and this function)
    render the whole column in scientific notation instead.
    """
    vals = [float(v) for v in values]
    decimals_needed: list[int] = []
    nsig_needed: list[int] = []
    for v in vals:
        if v != v or v in (float('inf'), float('-inf')) or v == 0:
            continue
        nsig, lead_exp = _nsig_and_lead_exp(abs(v), digits)
        decimals_needed.append(max(0, nsig - 1 - lead_exp))
        nsig_needed.append(nsig)
    common_decimals = max([nsmall] + decimals_needed)
    nsig_common = max([1] + nsig_needed)
    mantissa_decimals = nsig_common - 1

    def _special(v: float) -> 'str | None':
        if v != v:
            return 'NaN'
        if v in (float('inf'), float('-inf')):
            return '-Inf' if v < 0 else 'Inf'
        return None

    def _fmt_fixed(v: float) -> str:
        special = _special(v)
        return special if special is not None else f'{v:.{common_decimals}f}'

    def _fmt_sci(v: float) -> str:
        special = _special(v)
        if special is not None:
            return special
        if v == 0:
            mantissa = '0' if mantissa_decimals == 0 else '0.' + '0' * mantissa_decimals
            return f'{mantissa}e+00'
        sign = '-' if v < 0 else ''
        a = abs(v)
        exp = int(np.floor(np.log10(a)))
        mantissa_val = a / (10.0 ** exp)
        mantissa_str = f'{mantissa_val:.{mantissa_decimals}f}'
        # rounding the mantissa can carry it up to "10.0..."; bump the
        # exponent and reformat when that happens.
        if float(mantissa_str) >= 10:
            exp += 1
            mantissa_val = a / (10.0 ** exp)
            mantissa_str = f'{mantissa_val:.{mantissa_decimals}f}'
        exp_sign = '+' if exp >= 0 else '-'
        return f'{sign}{mantissa_str}e{exp_sign}{abs(exp):02d}'

    fixed_strs = [_fmt_fixed(v) for v in vals]
    sci_strs = [_fmt_sci(v) for v in vals]
    fixed_width = max((len(s) for s in fixed_strs), default=0)
    sci_width = max((len(s) for s in sci_strs), default=0)

    strs = fixed_strs if fixed_width <= sci_width else sci_strs
    width = max((len(s) for s in strs), default=0)
    return [s.rjust(width) for s in strs]


def print_rpart(x: dict[str, Any], minlength: int = 0, spaces: int = 2, cp: 'float | object' = _print_rpart_MISSING, digits: int = 7, nsmall: 'int | None' = None, **kwargs) -> dict[str, Any]:
    if not isinstance(x, dict) or 'frame' not in x:
        raise TypeError('Not a legitimate "rpart" object')

    if nsmall is None:
        nsmall = min(20, digits)

    if cp is not _print_rpart_MISSING:
        # R: `if (!missing(cp)) x <- prune.rpart(x, cp = cp)`. When `cp` is
        # an empty vector (R's `cp=list()`/`cp=numeric(0)`), R's internal
        # `ff$complexity <= cp` vectorized comparison against a zero-length
        # `cp` silently produces a zero-length logical result, so no rows
        # ever get pruned and prune.rpart() returns `x` unchanged -- no
        # error (confirmed empirically: `print(z, cp=list())` prints the
        # full, unpruned tree). prune_rpart.py's translation instead feeds
        # an empty `cp` straight into a numpy comparison against the
        # (non-empty) complexity column, which raises a broadcasting
        # ValueError rather than silently yielding "nothing to prune". Since
        # prune_rpart() itself is out of scope for this fix, special-case
        # an empty `cp` here (the only place print_rpart calls it) to match
        # R's actual behavior: skip pruning entirely rather than erroring.
        try:
            cp_is_empty = len(cp) == 0  # type: ignore[arg-type]
        except TypeError:
            cp_is_empty = False
        if not cp_is_empty:
            x = prune_rpart(x, cp=cp)

    frame = x['frame']
    ylevel = x.get('_ylevels', None)  # attr(x, 'ylevels')
    node = frame.index.astype(float).values  # as.numeric(row.names(frame))
    depth = tree_depth(node)  # integer-valued float array, 0-based depths

    # Build indent string and per-depth indent vector
    # R: indent <- paste(rep(' ', spaces * 32L), collapse = '')
    indent_full: str = ' ' * (spaces * 32)

    if len(node) > 1:
        # R: indent <- substring(indent, 1L, spaces * seq(depth))
        # seq(depth) = 1:max(depth), so iterate d from 1 to max_depth inclusive
        max_depth = int(depth.max())
        # indent_vec[i] corresponds to R's indent[i+1] (0-based), prefix of length spaces*(i+1)
        indent_vec: list[str] = [indent_full[:spaces * d] for d in range(1, max_depth + 1)]
        # R: paste0(c('', indent[depth]), format(node), ')')
        # indent[depth] selects indent by 1-based depth index; depth is 0-based here
        # depth==0 -> '' (root), depth==d -> indent_vec[d-1]
        depth_int = depth.astype(int)
        selected_indent = [''] + indent_vec  # index 0 -> '', index d -> indent_vec[d-1]
        node_indent = [selected_indent[d] for d in depth_int]
        # format(node): right-pad all node IDs to the same width
        node_strs = [str(int(v)) for v in node]
        max_node_width = max(len(s) for s in node_strs)
        node_strs_padded = [s.rjust(max_node_width) for s in node_strs]
        indent = [ni + ns + ')' for ni, ns in zip(node_indent, node_strs_padded)]
    else:
        node_strs = [str(int(v)) for v in node]
        indent = [ns + ')' for ns in node_strs]

    # Get print function from x['functions']
    tfun = None
    if 'functions' in x and x['functions'] is not None:
        tfun = x['functions'].get('print', None)

    # Compute yval strings
    if tfun is not None:
        if 'yval2' not in frame.columns or frame['yval2'] is None:
            yval = tfun(frame['yval'].to_numpy(), ylevel, digits, nsmall)
        else:
            # frame['yval2'] holds one array per row (object-dtype Series);
            # stack via tolist()+np.array() into a true 2-D matrix, since
            # print_func/summary_func implementations index yval.shape[1].
            yval2_mat = np.array(frame['yval2'].tolist(), dtype=np.float64)
            yval = tfun(yval2_mat, ylevel, digits, nsmall)
    else:
        # format(signif(frame$yval, digits)) -- `digits` (the print_rpart
        # caller's argument) is only ever passed to signif() in R; the
        # outer format() call always uses R's *session* digits option
        # (_R_FORMAT_DEFAULT_DIGITS), which is why r_format_vector below
        # is called with that constant rather than the caller's `digits`.
        yval_arr = frame['yval'].values.astype(float)
        def _signif(arr: np.ndarray, d: int) -> np.ndarray:
            # R's signif(arr, d): round each element to d significant
            # digits. Each element generally needs a *different* number of
            # decimal places (decimals = d - 1 - floor(log10(|x|))), so
            # numpy.round's single scalar `decimals` argument cannot do
            # this in one vectorized call -- np.round(arr, decimals_array)
            # raises "only integer scalar arrays can be converted to a
            # scalar index" for any array with more than one distinct
            # magnitude. Round element-by-element instead.
            decimals = d - 1 - np.floor(np.log10(np.abs(np.where(arr == 0, 1.0, arr)))).astype(int)
            return np.array(
                [0.0 if v == 0 else np.round(v, int(dec)) for v, dec in zip(arr, decimals)],
                dtype=float,
            )
        yval_rounded = _signif(yval_arr, digits)
        yval = r_format_vector(yval_rounded, _R_FORMAT_DEFAULT_DIGITS, nsmall=0)

    # term: ' ' for non-leaf, '*' for leaf
    term = [' '] * len(depth)
    var_values = frame['var'].values
    for i in range(len(var_values)):
        if var_values[i] == '<leaf>':
            term[i] = '*'

    # z = labels(x, digits=digits, minlength=minlength, ...)
    z = labels_rpart(x, digits=digits, minlength=minlength, **kwargs)

    n = frame['n'].values

    # format(signif(frame$dev, digits))
    # Per-element signif() rounding: see the identical fix/comment on the
    # `_signif` helper above -- np.round's `decimals` argument must be a
    # scalar, so an array of per-element decimal counts (one distinct value
    # per order of magnitude in dev_arr) cannot be passed to a single
    # vectorized np.round call.
    dev_arr = frame['dev'].values.astype(float)
    _dev_decimals = digits - 1 - np.floor(np.log10(np.abs(np.where(dev_arr == 0, 1.0, dev_arr)))).astype(int)
    dev_rounded = np.array(
        [0.0 if v == 0 else np.round(v, int(dec)) for v, dec in zip(dev_arr, _dev_decimals)],
        dtype=float,
    )
    # As above (yval): the outer format() in R's `format(signif(frame$dev,
    # digits))` always uses R's session digits option, not the caller's
    # `digits` argument -- only signif() (dev_rounded, above) uses it.
    dev_strs_padded = r_format_vector(dev_rounded, _R_FORMAT_DEFAULT_DIGITS, nsmall=0)

    # z <- paste(indent, z, n, format(signif(frame$dev, digits)), yval, term)
    n_strs = [str(int(v)) for v in n]
    z_lines = [
        ' '.join([indent[i], str(z[i]), n_strs[i], dev_strs_padded[i], str(yval[i]), term[i]])
        for i in range(len(n))
    ]

    # Print header
    omit = x.get('na.action', None)
    n0 = int(n[0])
    # `na.action` is a dict {'indices', 'names', 'class'} (see na_rpart.py);
    # the observation count is len(omit['indices']), not len(omit) (which
    # would wrongly always be 3, the fixed number of dict keys).
    n_omit = len(omit['indices']) if omit is not None else 0
    if omit is not None and n_omit > 0:
        noun = 'observation' if n_omit == 1 else 'observations'
        naprint_str = f'{n_omit} {noun} deleted due to missingness'
        print(f'n={n0} ({naprint_str})\n')
    else:
        # R: cat("n=", n[1L], "\n\n") uses cat's default sep=" ", giving
        # "n= <n> \n\n" (space after "n=" and before the trailing newline).
        print(f'n= {n0} \n')

    if x.get('method', '') == 'class':
        print('node), split, n, loss, yval, (yprob)')
    else:
        print('node), split, n, deviance, yval')
    print('      * denotes terminal node\n')

    print('\n'.join(z_lines))

    return x

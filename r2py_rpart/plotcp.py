from __future__ import annotations

import decimal
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker


def r_format_double(v: float) -> str:
    """Render a single double the way R's ``as.character()``/``format()``
    would, i.e. reproduce R's fixed-vs-scientific notation decision.

    R picks between the two candidate renderings by comparing their
    *character width* (governed by ``options(scipen)``, default 0): the
    narrower representation wins, and ties favor fixed notation. This is a
    fundamentally different rule from Python's ``str()``/``repr()``, which
    switches to scientific notation purely based on the value's exponent
    (e.g. < -4), independent of how many significant digits are present.

    The number of significant digits used for each candidate is the
    minimal count needed to round-trip the double exactly, obtained via
    Python's own shortest-round-trip ``repr()``. That matches what R's
    formatter converges on for values that have already been rounded to a
    handful of significant figures via ``signif()`` (as ``plotcp.R`` always
    does before formatting its ``cp`` axis labels) -- this helper is meant
    to be reusable wherever a Python port needs an R-``format()``-equivalent
    string for an already-rounded double (see e.g. printcp.py, print_rpart.py,
    summary_rpart.py, rpart_class.py, which have the same formatting gap for
    other call sites and may adopt this helper in follow-up fixes).
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

    d = decimal.Decimal(repr(a)).normalize()
    _sign_d, digits, exponent = d.as_tuple()
    if digits == (0,):
        return "0"
    nsig = len(digits)
    digit_str = "".join(str(dd) for dd in digits)
    # power-of-ten exponent of the leading significant digit
    lead_exp = exponent + nsig - 1

    # -- scientific candidate: d[.ddd]e±EE (R uses >= 2 exponent digits) --
    mantissa = digit_str if nsig == 1 else f"{digit_str[0]}.{digit_str[1:]}"
    exp_sign = "+" if lead_exp >= 0 else "-"
    sci = f"{mantissa}e{exp_sign}{abs(lead_exp):02d}"

    # -- fixed candidate --
    if lead_exp >= 0:
        if nsig <= lead_exp + 1:
            fixed = digit_str + "0" * (lead_exp + 1 - nsig)
        else:
            fixed = digit_str[: lead_exp + 1] + "." + digit_str[lead_exp + 1 :]
    else:
        fixed = "0." + "0" * (-lead_exp - 1) + digit_str

    # Narrower representation wins; ties favor fixed (R's scipen=0 default).
    return sign + (fixed if len(fixed) <= len(sci) else sci)


def plotcp(x: dict[str, Any], minline: bool = True, lty: int | str = 3, col: int | str = 1, upper: str = 'size', ax: plt.Axes | None = None, **kwargs: Any) -> None:
    _UPPER_CHOICES = ('size', 'splits', 'none')
    if upper not in _UPPER_CHOICES:
        raise ValueError(f"'upper' must be one of {_UPPER_CHOICES!r}; got {upper!r}")
    if not isinstance(x, dict) or 'cptable' not in x:
        raise TypeError('Not a legitimate "rpart" object')
    p_rpart = x['cptable']
    if hasattr(p_rpart, 'to_numpy'):
        p_rpart = p_rpart.to_numpy()
    if p_rpart.ndim < 2 or p_rpart.shape[1] < 5:
        raise ValueError("'cptable' does not contain cross-validation results")
    xstd = p_rpart[:, 4]
    xerror = p_rpart[:, 3]
    nsplit = p_rpart[:, 1]
    ns = np.arange(1, len(nsplit) + 1)
    cp0 = p_rpart[:, 0]
    cp = np.sqrt(cp0 * np.concatenate([[np.inf], cp0[:-1]]))
    if 'ylim' not in kwargs:
        ylim = (float(np.min(xerror - xstd)) - 0.1, float(np.max(xerror + xstd)) + 0.1)
    else:
        ylim = kwargs.pop('ylim')
    # R's base graphics `lty=` parameter accepts any of the integers 0-6
    # (cycling/clamping beyond that range) as well as their named aliases
    # ("blank","solid","dashed","dotted","dotdash","longdash","twodash"); all
    # seven are always valid and never raise in R (see `?par`'s "lty" entry).
    # matplotlib's Line2D/axhline, by contrast, only accepts a small fixed
    # set of linestyle spellings ('-','--','-.',':','None') or an explicit
    # (offset, (on_off_seq)) dash tuple -- it has no "5"/"6"/"dotdash"/etc.
    # built-in, and raises for anything else. Map every one of R's 7
    # int/name codes to a valid matplotlib linestyle (using custom dash
    # tuples for the two codes -- 5/"longdash" and 6/"twodash" -- that have
    # no direct matplotlib named equivalent) so that any lty value R itself
    # accepts is likewise accepted here, instead of silently falling through
    # to an unmapped raw int/name that matplotlib then rejects.
    _lty_map = {
        0: 'None', 'blank': 'None',
        1: '-', 'solid': '-',
        2: '--', 'dashed': '--',
        3: ':', 'dotted': ':',
        4: '-.', 'dotdash': '-.',
        5: (0, (10, 6)), 'longdash': (0, (10, 6)),
        6: (0, (5, 2, 2, 2)), 'twodash': (0, (5, 2, 2, 2)),
    }
    _col_map = {1: 'black', 2: 'red', 3: 'green', 4: 'blue'}
    linestyle = _lty_map.get(lty, lty)
    color = _col_map.get(col, 'black') if isinstance(col, int) else col
    if ax is None:
        _fig, ax = plt.subplots()
    ax.plot(ns, xerror, marker='o', linestyle='-', color=color)
    ax.set_ylim(*ylim)
    ax.set_xlabel('cp')
    ax.set_ylabel('X-val Relative Error')
    for spine in ax.spines.values():
        spine.set_visible(True)
    ax.yaxis.set_major_locator(matplotlib.ticker.AutoLocator())
    ax.vlines(x=ns, ymin=xerror - xstd, ymax=xerror + xstd, colors=color)
    def _signif(arr: np.ndarray[Any, np.dtype[np.float64]], digits: int) -> np.ndarray[Any, np.dtype[np.float64]]:
        arr = np.asarray(arr, dtype=float)
        with np.errstate(divide='ignore', invalid='ignore'):
            magnitude = np.floor(np.log10(np.abs(arr)))
            magnitude = np.where(np.isfinite(magnitude), magnitude, 0)
        # np.round()'s `decimals` must be a scalar, not a per-element array,
        # so round element-by-element (each value needs its own decimal
        # count to hit `digits` significant figures).
        decimals = (digits - 1 - magnitude).astype(int)
        return np.array([round(float(v), int(d)) for v, d in zip(arr, decimals)])
    cp_labels = [r_format_double(v) for v in _signif(cp, 2)]
    ax.set_xticks(ns)
    ax.set_xticklabels(cp_labels)
    if upper in ('size', 'splits'):
        ax_top = ax.twiny()
        ax_top.set_xlim(ax.get_xlim())
        ax_top.set_xticks(ns)
        if upper == 'size':
            ax_top.set_xticklabels([str(int(v) + 1) for v in nsplit])
            ax_top.set_xlabel('size of tree', labelpad=12)
        else:
            ax_top.set_xticklabels([str(int(v)) for v in nsplit])
            ax_top.set_xlabel('number of splits', labelpad=12)
    minpos = int(np.min(np.where(xerror == np.min(xerror))))
    if minline:
        ax.axhline(y=float((xerror + xstd)[minpos]), linestyle=linestyle, color=color)
    return None

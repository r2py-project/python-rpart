from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker



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
    _lty_map = {1: '-', 2: '--', 3: ':', 4: '-.'}
    _col_map = {1: 'black', 2: 'red', 3: 'green', 4: 'blue'}
    linestyle = _lty_map.get(lty, lty) if isinstance(lty, int) else lty
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
    cp_labels = [str(v) for v in _signif(cp, 2)]
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

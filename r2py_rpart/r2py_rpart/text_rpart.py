from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.axes
import warnings
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.transforms as mtransforms
from typing import Any, Callable
_text_rpart_MISSING = object()



def oval(middlex: float, middley: float, a: float, b: float, ax: matplotlib.axes.Axes, bg: str) -> None:
    theta: np.ndarray[Any, np.dtype[np.float64]] = np.linspace(0, 2 * np.pi, 61)
    newx: np.ndarray[Any, np.dtype[np.float64]] = middlex + a * np.cos(theta)
    newy: np.ndarray[Any, np.dtype[np.float64]] = middley + b * np.sin(theta)
    ax.fill(newx, newy, facecolor=bg, edgecolor='black')


def rectangle(middlex: float, middley: float, a: float, b: float, ax: matplotlib.axes.Axes, bg: str) -> None:
    newx: np.ndarray[Any, np.dtype[np.float64]] = middlex + np.array([a, a, -a, -a])
    newy: np.ndarray[Any, np.dtype[np.float64]] = middley + np.array([b, -b, -b, b])
    ax.fill(newx, newy, facecolor=bg, edgecolor='black')


def text_rpart(x: dict[str, Any], splits: bool = True, label: Any = _text_rpart_MISSING, FUN: Callable[..., None] | None = None, all: bool = False, pretty: Any = _text_rpart_MISSING, digits: int | None = None, use_n: bool = False, fancy: bool = False, fwidth: float = 0.8, fheight: float = 0.8, bg: str | None = None, minlength: int = 1, ax: 'matplotlib.axes.Axes | None' = None, cxy: 'tuple[float, float] | list[float] | None' = None, **kwargs: Any) -> None:
    if not isinstance(x, dict) or x.get('__class__') != 'rpart':
        raise ValueError('Not a legitimate "rpart" object')
    frame = x['frame']
    if len(frame) <= 1:
        raise ValueError('fit is not a tree, just a root')

    if label is not _text_rpart_MISSING:
        warnings.warn("argument 'label' is no longer used")

    if digits is None:
        digits = 4  # equivalent to getOption('digits') - 3L with digits default 7

    ylevels: list[str] | None = x.get('ylevels', None)

    # Resolve ax and cxy (analogues of par('cxy') and par('bg'))
    if ax is None:
        ax = plt.gca()
    if bg is None:
        rgba = ax.get_facecolor()
        bg = mcolors.to_hex(rgba, keep_alpha=True)

    # Compute cxy: character width and height in data (user) coordinates
    # Equivalent to par('cxy') in R
    if cxy is None:
        try:
            fig = ax.get_figure()
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            fontsize_pt: float = plt.rcParams['font.size']
            dpi: float = fig.get_dpi()
            char_height_px: float = fontsize_pt * dpi / 72.0
            char_width_px: float = char_height_px * 0.6
            inv_transform = ax.transData.inverted()
            origin_disp = ax.transData.transform((0.0, 0.0))
            x_shift_disp = origin_disp + np.array([char_width_px, 0.0])
            y_shift_disp = origin_disp + np.array([0.0, char_height_px])
            char_width_data: float = float(inv_transform.transform(x_shift_disp)[0] - inv_transform.transform(origin_disp)[0])
            char_height_data: float = float(inv_transform.transform(y_shift_disp)[1] - inv_transform.transform(origin_disp)[1])
            cxy = (char_width_data, char_height_data)
        except Exception:
            cxy = (0.02, 0.04)  # fallback stub

    # If srt==90 is passed, swap cxy (rev(cxy) in R)
    srt: Any = kwargs.get('srt', None)
    if srt is not None and srt == 90:
        cxy = (cxy[1], cxy[0])

    # Default FUN: draw text using matplotlib ax.text (vectorised wrapper)
    def _default_fun(xs: np.ndarray[Any, np.dtype[np.float64]], ys: np.ndarray[Any, np.dtype[np.float64]], labels: list[str | None], _ax: 'matplotlib.axes.Axes' = ax, **kw: Any) -> None:
        for xi, yi, lab in zip(xs, ys, labels):
            if lab is not None and not (isinstance(lab, float) and np.isnan(lab)):
                _ax.text(float(xi), float(yi), str(lab), **kw)

    if FUN is None:
        FUN = _default_fun

    # Compute node IDs from frame index (row.names(frame))
    node: np.ndarray[Any, np.dtype[np.int64]] = frame.index.astype(float).values.astype(np.int64)
    node_lookup: dict[int, int] = {int(v): i for i, v in enumerate(node)}

    is_left: np.ndarray[Any, np.dtype[np.bool_]] = (node % 2 == 0)
    node_left: np.ndarray[Any, np.dtype[np.int64]] = node[is_left]
    # parent: 0-based index of each left node's parent in node array
    parent: np.ndarray[Any, np.dtype[np.int64]] = np.array(
        [node_lookup.get(int(v) // 2, -1) for v in node_left], dtype=np.int64
    )

    # Compute plot coordinates
    xy: dict[str, np.ndarray[Any, np.dtype[np.float64]]] = rpartco(x)

    if splits:
        # left.child and right.child: 0-based indices into node array (-1 if not found)
        left_child: np.ndarray[Any, np.dtype[np.int64]] = np.array(
            [node_lookup.get(int(n) * 2, -1) for n in node], dtype=np.int64
        )
        right_child: np.ndarray[Any, np.dtype[np.int64]] = np.array(
            [node_lookup.get(int(n) * 2 + 1, -1) for n in node], dtype=np.int64
        )

        # Determine which labels()/labels_rpart() call to use based on pretty/minlength sentinels
        if pretty is not _text_rpart_MISSING and minlength == 1:
            # R: if (!missing(pretty) && missing(minlength)) labels(x, pretty = pretty)
            rows: list[str] = labels_rpart(x, pretty=pretty)
        else:
            rows = labels_rpart(x, minlength=minlength)

        if fancy:
            xytmp: dict[str, np.ndarray[Any, np.dtype[np.float64]]] = rpart_branch(
                x=xy['x'], y=xy['y'], node=node
            )
            # xytmp['x'] has shape (5, n_left); rows 0..3 are branch segment points
            # leftptx = midpoint of rows 0 and 1 (0-based)
            leftptx: np.ndarray[Any, np.dtype[np.float64]] = (xytmp['x'][1, :] + xytmp['x'][0, :]) / 2.0
            leftpty: np.ndarray[Any, np.dtype[np.float64]] = (xytmp['y'][1, :] + xytmp['y'][0, :]) / 2.0
            # rightptx = midpoint of rows 2 and 3
            rightptx: np.ndarray[Any, np.dtype[np.float64]] = (xytmp['x'][2, :] + xytmp['x'][3, :]) / 2.0
            rightpty: np.ndarray[Any, np.dtype[np.float64]] = (xytmp['y'][2, :] + xytmp['y'][3, :]) / 2.0

            # left.child[!is.na(left.child)]: filter valid (non -1) left child indices
            left_child_of_left: np.ndarray[Any, np.dtype[np.int64]] = left_child[is_left]
            valid_left_mask: np.ndarray[Any, np.dtype[np.bool_]] = (left_child_of_left != -1)
            left_labels: list[str] = [rows[i] for i in left_child_of_left[valid_left_mask]]
            FUN(leftptx[valid_left_mask], leftpty[valid_left_mask] + 0.52 * cxy[1], left_labels, **kwargs)

            right_child_of_left: np.ndarray[Any, np.dtype[np.int64]] = right_child[is_left]
            valid_right_mask: np.ndarray[Any, np.dtype[np.bool_]] = (right_child_of_left != -1)
            right_labels: list[str] = [rows[i] for i in right_child_of_left[valid_right_mask]]
            FUN(rightptx[valid_right_mask], rightpty[valid_right_mask] - 0.52 * cxy[1], right_labels, **kwargs)
        else:
            # plain mode: place split labels above each node
            # rows[left_child]: index into rows using 0-based left_child; -1 entries become None
            labels_for_nodes: list[str | None] = [
                rows[i] if i != -1 else None for i in left_child
            ]
            FUN(xy['x'], xy['y'] + 0.5 * cxy[1], labels_for_nodes, **kwargs)

    # Determine which nodes are leaves
    leaves: np.ndarray[Any, np.dtype[np.bool_]] = (
        np.ones(len(frame), dtype=bool) if all
        else (frame['var'].values == '<leaf>')
    )

    # Compute stat: call the method-specific text closure
    yval2 = frame.get('yval2', None) if hasattr(frame, 'get') else None
    # yval2 is a 2D array if present; yval is a 1D array
    if yval2 is not None and hasattr(yval2, 'ndim') and yval2.ndim == 2:
        yval_arg = yval2[leaves, :]
    elif yval2 is not None and hasattr(yval2, '__len__'):
        yval_arg = yval2[leaves]
    else:
        yval_arg = frame['yval'].values[leaves]

    stat: list[str] = x['functions']['text'](
        yval=yval_arg,
        dev=frame['dev'].values[leaves],
        wt=frame['wt'].values[leaves],
        ylevel=ylevels,
        digits=digits,
        n=frame['n'].values[leaves],
        use_n=use_n,
    )

    if fancy:
        # Check if bg is transparent; if so, default to 'white'
        try:
            rgba_bg = mcolors.to_rgba(bg)
            if rgba_bg[3] < 1.0:
                bg = 'white'
        except ValueError:
            bg = 'white'

        # Compute bounding box of stat strings for sizing ovals and rectangles
        stat_bb: dict[str, np.ndarray[Any, np.dtype[np.int_]]] = string_bounding_box(stat)
        maxlen: int = int(np.max(stat_bb['columns'])) + 1
        maxht: int = int(np.max(stat_bb['rows'])) + 1

        a_length: float = fwidth * cxy[0] * maxlen if fwidth < 1 else fwidth * cxy[0]
        b_length: float = fheight * cxy[1] * maxht if fheight < 1 else fheight * cxy[1]

        # Draw ovals around internal (non-leaf) nodes
        # parent contains 0-based indices into node array for left nodes' parents
        # R: for (i in parent) oval(xy$x[i], xy$y[i], ...)
        # parent is 0-based; use directly for indexing xy['x'] and xy['y']
        for i in parent:
            if i >= 0:
                oval(xy['x'][i], xy['y'][i], np.sqrt(2) * a_length / 2.0, np.sqrt(2) * b_length / 2.0, ax=ax, bg=bg)

        # Draw rectangles around leaf nodes
        # child: 0-based indices of leaf nodes in the node array
        leaf_node_ids: np.ndarray[Any, np.dtype[np.int64]] = node[frame['var'].values == '<leaf>']
        child: np.ndarray[Any, np.dtype[np.int64]] = np.array(
            [node_lookup.get(int(v), -1) for v in leaf_node_ids], dtype=np.int64
        )
        for i in child:
            if i >= 0:
                rectangle(xy['x'][i], xy['y'][i], a_length / 2.0, b_length / 2.0, ax=ax, bg=bg)

    # Draw stat labels at leaf positions
    if fancy:
        FUN(xy['x'][leaves], xy['y'][leaves] + 0.5 * cxy[1], stat, **kwargs)
    else:
        FUN(xy['x'][leaves], xy['y'][leaves] - 0.5 * cxy[1], stat, ha='center', **kwargs)

    return None

from __future__ import annotations

from typing import Any

import numpy as np

from .labels_rpart import labels_rpart
from .prune_rpart import prune_rpart
from .zzz import tree_depth

_print_rpart_MISSING = object()



def print_rpart(x: dict[str, Any], minlength: int = 0, spaces: int = 2, cp: 'float | object' = _print_rpart_MISSING, digits: int = 7, nsmall: 'int | None' = None, **kwargs) -> dict[str, Any]:
    if not isinstance(x, dict) or 'frame' not in x:
        raise TypeError('Not a legitimate "rpart" object')

    if nsmall is None:
        nsmall = min(20, digits)

    if cp is not _print_rpart_MISSING:
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
        # format(signif(frame$yval, digits))
        yval_arr = frame['yval'].values.astype(float)
        def _signif(arr: np.ndarray, d: int) -> np.ndarray:
            return np.where(arr == 0, 0.0,
                            np.round(arr, d - 1 - np.floor(np.log10(np.abs(np.where(arr == 0, 1.0, arr)))).astype(int)))
        yval_rounded = _signif(yval_arr, digits)
        yval_strs = [f'{v:.{digits}g}' for v in yval_rounded]
        max_yval_width = max(len(s) for s in yval_strs)
        yval = [s.rjust(max_yval_width) for s in yval_strs]

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
    dev_arr = frame['dev'].values.astype(float)
    dev_rounded = np.where(dev_arr == 0, 0.0,
                           np.round(dev_arr, digits - 1 - np.floor(np.log10(np.abs(np.where(dev_arr == 0, 1.0, dev_arr)))).astype(int)))
    dev_strs = [f'{v:.{digits}g}' for v in dev_rounded]
    max_dev_width = max(len(s) for s in dev_strs)
    dev_strs_padded = [s.rjust(max_dev_width) for s in dev_strs]

    # z <- paste(indent, z, n, format(signif(frame$dev, digits)), yval, term)
    n_strs = [str(int(v)) for v in n]
    z_lines = [
        ' '.join([indent[i], str(z[i]), n_strs[i], dev_strs_padded[i], str(yval[i]), term[i]])
        for i in range(len(n))
    ]

    # Print header
    omit = x.get('na.action', None)
    n0 = int(n[0])
    if omit is not None and len(omit) > 0:
        n_omit = len(omit)
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

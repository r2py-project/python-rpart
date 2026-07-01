from __future__ import annotations

from typing import Any

import warnings
import numpy as np

from .formatg import formatg

_labels_rpart_MISSING = object()



def labels_rpart(object: dict[str, Any], digits: int = 4, minlength: 'int | object' = _labels_rpart_MISSING, pretty: Any = _labels_rpart_MISSING, collapse: bool = True, **kwargs) -> 'list[str] | np.ndarray[Any, np.dtype[np.str_]]':
    # Resolve minlength/pretty dependency (R: missing(minlength) && !missing(pretty))
    if minlength is _labels_rpart_MISSING and pretty is not _labels_rpart_MISSING:
        if pretty is None:
            minlength = 1
        elif isinstance(pretty, bool):
            minlength = 4 if pretty else 0
        else:
            minlength = 0
    if minlength is _labels_rpart_MISSING:
        minlength = 1  # R default value for minlength

    ff = object['frame']
    n = len(ff)
    if n == 1:
        return ['root']

    # object['splits'] is normally a pandas DataFrame (see rpart.py); the
    # numpy-style [rows, col] indexing below needs a plain ndarray.
    splits_arr = np.asarray(object['splits'])

    is_leaf = (ff['var'].values == '<leaf>')
    whichrow = ~is_leaf
    vnames = ff['var'].values[whichrow]  # variable names for non-leaf nodes

    # Build cumulative index into splits matrix.
    # R: index <- cumsum(c(1L, ff$ncompete + ff$nsurrogate + !is.leaf))
    # Result is 1-based; we convert to 0-based for numpy.
    per_node = ff['ncompete'].values + ff['nsurrogate'].values + (~is_leaf).astype(int)
    index = np.cumsum(np.concatenate([[1], per_node]))  # length n+1, 1-based
    index_0based = index - 1

    # R: irow <- index[c(whichrow, FALSE)]
    # Append FALSE to whichrow (length n) to make length n+1, then index into index (length n+1).
    # Equivalent: select index_0based at positions where whichrow is True.
    irow = index_0based[np.where(whichrow)[0]]  # 0-based row indices into splits array

    # R: ncat <- object$splits[irow, 2L]  (R col 2 = Python col 1, 0-based)
    ncat = splits_arr[irow, 1].astype(int)

    num_irow = len(irow)
    lsplit = [''] * num_irow
    rsplit = [''] * num_irow

    # Handle continuous splits (ncat < 2)
    if np.any(ncat < 2):
        # R: jrow <- irow[ncat < 2L]  -- 0-based row indices into splits for continuous splits
        jrow = irow[ncat < 2]
        # R: cutpoint <- formatg(object$splits[jrow, 4L], digits)  (R col 4 = Python col 3)
        cutpoint = formatg(splits_arr[jrow, 3], digits)
        continuous_mask = ncat < 2
        # R: temp1 <- (ifelse(ncat < 0, '< ', '>='))[ncat < 2L]
        temp1_full = np.where(ncat < 0, '< ', '>=')
        temp2_full = np.where(ncat < 0, '>=', '< ')
        temp1 = temp1_full[continuous_mask]
        temp2 = temp2_full[continuous_mask]
        cont_indices = np.where(continuous_mask)[0]
        for idx_i, cp in enumerate(cutpoint):
            lsplit[cont_indices[idx_i]] = temp1[idx_i] + cp
            rsplit[cont_indices[idx_i]] = temp2[idx_i] + cp

    # Handle categorical splits (ncat > 1)
    if np.any(ncat > 1):
        xlevels = object['_xlevels']  # dict: variable name -> list of level strings
        # jrow: indices into the ncat/irow arrays (not into splits) for categorical splits
        jrow_idx = np.where(ncat > 1)[0]
        # R: crow <- object$splits[irow[ncat > 1], 4L]  (R col 4 = Python col 3)
        # crow is 1-based row into csplit
        crow = splits_arr[irow[ncat > 1], 3].astype(int)
        # R: cindex <- (match(vnames, names(xlevels)))[ncat > 1]
        # 0-based index of each split vname into xlevels keys
        xlevel_names = list(xlevels.keys())
        xlevel_index = {name: i for i, name in enumerate(xlevel_names)}
        cindex_full = np.array([xlevel_index.get(v, -1) for v in vnames])
        cindex = cindex_full[ncat > 1]  # 0-based index into xlevel_values
        xlevel_values = list(xlevels.values())

        if minlength == 1:
            if np.any(ncat > 52):
                warnings.warn('more than 52 levels in a predicting factor, truncated for printout')
            # R: xlevels <- lapply(xlevels, function(z) c(letters, LETTERS)[pmin(seq_along(z), 52L)])
            # pmin(seq_along(z), 52L) is 1-based capped at 52; index into 52-element alphabet is min(i, 51) 0-based
            _alphabet = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
            xlevels_abbrev_values = [
                [_alphabet[min(i, 51)] for i in range(len(v))]
                for v in xlevel_values
            ]
        elif minlength > 1:
            # R: xlevels <- lapply(xlevels, abbreviate, minlength, ...)
            def _abbrev_one(s: str, target_len: int) -> str:
                s_stripped = s.replace(' ', '')
                if len(s_stripped) <= target_len:
                    return s_stripped
                result = list(s_stripped)
                # Priority 1: remove lowercase vowels right-to-left
                for i in range(len(result) - 1, -1, -1):
                    if sum(1 for c in result if c is not None) <= target_len:
                        break
                    if result[i] is not None and result[i] in 'aeiou':
                        result[i] = None
                # Priority 2: remove lowercase consonants right-to-left
                for i in range(len(result) - 1, -1, -1):
                    if sum(1 for c in result if c is not None) <= target_len:
                        break
                    if result[i] is not None and result[i].islower():
                        result[i] = None
                # Priority 3: remove uppercase letters right-to-left
                for i in range(len(result) - 1, -1, -1):
                    if sum(1 for c in result if c is not None) <= target_len:
                        break
                    if result[i] is not None and result[i].isupper():
                        result[i] = None
                return ''.join(c for c in result if c is not None)
            def _abbreviate_list(levels: list, ml: int) -> list:
                current_ml = ml
                while True:
                    abbrevs = [_abbrev_one(s, current_ml) for s in levels]
                    if len(set(abbrevs)) == len(abbrevs):
                        break
                    current_ml += 1
                return abbrevs
            xlevels_abbrev_values = [_abbreviate_list(v, minlength) for v in xlevel_values]
        else:
            # minlength == 0: no abbreviation
            xlevels_abbrev_values = xlevel_values

        for i in range(len(jrow_idx)):
            j = jrow_idx[i]  # index into lsplit/rsplit lists
            # crow[i] is 1-based row into csplit; convert to 0-based
            splits_row = object['csplit'][crow[i] - 1, :]
            # R: cl <- if (minlength == 1L) '' else ','
            cl = '' if minlength == 1 else ','
            levels_i = xlevels_abbrev_values[cindex[i]]
            levels_arr = np.array(levels_i)
            # object['csplit'] is padded out to `maxcat` columns (the
            # largest category count across ALL categorical predictors in
            # the fit, e.g. 10 for a 10-level "Country" variable even on a
            # row that actually encodes a 6-level "Type" split); padding
            # columns beyond a given variable's own level count are always
            # set to 2 ("-", i.e. "not used" -- see summary_rpart.py's
            # ['L','-','R'] mapping for csplit values {1,2,3}), so they
            # never match `== 1`/`== 3` below and are safe to drop. R's
            # `(xlevels[[cindex[i]]])[splits == 1L]` gets away with the
            # length mismatch only because R silently pads out-of-range
            # logical-index positions with NA rather than raising; numpy's
            # boolean indexing requires the mask and array to have the
            # exact same length, so the row must be truncated to the
            # variable's true level count first.
            splits_row = splits_row[:len(levels_arr)]
            # R: lsplit[j] <- paste((xlevels[[cindex[i]]])[splits == 1L], collapse = cl)
            lsplit[j] = cl.join(levels_arr[splits_row == 1].tolist())
            # R: rsplit[j] <- paste((xlevels[[cindex[i]]])[splits == 3L], collapse = cl)
            rsplit[j] = cl.join(levels_arr[splits_row == 3].tolist())

    # Handle collapse=FALSE: return a 2-column array (ltemp, rtemp) per frame row
    if not collapse:
        ltemp = ['<leaf>'] * n
        rtemp = ['<leaf>'] * n
        whichrow_indices = np.where(whichrow)[0]
        for k, idx in enumerate(whichrow_indices):
            ltemp[idx] = lsplit[k]
            rtemp[idx] = rsplit[k]
        return np.column_stack([ltemp, rtemp])

    # Prepend '=' for categorical splits (ncat >= 2), '' for continuous (ncat < 2)
    # R: lsplit <- paste0(ifelse(ncat < 2L, '', '='), lsplit)
    lsplit_arr = np.array(lsplit, dtype=str)
    rsplit_arr = np.array(rsplit, dtype=str)
    prefix = np.where(ncat < 2, '', '=')
    lsplit_arr = np.char.add(prefix, lsplit_arr)
    rsplit_arr = np.char.add(prefix, rsplit_arr)

    varname = vnames.astype(str)
    # R: node <- as.numeric(row.names(ff))
    # frame index holds node IDs (stored as strings in pandas index)
    node = np.array(ff.index.tolist(), dtype=int)

    # R: parent <- match(node %/% 2L, node[whichrow])
    # Returns 1-based position of parent in node[whichrow]; -1 if not found (root).
    non_leaf_nodes = node[whichrow]
    non_leaf_lookup = {int(v): i for i, v in enumerate(non_leaf_nodes)}
    parent_ids = node // 2
    parent = np.array([non_leaf_lookup.get(int(p), -1) for p in parent_ids])

    # R: odd <- as.logical(node %% 2L)  -- True for odd nodes (right children)
    odd = (node % 2 == 1)

    labels = [''] * n
    for k in range(n):
        p = parent[k]
        if k == 0:
            labels[k] = 'root'
        elif odd[k]:
            # Right child: varname[parent] + rsplit[parent]
            labels[k] = varname[p] + rsplit_arr[p]
        else:
            # Left child: varname[parent] + lsplit[parent]
            labels[k] = varname[p] + lsplit_arr[p]
    return labels

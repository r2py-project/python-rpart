# Conversion Guide: `match` (R to Python)

## 1. Overview of `match` in R

`match(x, table, nomatch = NA_integer_, incomparables = NULL)` returns an integer vector of the same length as `x`. Each element is the position (1-based index) of the **first** occurrence of the corresponding element of `x` in `table`, or `nomatch` (defaulting to `NA_integer_`) when no match is found.

Key properties:
- The result is always an integer vector of the same length as `x`.
- The default `nomatch = NA` means unmatched elements become `NA` (which in R behaves as a missing integer).
- When `nomatch = 0L` is supplied, unmatched elements become `0` instead of `NA`, which is idiomatic for boolean-style filtering (`result > 0L` tests membership).
- Indexing is 1-based in R.

---

## 2. Contextual Usage Analysis

Across the 35 call sites in this CSV the function is used in five recurring patterns:

| Pattern | Description | `nomatch` |
|---|---|---|
| **Index lookup** | Find where each element of `x` appears in `table`; use the resulting positions to index into another structure. | `NA` (default) |
| **Membership / existence test** | Use `result > 0L` or `result == 0L` to test set membership without caring about the actual position. | `0L` |
| **Parent lookup in a binary tree** | Given a node-id vector, find each node's parent by looking up `node %/% 2L` in the same vector. | `NA` (default) |
| **String-to-integer dispatch** | Map a character string to a positional integer that drives a `switch`-like branch (e.g. argument name validation). | `0L` or `NA` |
| **De-duplication / first-occurrence selection** | `match(unique(x), x)` returns the position of the first occurrence of each unique value in the original vector. | `NA` (default) |

The arguments are consistently integer or character vectors; no scalar-only context appears. Because every call site operates on vectors (node-id arrays, column-name arrays, etc.), NumPy-style vectorised operations are the correct translation target.

---

## 3. Python Conversion Strategy

The primary Python equivalent is **`numpy.searchsorted`** for sorted data and, more generally, a custom lookup built with **`numpy` array operations** or a **`pandas` `Index.get_indexer`** call for arbitrary ordering.

For the exact semantics of R's `match` — an unsorted lookup of `x` into `table` returning the first-match 1-based position — the most faithful and efficient approach is:

```python
import numpy as np

def r_match(x, table, nomatch=None):
    """
    Mimics R's match(x, table, nomatch=NA / nomatch=0).
    Returns a 0-based index array if nomatch=0 analogue is desired,
    or an array with np.nan for unmatched elements otherwise.

    Parameters
    ----------
    x       : array-like of values to look up
    table   : array-like to search in
    nomatch : value to return for unmatched entries.
              Use 0 to mimic R's nomatch=0L (membership-test pattern).
              Use np.nan (default) to mimic R's default nomatch=NA.

    Returns
    -------
    numpy array of int64, 1-based positions matching R's convention,
    or `nomatch` for elements not found.
    """
    x = np.asarray(x)
    table = np.asarray(table)
    # Build a lookup dict: value -> first 1-based position
    lookup = {}
    for i, v in enumerate(table):
        if v not in lookup:
            lookup[v] = i + 1          # 1-based
    result = np.array([lookup.get(v, nomatch if nomatch is not None else np.nan)
                       for v in x])
    return result
```

For **pandas-based** code the `pd.Index.get_loc` / `pd.Index.get_indexer` methods offer the same semantics with better performance on large arrays:

```python
import numpy as np
import pandas as pd

def r_match_pd(x, table, nomatch=0):
    idx = pd.Index(table)
    # get_indexer returns 0-based positions, -1 for not found
    pos0 = idx.get_indexer(x)          # 0-based, -1 = not found
    result = np.where(pos0 == -1, nomatch, pos0 + 1)  # convert to 1-based
    return result
```

Which variant to use depends on context:
- **Index lookups** that feed into further array indexing: use the 1-based result directly but subtract 1 before using it as a Python/NumPy 0-based index.
- **Membership tests** (`nomatch=0L` in R): compare the result array to `0` (or `-1` before converting) rather than converting to 1-based positions.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Name-to-position lookup for column filtering

**Locations:** `rpart/R/pred.rpart.R` — `pred.rpart` (line 13); `rpart/R/xpred.rpart.R` — `xpred.rpart` (line 56); `rpart/R/rpart.R` — `rpart` (line 87).

**Original R Context:**

```r
# pred.rpart.R line 13
# rownames(fit$splits) : character vector of split variable names
# colnames(x)          : character vector of predictor column names
# Result: integer vector; NA if a split variable is missing from x
vnum <- match(rownames(fit$splits), colnames(x))
if (any(is.na(vnum)))
    stop("Tree has variables not found in new data")

# rpart.R line 87
# names(xlevels): names of factor predictors
# colnames(X)   : all predictor column names
# nomatch=0 means absence returns 0, not NA
indx <- match(names(xlevels), colnames(X), nomatch=0)
cats[indx] <- ...          # only the matched positions (>0) are used

# xpred.rpart.R line 56
cats[match(names(xlevels), colnames(X))] <- unlist(lapply(xlevels, length))
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# --- pred.rpart pattern (nomatch -> NA, error if any missing) ---
split_names = list(fit_splits_index)     # rownames of splits matrix
col_names   = list(x.columns)           # colnames of predictor matrix

col_index = pd.Index(col_names)
# get_indexer returns 0-based; -1 means not found
vnum_0based = col_index.get_indexer(split_names)
if np.any(vnum_0based == -1):
    raise ValueError("Tree has variables not found in new data")
# vnum_0based is already 0-based, suitable for direct numpy indexing

# --- rpart.R line 87 pattern (nomatch=0, membership test) ---
xlevel_names = list(xlevels.keys())
indx_0based = col_index.get_indexer(xlevel_names)   # -1 = not found
matched = indx_0based[indx_0based != -1]            # drop non-matches
cats[matched] = np.array([len(v) for k, v in xlevels.items()
                           if col_index.get_loc(k) != -1
                          if k in col_index])
```

**Explanation:**
- `pd.Index.get_indexer` is the direct vectorised equivalent: it returns `-1` for no match (analogous to R's `nomatch=0L`).
- R's result is 1-based; NumPy/pandas results are 0-based. No offset adjustment is needed when the result is used immediately as a Python array index.
- The `nomatch=0` guard in R (`indx > 0`) translates to `indx_0based != -1` in Python.

---

### 4.2 Argument-name validation (string dispatch)

**Locations:** `rpart/R/rpart.R` — `rpart` (lines 13 and 97); `rpart/R/xpred.rpart.R` — `xpred.rpart` (line 21); `rpart/R/residuals.rpart.R` — `residuals.rpart` (line 11).

**Original R Context:**

```r
# rpart.R line 13
# Match specific argument names in a call object; 0 means absent
indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
temp <- Call[c(1L, indx)]   # keep only matched args

# rpart.R line 97
controlargs <- names(formals(rpart.control))
indx <- match(names(extraArgs), controlargs, nomatch = 0L)
if (any(indx == 0L))
    stop(...)    # unrecognised argument names

# residuals.rpart.R line 11
# type is a validated string; match used after match.arg() for a guard
if (is.na(match(type, c("usual", "pearson", "deviance"))))
    stop("Invalid type of residual")
```

**Python Equivalent:**

```python
import numpy as np

# --- rpart.R line 13 pattern ---
wanted = ["formula", "data", "weights", "subset"]
call_names = list(call_dict.keys())
call_index = {name: i for i, name in enumerate(call_names)}
indx = np.array([call_index.get(k, -1) for k in wanted])
# keep only entries where indx != -1 (analogous to indx > 0 in R)
present = indx[indx != -1]

# --- rpart.R line 97 pattern (validate user-supplied arg names) ---
legal_args = set(rpart_control_params)   # names of legal control arguments
bad = [k for k in extra_args if k not in legal_args]
if bad:
    raise ValueError(f"Argument {bad[0]} not matched")

# --- residuals.rpart.R line 11 pattern ---
VALID_TYPES = {"usual", "pearson", "deviance"}
if type_ not in VALID_TYPES:
    raise ValueError("Invalid type of residual")
```

**Explanation:**
- In Python, string membership tests are best expressed with `in` / set lookups rather than a positional lookup.
- The `nomatch=0L` + `any(indx==0L)` idiom translates directly to checking for `-1` values in NumPy indexer arrays or using set operations.
- For the `residuals.rpart` guard (checking a single string), a simple `in` check against a set or list is clearest.

---

### 4.3 Parent-node lookup in a binary tree (vectorised)

**Locations:** `rpart/R/labels.rpart.R` — `labels.rpart` (line 101); `rpart/R/rpartco.R` — `rpartco` (lines 30, 31); `rpart/R/rpart.branch.R` — `rpart.branch` (lines 19, 20); `rpart/R/text.rpart.R` — `text.rpart` (lines 26, 30, 31, 90); `rpart/R/zzz.R` — `descendants` (line 42).

**Original R Context:**

```r
# labels.rpart.R line 101
# node: numeric vector of node IDs (row names of frame)
# node[whichrow]: subset of non-leaf node IDs
# Result: for each node, the 1-based row index of its parent among non-leaves
parent <- match(node %/% 2L, node[whichrow])

# rpartco.R lines 30-31
parent  <- match(node %/% 2L, node)
sibling <- match(ifelse(node %% 2L, node - 1L, node + 1L), node)

# rpartco.R lines 56-57
left.child  <- match(node * 2L, node)
right.child <- match(node * 2L + 1L, node)

# rpart.branch.R lines 19-20
parent  <- match(node.left / 2L, node)
sibling <- match(node.left + 1L, node)

# zzz.R line 42 (descendants function)
parents <- match((nodes %/% 2L), nodes)
```

**Python Equivalent:**

```python
import numpy as np

# node is a 1-D integer numpy array of node IDs
node = np.array(frame.index, dtype=np.int64)  # row names of frame

# Build a lookup: node_id -> 0-based position in `node`
node_lookup = {v: i for i, v in enumerate(node)}

# Parent lookup (labels.rpart pattern)
non_leaf_nodes = node[which_row]
non_leaf_lookup = {v: i for i, v in enumerate(non_leaf_nodes)}
parent_ids = node // 2
# 0-based index into non_leaf_nodes; -1 when not found (root has no parent)
parent = np.array([non_leaf_lookup.get(p, -1) for p in parent_ids])
# Equivalent to R's parent (1-based) minus 1 for Python indexing

# Sibling lookup (rpartco pattern)
sibling_ids = np.where(node % 2 == 1, node - 1, node + 1)
sibling = np.array([node_lookup.get(s, -1) for s in sibling_ids])

# Child lookups (rpartco lines 56-57)
left_child  = np.array([node_lookup.get(n * 2,     -1) for n in node])
right_child = np.array([node_lookup.get(n * 2 + 1, -1) for n in node])

# descendants (zzz.R) — parents array for all nodes
parent_all = np.array([node_lookup.get(n // 2, -1) for n in node])
```

**Explanation:**
- R's `node %/% 2L` is integer division; Python equivalent is `node // 2` on a NumPy array.
- R's result is 1-based; in Python the dictionary lookup returns 0-based positions directly, which are suitable for NumPy indexing without adjustment.
- The sentinel `-1` (no parent found for root, or no child for leaf nodes) replaces R's `NA`.
- For large node arrays a dict comprehension is O(n); for very large trees `pd.Index(node).get_indexer(...)` is faster.

---

### 4.4 Membership test with `nomatch=0L` (filter/guard pattern)

**Locations:** `rpart/R/snip.rpart.R` — `snip.rpart` (lines 17, 40, 46, 53, 72, 75); `rpart/R/snip.rpart.mouse.R` — `snip.rpart.mouse` (lines 48, 52).

**Original R Context:**

```r
# snip.rpart.R
toss.idx <- match(toss, id, 0L)          # 0 = not found
if (any(toss.idx == 0L)) { ... }          # guard: warn about unknown nodes

xx <- match(id2, toss, 0L) > 0L          # boolean: is id2 element in toss?
toss <- c(toss, id[xx])                  # augment toss with descendants

temp <- match(toss %/% 2L, toss, 0L)     # is the parent also in toss?
newleaf <- match(toss[temp == 0L], id)   # row index for new leaves

n.split <- rep(...)
split <- x$splits[match(n.split, keepit, 0L) > 0L, , drop=FALSE]

# snip.rpart.mouse.R
temp <- match(id2, id, 0L) > 0L
temp <- match(id, node[ff$var != "<leaf>"], 0L)
```

**Python Equivalent:**

```python
import numpy as np

# --- Basic membership test (nomatch=0 -> compare to -1) ---
node_set = set(id_array)
toss_set = set(toss_array)

# match(toss, id, 0L) > 0L  ->  np.isin(toss_array, id_array)
toss_in_id = np.isin(toss_array, id_array)

# match(id2, toss, 0L) > 0L  ->  np.isin(id2, toss_array)
xx = np.isin(id2, toss_array)
toss = np.concatenate([toss, id[xx]])
id2[xx] = 0

# match(toss %/% 2L, toss, 0L) -- parent membership
parent_in_toss = np.isin(toss // 2, toss)   # True = parent is also in toss

# match(n_split, keepit, 0L) > 0L -- filter splits
split_mask = np.isin(n_split, keepit)
split = x_splits[split_mask]

# match(id2, id3, 0L)  with iterative parent-walking (lines 72,75,77)
id_index = {v: i for i, v in enumerate(id3)}
while True:
    positions = np.array([id_index.get(v, -1) for v in id2])
    if not np.any(positions == -1):
        break
    id2[positions == -1] //= 2            # walk up to parent

# Final index lookup (line 77: match(id2, id3))
where = np.array([id_index[v] for v in id2])  # 0-based row indices
```

**Explanation:**
- When `nomatch=0L` is used solely for a boolean check (`> 0L`), `np.isin` is the idiomatic Python replacement — it directly returns a boolean array with no positional arithmetic needed.
- When the result is used as an actual index (line 77, no `nomatch`), a dictionary lookup is used and the `-1` sentinel means unmatched (the while loop eliminates these before the final lookup).
- The iterative parent-walking loop (`while any(temp == 0L)`) is preserved structurally in Python.

---

### 4.5 De-duplication / first-occurrence selection

**Locations:** `rpart/R/prune.rpart.R` — `prune.rpart` (line 10); `rpart/R/snip.rpart.R` — `snip.rpart` (line 47, 48).

**Original R Context:**

```r
# prune.rpart.R line 10
# temp is a numeric vector; unique(temp) selects distinct values.
# match(unique(temp), temp) returns the index of the FIRST occurrence
#   of each unique value in temp.
keep <- match(unique(temp), temp)
newx$cptable <- tree$cptable[keep, , drop = FALSE]

# snip.rpart.R line 47
newleaf <- match(toss[temp == 0L], id)   # row positions of new leaf candidates

# snip.rpart.R line 48
keepit <- (1:ff.n)[is.na(match(id, toss))]  # rows NOT in toss
```

**Python Equivalent:**

```python
import numpy as np

# --- prune.rpart: first-occurrence indices (0-based) ---
temp = np.array(tree_cptable[:, 0])      # first column of cptable
_, first_occurrence = np.unique(temp, return_index=True)
# np.unique sorts; to preserve R's order (first seen, not sorted):
_, idx = np.unique(temp, return_index=True)
keep = np.sort(idx)                      # optional: sort to maintain original order
new_cptable = tree_cptable[keep, :]

# To exactly replicate R's match(unique(temp), temp) without sorting:
seen = {}
first_occ = []
for i, v in enumerate(temp):
    if v not in seen:
        seen[v] = i
        first_occ.append(i)
keep = np.array(first_occ)               # 0-based, in order of first appearance

# --- snip.rpart line 48: rows NOT in toss ---
# is.na(match(id, toss)) -> np.logical_not(np.isin(id, toss))
keepit = np.where(~np.isin(id_array, toss_array))[0]  # 0-based row indices
```

**Explanation:**
- `match(unique(temp), temp)` in R selects the index of the **first** occurrence of each unique value in `temp`, preserving insertion order. `np.unique` sorts its output, so the order differs. The `seen` dict approach exactly replicates R's semantics.
- `is.na(match(id, toss))` (no `nomatch` means default `NA`) identifies elements of `id` absent from `toss`. The Python equivalent is `~np.isin(id, toss)`.

---

### 4.6 Factor/xlevels name alignment

**Locations:** `rpart/R/labels.rpart.R` — `labels.rpart` (line 61); `rpart/R/rpart.R` — `rpart` (line 87); `rpart/R/xpred.rpart.R` — `xpred.rpart` (line 56).

**Original R Context:**

```r
# labels.rpart.R line 61
# vnames: factor variable names appearing in splits (character vector)
# names(xlevels): names of the xlevels list (factor column names)
# Result: for each split variable, its index in xlevels (1-based), NA if missing
cindex <- (match(vnames, names(xlevels)))[ncat > 1L]

# rpart.R line 87
indx <- match(names(xlevels), colnames(X), nomatch=0)
cats[indx] <- (unlist(lapply(xlevels, length)))[indx > 0]
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# --- labels.rpart line 61 ---
# vnames: list of split variable names
# xlevels: dict {factor_name: list_of_levels}
xlevel_names = list(xlevels.keys())
xlevel_index = {name: i for i, name in enumerate(xlevel_names)}

# cindex: for each entry in vnames, the 0-based position in xlevel_names
#          (None / -1 if not found), then filtered to only categorical splits
cindex_full = np.array([xlevel_index.get(v, -1) for v in vnames])
cindex = cindex_full[ncat > 1]          # filter to categorical splits

# Within the loop: xlevels[cindex[i]] -> list(xlevels.values())[cindex[i]]
xlevel_values = list(xlevels.values())
for i in range(len(jrow)):
    levels_i = xlevel_values[cindex[i]]   # 0-based
    ...

# --- rpart.R line 87 ---
col_index = pd.Index(list(X.columns))
indx_0based = col_index.get_indexer(xlevel_names)   # -1 = not found
matched_mask = indx_0based != -1
matched_cols = indx_0based[matched_mask]
cats[matched_cols] = np.array([len(v) for v in
                                np.array(list(xlevels.values()))[matched_mask]])
```

**Explanation:**
- In Python, `xlevels` is a dict; iterating over `xlevels.keys()` and `xlevels.values()` in parallel requires careful alignment. The 0-based index into `list(xlevels.values())` is equivalent to R's 1-based `xlevels[[cindex[i]]]`.
- The `cats[indx]` assignment in R using positions from `match` translates to using NumPy advanced indexing with the 0-based positions returned by `get_indexer`, after masking out `-1` entries.

---

## Summary Table

| R idiom | Python equivalent |
|---|---|
| `match(x, table)` (default `nomatch=NA`) | `pd.Index(table).get_indexer(x)` then treat `-1` as missing; or dict lookup returning `None`/`-1` |
| `match(x, table, nomatch=0L)` for boolean test | `np.isin(x, table)` |
| `match(x, table, nomatch=0L) > 0L` | `np.isin(x, table)` |
| `is.na(match(x, table))` | `~np.isin(x, table)` |
| `match(unique(x), x)` (first-occurrence indices) | Dict-based first-occurrence loop (see §4.5) |
| `match(node %/% 2L, node)` (parent lookup) | Dict `{id: idx}` + list comprehension; or `pd.Index(node).get_indexer(node // 2)` |
| Result used as 1-based row selector | Subtract 1 for 0-based Python indexing |
| `match` result used with `NA` guard | Check for `-1` (pandas) or `None` (dict lookup) |

# Conversion Guide: `labels` (R to Python)

---

### 1. Overview of `labels` in R

`labels` is a base R S3 generic function that retrieves human-readable string labels from an R object. Its behaviour is entirely determined by the class of the object it is called on: R dispatches to the appropriate S3 method automatically.

**Base generic signature:**
```r
labels(object, ...)
```

In the rpart package, calling `labels(x, ...)` on an `rpart` object dispatches to `labels.rpart()`, defined in `rpart/R/labels.rpart.R`.

**`labels.rpart` signature:**
```r
labels.rpart(object, digits = 4, minlength = 1L, pretty, collapse = TRUE, ...)
```

**Key parameters:**

| Parameter | Type | Description |
|---|---|---|
| `object` | `rpart` object | The fitted decision tree |
| `digits` | integer scalar | Decimal precision for numeric split cut-points (default `4`) |
| `minlength` | integer scalar | Controls factor-level abbreviation: `0` = no abbreviation, `1` = single letters, `>= 2` = call `abbreviate(level, minlength)` |
| `pretty` | `NULL`, logical, or integer `0` | Legacy compatibility alias for `minlength`: `NULL` → `minlength=1`, `TRUE` → `minlength=4`, `0` → `minlength=0` |
| `collapse` | logical | When `TRUE` (default), returns a character vector of length `nrow(frame)` — one label per node. When `FALSE`, returns a two-column character matrix of left/right branch labels for non-leaf nodes only |

**Return value:** A character vector (length = `nrow(object$frame)`) where each element is the split description joining that node to its parent (e.g. `"Age< 35"`, `"Sex=a,b"`). The first element is always `"root"`. Leaves inherit the label of the edge leading to them from their parent.

**Core behaviour:** The function iterates over every internal (non-leaf) node in the frame, reads the corresponding row of `object$splits`, and constructs a human-readable condition string. Continuous predictors produce `"< cutpoint"` / `">= cutpoint"` strings; categorical predictors produce `"=levelA,levelB"` strings derived from `object$csplit` and the factor level names in `attr(object, "xlevels")`. The two half-labels are then collapsed into one per node according to whether the node is a left or right child.

---

### 2. Contextual Usage Analysis

Both rows in the CSV refer to **line 33** of `rpart/R/text.rpart.R`, inside the `text.rpart` function. They represent the two branches of a single conditional expression — only one branch executes at runtime:

```r
# text.rpart.R, lines 29–33
if (splits) {
    left.child <- match(2L * node, node)
    right.child <- match(node * 2L + 1L, node)
    rows <- if (!missing(pretty) && missing(minlength))
        labels(x, pretty = pretty) else labels(x, minlength = minlength)
```

**Branch 1 — `labels(x, pretty = pretty)`**

Triggered when the caller passes `pretty` explicitly but does not pass `minlength`. `pretty` is forwarded verbatim to `labels.rpart`, which converts it internally to a `minlength` value:

- `pretty = NULL`  → `minlength = 1L`
- `pretty = TRUE`  → `minlength = 4L`
- `pretty = 0`     → `minlength = 0L`

**Branch 2 — `labels(x, minlength = minlength)`**

The default path. `minlength` defaults to `1L` in `text.rpart`'s own signature, so this call typically resolves to `labels.rpart(x, minlength = 1L)`, producing single-letter abbreviations for factor levels.

**Return value and downstream use:**

In both branches the return value `rows` is a character vector with one label per node (equal in length to `nrow(x$frame)`). It is subsequently indexed:

```r
# lines 43, 45, 47
rows[left.child[!is.na(left.child)]]   # split labels for left branches (fancy mode)
rows[right.child[!is.na(right.child)]] # split labels for right branches (fancy mode)
rows[left.child]                        # split labels at parent nodes (plain mode)
```

**Data types:**

- Input `x`: an `rpart` object (a named list with `$frame`, `$splits`, `$csplit`, plus attributes `"xlevels"` and `"ylevels"`).
- `pretty`: `NULL`, a single logical, or the integer `0`.
- `minlength`: a single integer scalar.
- Return: `character` vector, length = number of rows in `x$frame`.

**Recurring pattern:** Both CSV rows resolve to the same underlying function, `labels.rpart`. The `pretty` / `minlength` duality is purely an argument-handling convenience; the computation is identical once `minlength` is resolved.

---

### 3. Python Conversion Strategy

Because `labels` dispatches to `labels.rpart` for `rpart` objects, the Python translation targets `labels_rpart` directly — there is no generic dispatch mechanism to replicate.

The function is **not vectorized in the NumPy sense**: it builds strings by iterating over tree nodes and does not operate on homogeneous numeric arrays. Therefore `numpy`, `scipy`, and `pandas` are not the primary tools here. The natural Python equivalents are:

- **Plain Python `list[str]`** for the output character vector.
- **`numpy.ndarray`** (dtype `float64` / `int32`) for the numeric matrices `object$splits` and `object$csplit`, which are likely already stored as NumPy arrays in the Python rpart port.
- **Python `dict`** for `attr(object, "xlevels")` — a mapping from predictor name to list of factor-level strings.
- **Python `string` operations** (`str.join`, f-strings, `format`) to construct the label strings.

The `pretty` → `minlength` conversion logic is a pure scalar conditional that maps directly to an `if/elif/else` block in Python. No library is required for this part.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Resolving `pretty` to `minlength`

This sub-logic occurs inside `labels.rpart` (lines 19–24 of `labels.rpart.R`) and must be reproduced at the top of the Python equivalent before any label generation begins.

**Locations:** `rpart/R/labels.rpart.R` — `labels.rpart`; indirectly triggered from `rpart/R/text.rpart.R` — `text.rpart` (line 33, Branch 1).

**Original R Context:**

- `minlength`: integer scalar, default `1L`.
- `pretty`: may be `NULL`, `TRUE`/`FALSE`, or integer `0`. It is "missing" unless explicitly supplied by the caller.
- Return: resolved integer value for `minlength` used throughout the rest of the function.

```r
# R: argument resolution at the top of labels.rpart
labels.rpart <- function(object, digits = 4, minlength = 1L, pretty, collapse = TRUE, ...)
{
    if (missing(minlength) && !missing(pretty)) {
        minlength <- if (is.null(pretty)) 1L
                     else if (is.logical(pretty)) {
                         if (pretty) 4L else 0L
                     } else 0L
    }
    # ... rest of function uses resolved minlength
}
```

**Python Equivalent:**

```python
_MISSING = object()  # sentinel for "argument not supplied"

def labels_rpart(obj, digits=4, minlength=1, pretty=_MISSING, collapse=True, **kwargs):
    """
    Python equivalent of R's labels.rpart().

    Parameters
    ----------
    obj : rpart-like object
        Must expose .frame (DataFrame), .splits (ndarray), .csplit (ndarray),
        and xlevels attribute (dict[str, list[str]]).
    digits : int
        Decimal precision for numeric cut-points (default 4).
    minlength : int
        Abbreviation length for factor levels (default 1).
    pretty : object or _MISSING
        Legacy alias: None -> minlength=1, True -> minlength=4, 0/False -> minlength=0.
        Pass _MISSING (the default) to omit, mirroring R's missing().
    collapse : bool
        If True (default), return a flat list[str] of length nrow(frame).
        If False, return a two-column list-of-lists [[left_label, right_label], ...].

    Returns
    -------
    list[str]  (collapse=True)  or  list[list[str, str]]  (collapse=False)
    """
    # --- Step 1: resolve pretty -> minlength (mirrors lines 19-24 of labels.rpart.R) ---
    if pretty is not _MISSING:
        # Only override minlength when pretty is explicitly supplied
        # and minlength was left at its default (we use sentinel to detect this)
        if pretty is None:
            minlength = 1
        elif isinstance(pretty, bool):
            minlength = 4 if pretty else 0
        else:
            # pretty = 0 (integer) falls here
            minlength = 0

    # ... rest of the function follows (see Section 4.2)
```

**Explanation:**

| R concept | Python translation |
|---|---|
| `missing(minlength)` | Use a sentinel `_MISSING = object()` as the default; check `pretty is not _MISSING` |
| `!missing(pretty)` | `pretty is not _MISSING` — the sentinel distinguishes "not supplied" from `None` |
| `is.null(pretty)` | `pretty is None` |
| `is.logical(pretty)` | `isinstance(pretty, bool)` |
| `if (pretty) 4L else 0L` | `4 if pretty else 0` |
| Integer literals `1L`, `4L`, `0L` | Plain Python `int`: `1`, `4`, `0` |

Note that Python does not have R's `missing()` concept for function arguments. The sentinel pattern is the idiomatic Python replacement.

---

#### 4.2 Generating split labels and assembling the output vector

This is the main body of `labels.rpart`, producing the character vector returned to `text.rpart`.

**Locations:** `rpart/R/labels.rpart.R` — `labels.rpart`; result consumed in `rpart/R/text.rpart.R` — `text.rpart` (line 33, both branches).

**Original R Context:**

- `object$frame`: a data frame with columns `var` (factor/character — predictor name or `"<leaf>"`), `ncompete`, `nsurrogate`, `n`, etc. One row per node.
- `object$splits`: a numeric matrix; column 2 = `ncat` (number of categories; negative or `< 2` signals a continuous split), column 4 = cut-point value (continuous) or row index into `csplit` (categorical).
- `object$csplit`: an integer matrix encoding which factor levels go left (`1`) or right (`3`) at each categorical split.
- `attr(object, "xlevels")`: named list mapping predictor name → character vector of factor levels.
- Return: `character` vector, length = `nrow(object$frame)`.

```r
# R: core label-building logic (labels.rpart.R, lines 26-108)
ff    <- object$frame
n     <- nrow(ff)
if (n == 1L) return("root")          # tree with no splits

is.leaf  <- (ff$var == "<leaf>")
whichrow <- !is.leaf
vnames   <- ff$var[whichrow]         # predictor name for each internal node

index <- cumsum(c(1, ff$ncompete + ff$nsurrogate + !is.leaf))
irow  <- index[c(whichrow, FALSE)]   # row index into object$splits for each split
ncat  <- object$splits[irow, 2L]     # number of categories (< 2 -> continuous)

lsplit <- rsplit <- character(length(irow))

# Continuous predictors
if (any(ncat < 2L)) {
    jrow     <- irow[ncat < 2L]
    cutpoint <- formatg(object$splits[jrow, 4L], digits)
    temp1 <- ifelse(ncat[ncat < 2L] < 0, "< ", ">=")
    temp2 <- ifelse(ncat[ncat < 2L] < 0, ">=", "< ")
    lsplit[ncat < 2L] <- paste0(temp1, cutpoint)
    rsplit[ncat < 2L] <- paste0(temp2, cutpoint)
}

# Categorical predictors
if (any(ncat > 1L)) {
    xlevels <- attr(object, "xlevels")
    jrow   <- seq_along(ncat)[ncat > 1L]
    crow   <- object$splits[irow[ncat > 1L], 4L]
    cindex <- match(vnames, names(xlevels))[ncat > 1L]

    if (minlength == 1L)
        xlevels <- lapply(xlevels, function(z) c(letters, LETTERS)[pmin(seq_along(z), 52L)])
    else if (minlength > 1L)
        xlevels <- lapply(xlevels, abbreviate, minlength, ...)

    for (i in seq_along(jrow)) {
        j      <- jrow[i]
        splits <- object$csplit[crow[i], ]
        cl     <- if (minlength == 1L) "" else ","
        lsplit[j] <- paste(xlevels[[cindex[i]]][splits == 1L], collapse = cl)
        rsplit[j] <- paste(xlevels[[cindex[i]]][splits == 3L], collapse = cl)
    }
}

# Add prefix
lsplit <- paste0(ifelse(ncat < 2L, "", "="), lsplit)
rsplit <- paste0(ifelse(ncat < 2L, "", "="), rsplit)

# Assign labels to every node
varname <- as.character(vnames)
node    <- as.numeric(row.names(ff))
parent  <- match(node %/% 2L, node[whichrow])
odd     <- as.logical(node %% 2L)

labels <- character(n)
labels[odd]  <- paste0(varname[parent[odd]],  rsplit[parent[odd]])
labels[!odd] <- paste0(varname[parent[!odd]], lsplit[parent[!odd]])
labels[1L]   <- "root"
labels
```

**Python Equivalent:**

```python
import numpy as np

# Assume: letters = list("abcdefghijklmnopqrstuvwxyz")
#         LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_LETTERS = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")  # 52 elements


def _formatg(x, digits):
    """
    Approximate equivalent of R's formatg(): format a float to `digits`
    significant figures, stripping trailing zeros.
    """
    return f"{x:.{digits}g}"


def labels_rpart_body(obj, digits=4, minlength=1, collapse=True, **kwargs):
    """
    Core label-building logic of labels.rpart (after minlength is resolved).
    Call after resolving pretty -> minlength (see Section 4.1).

    Parameters
    ----------
    obj : rpart-like object
        .frame     : pandas DataFrame with columns 'var', 'ncompete', 'nsurrogate'
        .splits    : numpy ndarray, shape (total_splits, 5); col-index 1 = ncat, col-index 3 = cut/crow
        .csplit    : numpy ndarray of int, shape (n_cat_splits, max_levels);
                     1 = left, 3 = right, 2 = neither
        .xlevels   : dict[str, list[str]]  (attr(object, "xlevels"))
        .frame.index (row names) are node numbers as strings

    Returns
    -------
    list[str]
    """
    frame = obj.frame
    n = len(frame)

    if n == 1:
        return ["root"]

    var_col = frame["var"].to_numpy(dtype=str)
    is_leaf = var_col == "<leaf>"
    whichrow = ~is_leaf                       # boolean mask for internal nodes
    vnames = var_col[whichrow]                # predictor names at internal nodes

    ncompete   = frame["ncompete"].to_numpy(dtype=int)
    nsurrogate = frame["nsurrogate"].to_numpy(dtype=int)
    not_leaf_int = (~is_leaf).astype(int)

    # cumsum(c(1, ncompete + nsurrogate + !is_leaf)) then slice [whichrow]
    # In R, index is 1-based; we use 0-based here
    increments = np.concatenate([[0], ncompete + nsurrogate + not_leaf_int])
    index = np.cumsum(increments)             # length n+1; index[i] is start of node i's splits
    # irow: for each internal node, its primary split row in obj.splits (0-based)
    irow = index[np.where(whichrow)[0]]       # shape: (n_internal,)

    ncat = obj.splits[irow, 1].astype(int)   # column 2 in R (1-based) = column index 1 (0-based)

    n_internal = int(whichrow.sum())
    lsplit = [""] * n_internal
    rsplit = [""] * n_internal

    # --- Continuous predictors (ncat < 2) ---
    cont_mask = ncat < 2
    if cont_mask.any():
        jrow = irow[cont_mask]
        cutpoints = obj.splits[jrow, 3]       # column 4 in R = index 3
        for idx, (j_local, cp, nc) in enumerate(
            zip(np.where(cont_mask)[0], cutpoints, ncat[cont_mask])
        ):
            cp_str = _formatg(cp, digits)
            if nc < 0:
                lsplit[j_local] = f"< {cp_str}"
                rsplit[j_local] = f">= {cp_str}"
            else:
                lsplit[j_local] = f">= {cp_str}"
                rsplit[j_local] = f"< {cp_str}"

    # --- Categorical predictors (ncat > 1) ---
    cat_mask = ncat > 1
    if cat_mask.any():
        xlevels = dict(obj.xlevels)           # shallow copy; values are list[str]

        if minlength == 1:
            # Replace each level list with single letters (a-z then A-Z), capped at 52
            xlevels = {
                k: [_LETTERS[min(i, 51)] for i in range(len(v))]
                for k, v in xlevels.items()
            }
        elif minlength > 1:
            # Apply abbreviation (see abbreviate.md conversion guide)
            from abbreviate import abbreviate_levels  # project-local helper
            xlevels = abbreviate_levels(xlevels, minlength=minlength, **kwargs)

        xlevel_names = list(xlevels.keys())
        cat_positions = np.where(cat_mask)[0]
        crow_indices  = obj.splits[irow[cat_mask], 3].astype(int)  # 0-based row into csplit
        # Match vnames[cat_mask] to xlevels keys
        cindex = [xlevel_names.index(vnames[j]) for j in cat_positions]

        cl = "" if minlength == 1 else ","

        for i, (j_local, crow, ci) in enumerate(
            zip(cat_positions, crow_indices, cindex)
        ):
            level_list = list(xlevels.values())[ci]
            split_dirs = obj.csplit[crow]     # 1=left, 3=right, 2=neither
            left_levels  = [level_list[k] for k, d in enumerate(split_dirs) if d == 1]
            right_levels = [level_list[k] for k, d in enumerate(split_dirs) if d == 3]
            lsplit[j_local] = cl.join(left_levels)
            rsplit[j_local] = cl.join(right_levels)

    # Add "=" prefix for categorical, nothing for continuous
    lsplit = [
        ("=" if nc >= 2 else "") + s
        for nc, s in zip(ncat, lsplit)
    ]
    rsplit = [
        ("=" if nc >= 2 else "") + s
        for nc, s in zip(ncat, rsplit)
    ]

    # --- Assign one label per node ---
    varname = vnames.tolist()
    node = np.array([int(r) for r in frame.index], dtype=int)
    # parent[i]: index (0-based) of node i's parent among internal nodes
    internal_nodes = node[whichrow]
    parent_node_num = node // 2
    # match parent_node_num to position in internal_nodes
    internal_node_map = {v: idx for idx, v in enumerate(internal_nodes)}
    parent = np.array(
        [internal_node_map.get(p, -1) for p in parent_node_num],
        dtype=int
    )
    odd = (node % 2).astype(bool)             # True = right child (odd node numbers)

    out_labels = [""] * n
    for i in range(n):
        p = parent[i]
        if p < 0:
            continue
        if odd[i]:
            out_labels[i] = varname[p] + rsplit[p]
        else:
            out_labels[i] = varname[p] + lsplit[p]
    out_labels[0] = "root"

    return out_labels
```

**Explanation:**

| R concept | Python translation |
|---|---|
| `nrow(ff)` | `len(frame)` |
| `ff$var == "<leaf>"` | `frame["var"].to_numpy(dtype=str) == "<leaf>"` |
| `!is.leaf` | `~is_leaf` (NumPy boolean negation) |
| `cumsum(c(1, ...))` | `np.cumsum(np.concatenate([[0], ...]))` — 0-based offset instead of R's 1-based `1` |
| `object$splits[irow, 2L]` | `obj.splits[irow, 1]` — R column 2 (1-based) = Python index 1 (0-based) |
| `object$splits[irow, 4L]` | `obj.splits[irow, 3]` — R column 4 (1-based) = Python index 3 (0-based) |
| `seq_along(ncat)[ncat > 1L]` | `np.where(cat_mask)[0]` |
| `match(vnames, names(xlevels))` | `[list(xlevels.keys()).index(name) for name in vnames[cat_mask]]` |
| `c(letters, LETTERS)[pmin(seq_along(z), 52L)]` | `[_LETTERS[min(i, 51)] for i in range(len(v))]` — Python 0-based index into the 52-element `_LETTERS` list |
| `paste(..., collapse=cl)` | `cl.join(...)` |
| `paste0(prefix, s)` | f-string or `prefix + s` |
| `row.names(ff)` as numeric | `[int(r) for r in frame.index]` |
| `node %/% 2L` | `node // 2` (integer floor division) |
| `node %% 2L` | `node % 2` |
| `match(x, table)` | `{v: idx for idx, v in enumerate(table)}` lookup dict |
| `labels[odd]  <- ...` | Loop: `if odd[i]: out_labels[i] = ...` |
| `labels[1L] <- "root"` | `out_labels[0] = "root"` (0-based index) |

---

#### 4.3 Using the converted function in `text_rpart` (the call site)

**Locations:** `rpart/R/text.rpart.R` — `text.rpart` (line 33, both CSV rows).

**Original R Context:**

```r
# R: text.rpart, lines 29-33
rows <- if (!missing(pretty) && missing(minlength))
    labels(x, pretty = pretty) else labels(x, minlength = minlength)
```

**Python Equivalent:**

```python
def text_rpart(x, splits=True, FUN=None, all_nodes=False,
               pretty=_MISSING, digits=None, use_n=False,
               fancy=False, fwidth=0.8, fheight=0.8,
               bg=None, minlength=1, **kwargs):
    """
    Python equivalent of R's text.rpart (partial — label-generation section only).
    """
    if digits is None:
        digits = 7 - 3  # getOption("digits") - 3L defaults to 4 in a typical R session

    # ... (setup code omitted for brevity) ...

    if splits:
        # Mirror R line 32-33: choose argument routing based on what was supplied
        if pretty is not _MISSING:
            # Branch 1: caller supplied pretty, did not supply minlength explicitly
            rows = labels_rpart(x, pretty=pretty)
        else:
            # Branch 2: default path — use minlength (default 1)
            rows = labels_rpart(x, minlength=minlength)

        # rows is now list[str], one entry per node — index it exactly as R does
        # (adjusting for 0-based indexing)
        # ... downstream indexing: rows[left_child], rows[right_child], etc.
```

**Explanation:**

| R concept | Python translation |
|---|---|
| `!missing(pretty) && missing(minlength)` | `pretty is not _MISSING` — the sentinel covers both conditions simultaneously: if `pretty` was supplied, we use it; otherwise we use `minlength` |
| `labels(x, pretty = pretty)` | `labels_rpart(x, pretty=pretty)` — no S3 dispatch needed; call the method directly |
| `labels(x, minlength = minlength)` | `labels_rpart(x, minlength=minlength)` |
| `rows[left.child]` (1-based R indexing) | `[rows[i] for i in left_child]` or `rows[left_child - 1]` if using 0-based NumPy arrays; prefer storing `left_child` as 0-based throughout the Python port |
| Return type: R `character` vector | Python `list[str]` |

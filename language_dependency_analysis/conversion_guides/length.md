# Conversion Guide: `length` (R to Python)

---

## 1. Overview of `length` in R

`length` is a base R function that returns a single non-negative integer: the number of elements in its argument. Its signature is:

```r
length(x)
```

- **Input (`x`):** Any R object — atomic vector (logical, integer, double, complex, character, raw), list, factor, matrix, data frame, `NULL`, or a function.
- **Output:** A single integer scalar (always `>= 0`). For `NULL`, it returns `0`. For a matrix or data frame, it returns the total number of elements (rows * columns for a matrix; number of columns for a data frame). For a list, it returns the number of top-level elements. For a factor, it returns the number of elements (not the number of levels).
- **Key semantic:** `length` counts top-level elements, not nested ones. It does not recurse into list elements or matrix rows.

In practice across the rpart codebase, `length` is used almost exclusively on 1-D atomic vectors and lists, so it uniformly counts items in those containers.

---

## 2. Contextual Usage Analysis

Across the 62 call sites in the CSV, five distinct usage patterns appear:

### Pattern A — Guard / early-exit check (comparing length to 0 or a fixed scalar)

The most common pattern. `length(x)` is compared against a literal (typically `0L`, `1L`, or another constant) in an `if` condition to decide whether to bail out early, take a branch, or issue a warning. The vector is always 1-D (integer, character, or numeric vector; a list; or a named list).

Representative sites: `prune.rpart.R:6`, `snip.rpart.R:8,10,15`, `path.rpart.R:23`, `rpart.R:95,114,117,120,129,141,159`, `rpartcallback.R:6`, `zzz.R:24`.

### Pattern B — Storing length as a scalar for downstream arithmetic / loop bounds

`length(x)` is called and its result is assigned to a named variable (`nclass`, `ngrp`, `cutoff.n`, etc.) or used directly as a dimension in `matrix()`, `seq()`, or `1:n` iteration. The object measured is always a 1-D vector or list.

Representative sites: `predict.rpart.R:22,31`, `residuals.rpart.R:16`, `roc.rpart.R:5,28`, `rpart.exp.R:39,42,56`, `xpred.rpart.R:50,63,68,71,73,80,82,99,118,137`, `zzz.R:37`.

### Pattern C — Used inline to allocate a correctly sized container

`character(length(irow))` (and similar) creates a zero-filled vector whose length matches another vector. The call appears as the argument to `character()`, `integer()`, `double()`, etc.

Representative sites: `labels.rpart.R:41`, `rpartco.R:54`.

### Pattern D — Used as the side-effect vehicle for assignment-in-condition

```r
while (length(i <- identify(xy, n = 1L, plot = FALSE)) > 0L)
```

Here `length(...)` both triggers the side-effectful call and checks whether the returned vector is non-empty. This pattern is specific to interactive/GUI code.

Representative sites: `path.rpart.R:15`, `snip.rpart.mouse.R:25`.

### Pattern E — Passed as a function object (not called)

```r
columns <- sapply(s2, function(x) max(nchar(x, "w")))
```

In `zzz.R:14`, `string.bounding.box` uses `sapply(s2, length)` — passing `length` itself as the function argument to `sapply`. This is purely a functional-programming idiom.

Representative site: `zzz.R:14`.

### Pattern F — Validation: comparing `length(x)` against `length(y)` or a computed quantity

`length(...)` is compared against `nobs`, `numclass^2`, `ncat - 1L`, etc., to validate that a returned or input object has the expected size.

Representative sites: `rpart.class.R:29,35`, `rpartcallback.R:35,37,47,48,53,55,64,66,77,78,84,86`, `rpart.R:141`.

### Data types observed

| Object type | Example sites |
|---|---|
| Integer vector | `labels.rpart.R:41`, `rpart.R:114,117` |
| Numeric (double) vector | `rpart.exp.R:39,42,56`, `xpred.rpart.R:50,63` |
| Character vector | `rpartco.R:54`, `print.rpart.R:13,23,30` |
| Named list | `rpartcallback.R:6`, `rpartco.R:15`, `xpred.rpart.R:99` |
| Factor (as vector) | `predict.rpart.R:22,31`, `residuals.rpart.R:16` |
| Attribute-extracted vector | `roc.rpart.R:5` (`attr(object, "ylevels")`) |
| NULL (implicit 0) | `rpart.R:29` (when `wt` is empty) |

---

## 3. Python Conversion Strategy

**Primary equivalent: `len()` (Python built-in)**

Unlike many R vectorized functions that require `numpy`, `length` in R always returns a single scalar integer describing the size of a container — it is not itself a vectorized operation. The direct Python equivalent is the built-in `len()`, which:

- Returns `int` (not `numpy.int64`), matching R's scalar-integer output.
- Works on `list`, `tuple`, `str`, `dict`, `numpy.ndarray` (1-D), and `pandas.Series`.
- Returns `0` for empty sequences, matching R's `length(NULL) == 0`.

For `numpy.ndarray`, `len(arr)` returns the size of the **first axis** (equivalent to `nrow()` for 2-D). To count total elements of a multi-dimensional array (the rare case matching R's matrix behaviour for `length`), use `arr.size`. However, in rpart's usage, all measured objects are 1-D or lists, so `len()` is always the right choice.

**Secondary equivalent: `arr.shape[0]` / `arr.size`**

When the Python translation of an R vector is a `numpy` array, both `len(arr)` (for 1-D) and `arr.shape[0]` are unambiguous and interchangeable. Prefer `len()` for readability unless the surrounding code already uses `.shape` indexing.

**Pattern E (passing as a callable):** Replace `sapply(s2, length)` with a list comprehension or `[len(x) for x in s2]`, or `np.array([len(x) for x in s2])`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Guard / early-exit check

**Locations:**
- `prune.rpart.R` — `prune.rpart` (line 6)
- `snip.rpart.R` — `snip.rpart` (lines 8, 10, 15)
- `path.rpart.R` — `path.rpart` (line 23)
- `rpart.R` — `rpart` (lines 95, 114, 117, 120, 129, 141, 159)
- `rpartcallback.R` — `rpartcallback` (line 6)
- `zzz.R` — `node.match` (line 24)

**Original R context:**

`toss` is an integer vector, `mlist` is a list, `xval` is a numeric vector, `nodes`/`bad` are integer vectors.

```r
# prune.rpart.R:5-7
toss <- id[ff$complexity <= cp & ff$var != "<leaf>"]
if (length(toss) == 0L) return(tree)

# snip.rpart.R:8-10
if (missing(toss) || length(toss) == 0L) {
    toss <- snip.rpart.mouse(x)
    if (length(toss) == 0L) return(x)
}

# rpartcallback.R:6
if (length(mlist) < 3L)
    stop("User written methods must have 3 functions")

# rpart.R:95
if (length(extraArgs)) { ... }

# zzz.R:23-24
bad <- nodes[node.index == 0L]
if (length(bad) > 0 && print.it) warning(...)
```

**Python equivalent:**

```python
import numpy as np

# Guard: early return if container is empty
toss = id_arr[(ff_complexity <= cp) & (ff_var != "<leaf>")]
if len(toss) == 0:
    return tree

# Guard: check minimum list length
if len(mlist) < 3:
    raise ValueError("User written methods must have 3 functions")

# Truthiness shorthand (non-empty == truthy, just like R's if(length(x)))
extra_args = {}  # dict equivalent of R list(...)
if len(extra_args):
    pass  # process extra_args

# Compare to another length or threshold
bad = nodes[node_index == 0]
if len(bad) > 0 and print_it:
    import warnings
    warnings.warn(f"supplied nodes {bad} are not in this tree")
```

**Explanation:**
- `length(x) == 0L` maps directly to `len(x) == 0`. Python also supports the idiomatic `if not x:` for empty lists/arrays, but explicit `len()` checks are clearer when the surrounding code uses numeric comparisons.
- R's `if (length(x))` (truthy check) maps to Python's `if len(x):` or `if x:` (for lists). For `numpy` arrays, use `if len(x) > 0:` because bare `if arr:` raises an error on arrays with more than one element.
- `< 3L` in R maps to `< 3` in Python; the `L` suffix is R's integer literal marker with no Python counterpart.

---

### 4.2 Pattern B — Storing length as a scalar for downstream use

**Locations:**
- `predict.rpart.R` — `predict.rpart` (lines 22, 31)
- `residuals.rpart.R` — `residuals.rpart` (line 16)
- `roc.rpart.R` — `roc.rpart` (lines 5, 28)
- `rpart.exp.R` — `drate2` (line 56), `rpart.exp` (lines 39, 42, 107)
- `print.rpart.R` — `print.rpart` (lines 13, 23, 30)
- `printcp.R` — `printcp` (line 35)
- `summary.rpart.R` — `summary.rpart` (lines 21, 38)
- `xpred.rpart.R` — `xpred.rpart` (lines 50, 63, 68, 71, 73, 80, 82, 99, 118, 137)
- `zzz.R` — `descendants` (line 37)

**Original R context:**

`ylevels` is a character vector (factor levels), `cutoffs` is a numeric vector, `dtimes`/`ilength` are numeric vectors, `xval`/`xgroups` are integer vectors, `wt` is a numeric vector, `nodes` is an integer vector.

```r
# predict.rpart.R:22
ylevels <- attr(object, "ylevels")
nclass <- length(ylevels)       # integer scalar used for indexing

# roc.rpart.R:5
if (length(attr(object, "ylevels")) != 2L)
    stop(...)
# roc.rpart.R:28
cutoff.n <- length(cutoffs)     # used to size matrices below

# rpart.exp.R:56
ilength <- diff(itable)
ngrp <- length(ilength)         # number of intervals

# rpart.exp.R:39
if (length(dtimes) > 1000) dtimes <- quantile(dtimes, 0:1000/1000)

# xpred.rpart.R:73
xval <- length(unique(xgroups))

# zzz.R:37
n <- length(nodes)
if (n == 1L) return(matrix(TRUE, 1L, 1L))
```

**Python equivalent:**

```python
import numpy as np

# Scalar for indexing / arithmetic
ylevels = object_attrs.get("ylevels", [])
nclass = len(ylevels)           # int scalar

# Validation against fixed value
if len(ylevels) != 2:
    raise ValueError("Not a 2-level factor")

# Size for matrix allocation
cutoffs = np.unique(np.concatenate([[0, 1], frame_yprob_endnodes]))
cutoff_n = len(cutoffs)
sensitivity = np.zeros((cutoff_n, 1))

# Length of a computed diff array
ilength = np.diff(itable)
ngrp = len(ilength)

# Threshold check
if len(dtimes) > 1000:
    dtimes = np.quantile(dtimes, np.arange(0, 1001) / 1000)

# Length of unique values
xval = len(np.unique(xgroups))

# Early return based on length
n = len(nodes)
if n == 1:
    return np.ones((1, 1), dtype=bool)
```

**Explanation:**
- `length(ylevels)` where `ylevels` is a character vector translates to `len(ylevels)` whether `ylevels` is a Python `list` or `numpy` array of strings.
- `length(unique(xgroups))` becomes `len(np.unique(xgroups))`. R's `unique()` on a vector is `np.unique()` on a 1-D array.
- R uses `1L` integer literals; Python uses plain `1`. The semantics are identical for comparisons.
- `length(diff(itable))` is `len(np.diff(itable))` — `np.diff` returns an array one element shorter than its input, exactly as R's `diff`.

---

### 4.3 Pattern C — Allocate a correctly sized container

**Locations:**
- `labels.rpart.R` — `labels.rpart` (line 41)
- `rpartco.R` — `rpartco` (line 54)

**Original R context:**

`irow` is an integer index vector. `node` is an integer vector of node numbers.

```r
# labels.rpart.R:41
lsplit <- rsplit <- character(length(irow))
# Creates two character vectors of the same length as irow, filled with ""

# rpartco.R:54
x <- double(length(node))
# Creates a numeric vector of zeros, same length as node
```

**Python equivalent:**

```python
import numpy as np

# Equivalent of character(length(irow)) — array of empty strings
irow = ...  # numpy integer array or Python list
lsplit = np.full(len(irow), "", dtype=object)   # or: [""] * len(irow)
rsplit = np.full(len(irow), "", dtype=object)

# Equivalent of double(length(node)) — zero-filled float array
node = ...  # numpy integer array or Python list
x = np.zeros(len(node), dtype=float)
```

**Explanation:**
- R's `character(n)` creates a length-`n` vector of empty strings `""`. The Python equivalent using numpy is `np.full(n, "", dtype=object)` or a plain list `[""] * n`.
- R's `double(n)` creates a length-`n` zero-filled numeric vector. Python's equivalent is `np.zeros(n, dtype=float)` or `np.zeros(n)` (default dtype is already `float64`).
- In both cases the allocation size is `len(irow)` / `len(node)`, a direct substitution.

---

### 4.4 Pattern D — Side-effect assignment inside length check (interactive GUI code)

**Locations:**
- `path.rpart.R` — `path.rpart` (line 15)
- `snip.rpart.mouse.R` — `snip.rpart.mouse` (line 25)

**Original R context:**

`identify()` is an R interactive graphics function that returns the indices of graphical points clicked by the user. `length(i <- identify(...))` simultaneously assigns the result to `i` and checks that at least one point was identified.

```r
# path.rpart.R:14-16
xy <- rpartco(tree)
while (length(i <- identify(xy, n = 1L, plot = FALSE)) > 0L) {
    path[[n[i]]] <- path.i <- splits[which[, i]]
    ...
}

# snip.rpart.mouse.R:25
while (length(choose <- identify(xy, n = 1L, plot = FALSE))) {
    ...
}
```

**Python equivalent:**

```python
# R's identify() is an interactive GUI function with no direct Python
# equivalent in a non-GUI context. In a matplotlib-based translation,
# the pattern becomes an event-driven callback loop.

import matplotlib.pyplot as plt

xy = rpartco(tree)
selected = []

def on_click(event):
    if event.xdata is not None and event.ydata is not None:
        # find the nearest node index (equivalent of identify())
        i = find_nearest_node(xy, event.xdata, event.ydata)
        if i is not None:
            selected.append(i)
            # process selected node: equivalent of the while-loop body
            process_node(i, splits, which, n)

fig, ax = plt.subplots()
cid = fig.canvas.mpl_connect('button_press_event', on_click)
plt.show()

# Alternatively, for a non-interactive (programmatic) translation,
# replace the while-loop with iteration over a pre-specified list of
# node indices, eliminating the length() guard entirely:
for i in node_indices:
    process_node(i, splits, which, n)
```

**Explanation:**
- The `length(i <- identify(...)) > 0L` idiom has no direct Python analogue because: (1) Python does not allow assignment-as-expression in the same way (though the walrus operator `:=` is close); (2) `identify()` is an R-specific interactive graphics primitive.
- For non-interactive translations, the while-loop body is simply iterated over a pre-determined list.
- If interactive node selection is needed in Python, use `matplotlib`'s `mpl_connect('button_press_event', ...)` callback pattern. The `len()` check becomes an event-driven loop exit condition.
- The walrus operator approach in Python:

```python
# Using Python's walrus operator (:=), available in Python 3.8+
while (choose := identify_node(xy)) is not None and len(choose) > 0:
    process(choose)
```

---

### 4.5 Pattern E — Passing `length` as a callable to a higher-order function

**Locations:**
- `zzz.R` — `string.bounding.box` (line 14)

**Original R context:**

`s2` is a list of character vectors (each element is the lines of one string). `sapply(s2, length)` applies `length` to each element and returns an integer vector counting the lines.

```r
# zzz.R:11-16
string.bounding.box <- function(s)
{
    s2 <- strsplit(s, "\n")
    rows <- sapply(s2, length)
    columns <- sapply(s2, function(x) max(nchar(x, "w")))
    list(columns = columns, rows = rows)
}
```

**Python equivalent:**

```python
import numpy as np

def string_bounding_box(s):
    # strsplit(s, "\n") splits each string by newline
    if isinstance(s, str):
        s = [s]
    s2 = [item.split("\n") for item in s]

    # sapply(s2, length) -> count lines per string
    rows = np.array([len(x) for x in s2])

    # sapply(s2, function(x) max(nchar(x, "w"))) -> max display width per string
    columns = np.array([max(len(line) for line in x) if x else 0 for x in s2])

    return {"columns": columns, "rows": rows}
```

**Explanation:**
- `sapply(s2, length)` in R applies the `length` function to each list element; the direct Python equivalent is a list comprehension `[len(x) for x in s2]`, optionally wrapped in `np.array(...)` to get a numpy integer array.
- R's `strsplit(s, "\n")` on a character vector always returns a list, even for a single string. In Python, wrapping a bare `str` in a list first ensures consistent list-of-lists structure.
- `nchar(x, "w")` counts display width; `len(line)` counts Unicode code points (a close approximation for ASCII text). For full Unicode width support, use the `wcwidth` library.

---

### 4.6 Pattern F — Validation: comparing length against a computed expected value

**Locations:**
- `rpart.class.R` — `rpart.class` (lines 29, 35)
- `rpartcallback.R` — `rpartcallback` (lines 35, 37, 47, 48, 53, 55, 64, 66, 77, 78, 84, 86)
- `rpart.R` — `rpart` (line 141)

**Original R context:**

These sites validate that a user-supplied or callback-returned object has the exact expected number of elements. The objects validated are numeric vectors, lists, and matrix-derived vectors.

```r
# rpart.class.R:29
if (length(temp) != numclass)
    stop("Wrong length for priors")

# rpart.class.R:35
if (length(temp2) != numclass^2)
    stop("Wrong length for loss matrix")

# rpart.R:141
if (length(cost) != nvar)
    stop("Cost vector is the wrong length")

# rpartcallback.R:35-36 (numy == 1 branch)
if (length(temp$label) != numresp)
    stop("User 'eval' function returned invalid label")

# rpartcallback.R:47-48
if (length(temp$goodness) != ncat - 1L ||
    length(temp$direction) != ncat)
    stop("Invalid return from categorical 'split' function")

# rpartcallback.R:53-55
if (length(temp$goodness) != (nback - 1L))
    stop("User 'split' function returned invalid goodness")
if (length(temp$direction) != (nback - 1L))
    stop("User 'split' function returned invalid direction")
```

**Python equivalent:**

```python
import numpy as np

# Validate a 1-D array / list length against an expected scalar
if len(temp) != numclass:
    raise ValueError("Wrong length for priors")

if len(temp2) != numclass ** 2:
    raise ValueError("Wrong length for loss matrix")

if len(cost) != nvar:
    raise ValueError("Cost vector is the wrong length")

# Validate dict/object fields returned from a callback
if len(temp["label"]) != numresp:
    raise ValueError("User 'eval' function returned invalid label")

if (len(temp["goodness"]) != ncat - 1 or
        len(temp["direction"]) != ncat):
    raise ValueError("Invalid return from categorical 'split' function")

if len(temp["goodness"]) != nback - 1:
    raise ValueError("User 'split' function returned invalid goodness")
if len(temp["direction"]) != nback - 1:
    raise ValueError("User 'split' function returned invalid direction")
```

**Explanation:**
- `length(x) != n` translates directly to `len(x) != n` in Python, whether `x` is a `list`, `numpy` array, or `dict` value.
- R's `stop(...)` raises an error that terminates execution; Python's equivalent is `raise ValueError(...)`.
- R's list field access `temp$label` becomes Python dict access `temp["label"]` (if `temp` is a `dict`) or attribute access `temp.label` (if `temp` is a named-tuple or dataclass).
- The `||` (OR) and `&&` (AND) operators in R become `or` and `and` in Python, with identical short-circuit semantics.
- Integer literal suffixes (`1L`, `2L`) in R have no Python equivalent; replace with plain integers.

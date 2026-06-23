# Conversion Guide: `rep` (R to Python)

---

## 1. Overview of `rep` in R

`rep(x, times, length.out, each)` is a base-R function that replicates the values of its first argument `x`. Its key parameters are:

- **`x`**: The object to replicate. Can be a scalar, character string, logical value, or a vector of any type.
- **`times`**: An integer scalar (or integer vector equal in length to `x`) specifying how many times each element of `x` is replicated. When a vector is passed for `times`, element `x[i]` is repeated `times[i]` times — this is the "rep-each-differently" mode.
- **`length.out`**: An integer giving the desired total length of the output. The input vector `x` is recycled (wrapped around) as many times as necessary to fill exactly `length.out` elements.
- **`each`**: An integer specifying that each element of `x` is replicated `each` times before moving to the next element.
- **`names`**: An optional named argument (available via `...`) that assigns names to the resulting vector.

The return value is always a vector of the same type as `x` (character, integer, double, logical).

---

## 2. Contextual Usage Analysis

Across the 21 CSV rows spanning seven R files, six distinct behavioral patterns appear:

| Pattern | Description | Representative call |
|---|---|---|
| A | Repeat a scalar `n` times (weights/cats/costs initialisation) | `rep(1, nrow(m))` |
| B | Repeat an integer scalar `n` times (zero-fill) | `rep(0L, ncol(X))` |
| C | Repeat a string `n` times (indent/label fill) | `rep(" ", spaces * 32L)` |
| D | Recycle an integer sequence to a fixed length | `rep(1L:xval, length.out = nobs)` |
| E | Repeat a logical vector element-wise by a parallel count vector | `rep(1L:ff.n, ff$ncompete + ff$nsurrogate + ...)` |
| F | Repeat a logical/scalar with `names` argument | `rep(1, nrow(x), names = rownames(x))` |

**Dominant usage**: Patterns A and B (scalar fill) account for the majority of calls and are used to initialise weight vectors, cost vectors, and integer category arrays that are later passed to C routines. These arrays are always 1-D with a length determined at runtime by a dimension of a data frame or matrix.

**Data types involved**:
- Input scalars: `1` (double), `1L` / `0L` (integer), `"<leaf>"` / `" "` (character), `TRUE` (logical).
- Input vectors: integer sequences (`1L:xval`, `1L:ff.n`), logical vectors (`is.ordered(x)`).
- Output: a vector of the same type as the input, always 1-D.

---

## 3. Python Conversion Strategy

**Primary library: `numpy`.**

Because `rep` is inherently vectorized and its outputs are immediately passed to matrix operations or C routines, `numpy` arrays are the natural equivalent in every pattern:

- `numpy.full(n, fill_value)` replaces scalar-fill calls and produces a typed 1-D array in one step.
- `numpy.tile` / `numpy.resize` replaces `length.out` recycling.
- `numpy.repeat(x, times)` replaces per-element replication (Pattern E).
- Python's built-in `[value] * n` on a plain list is acceptable only for small string arrays (Pattern C) where the result is immediately passed to a string join, not a numeric operation.

**dtype mapping**:
- `rep(1, n)` → `np.ones(n, dtype=float)` or `np.full(n, 1.0)`
- `rep(0L, n)` / `rep(1L, n)` → `np.zeros(n, dtype=int)` / `np.ones(n, dtype=int)`
- `rep(0, n)` → `np.zeros(n, dtype=float)` (Pattern B-variant in `xpred.rpart.R`)
- `rep("<leaf>", n)` / `rep(" ", n)` → `np.full(n, "<leaf>", dtype=object)` or `["<leaf>"] * n`
- `rep(TRUE, n)` → `np.ones(n, dtype=bool)` or `np.full(n, True)`

---

## 4. Step-by-Step Conversion Examples

### Pattern A — Repeat the double scalar `1` to initialise a weights / cost vector

**Locations:**
- `na.rpart.R`, `na.rpart`, lines 7, 12, 13, 14
- `rpart.R`, `rpart`, line 29
- `rpart.R`, `rpart`, line 139
- `xpred.rpart.R`, `xpred.rpart`, lines 50, 88
- `rpart.class.R`, `rpart.class`, line 13 (as part of a larger matrix expression)

**Original R context:**

```r
# na.rpart.R — used as a ones-column-vector for matrix-vector product
xmiss <- is.na(x)           # logical matrix: (nobs x ncols)
keep <- (xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)

# rpart.R — default weight vector when none is supplied
if (!length(wt)) wt <- rep(1, nrow(m))

# rpart.R — default cost vector
if (missing(cost)) cost <- rep(1, nvar)

# xpred.rpart.R — default weight vector
if (length(wt) == 0) wt <- rep(1, nobs)

# xpred.rpart.R — default cost vector
if (is.null(costs)) costs <- rep(1, nvar)

# rpart.class.R — loss matrix initialisation (flattened)
loss <- matrix(rep(1, numclass^2) - diag(numclass), numclass)
```

Input: a non-negative integer scalar (`ncol(xmiss)`, `nrow(m)`, `nvar`, `nobs`, `numclass^2`).
Return: a double vector of length `n` filled with `1.0`.

**Python equivalent:**

```python
import numpy as np

# na.rpart equivalent — ones-column-vector for row-sum via matmul
xmiss = np.isnan(x)                          # boolean array (nobs, ncols)
ones_col = np.ones(xmiss.shape[1], dtype=float)
keep = (xmiss @ ones_col) < xmiss.shape[1]

# rpart equivalent — default weight vector
if wt is None or len(wt) == 0:
    wt = np.ones(m.shape[0], dtype=float)

# cost vector default
cost = np.ones(nvar, dtype=float)

# rpart.class equivalent — loss matrix (ones minus identity)
loss = np.ones(numclass ** 2, dtype=float).reshape(numclass, numclass) - np.eye(numclass)
```

**Explanation:**
- `rep(1, n)` → `np.ones(n, dtype=float)`. The `dtype=float` matches R's default numeric (double) type.
- The matrix-vector product `xmiss %*% rep(1, ncol(xmiss))` is a row-sum; it can also be written as `xmiss.sum(axis=1)`, but `@ ones_col` is the most faithful structural translation.
- `matrix(rep(1, numclass^2) - diag(numclass), numclass)` becomes `np.ones((numclass, numclass)) - np.eye(numclass)` directly; there is no need to flatten then reshape because numpy arithmetic already operates element-wise on 2-D arrays.

---

### Pattern B — Repeat the integer scalar `0L` or `1L` to initialise an integer array

**Locations:**
- `rpart.R`, `rpart`, line 83: `rep(0L, ncol(X))`
- `pred.rpart.R`, `pred.rpart`, line 20: `rep(0L, 2L)`
- `xpred.rpart.R`, `xpred.rpart`, line 52: `rep(0, nvar)`

**Original R context:**

```r
# rpart.R — integer category-count array for C call
cats <- rep(0L, ncol(X))

# pred.rpart.R — two-element integer zero vector for csplit dimension
as.integer(if (is.null(fit$csplit)) rep(0L, 2L) else dim(fit$csplit))

# xpred.rpart.R — double zero array for cats
cats <- rep(0, nvar)
```

Input: a small or runtime-sized integer scalar.
Return: an integer or double vector of zeros.

**Python equivalent:**

```python
import numpy as np

# cats integer array
cats = np.zeros(X.shape[1], dtype=int)

# two-element zero vector for csplit dimension fallback
csplit_dim = np.zeros(2, dtype=int) if fit_csplit is None else np.array(fit_csplit.shape, dtype=int)

# cats double array (xpred.rpart)
cats = np.zeros(nvar, dtype=float)
```

**Explanation:**
- `rep(0L, n)` → `np.zeros(n, dtype=int)`. The `L` suffix in R denotes an integer literal; use `dtype=int` in numpy.
- `rep(0, n)` (without `L`) → `np.zeros(n, dtype=float)` since R's undecorated `0` is a double.
- `rep(0L, 2L)` → `np.zeros(2, dtype=int)`. Both arguments are integer literals; the size `2` is a plain Python int when passed to numpy.

---

### Pattern C — Repeat a string `n` times to build an indent or label vector

**Locations:**
- `print.rpart.R`, `print.rpart`, line 11: `rep(" ", spaces * 32L)`
- `print.rpart.R`, `print.rpart`, line 23: `rep(" ", length(depth))`
- `labels.rpart.R`, `labels.rpart`, line 87: `rep("<leaf>", n)`
- `text.rpart.R`, `text.rpart`, line 50: `rep(TRUE, nrow(frame))`

**Original R context:**

```r
# print.rpart.R — create a long blank string then take substrings
indent <- paste(rep(" ", spaces * 32L), collapse = "")
# ...
term <- rep(" ", length(depth))
term[frame$var == "<leaf>"] <- "*"

# labels.rpart.R — fill entire label vectors before overwriting interiors
ltemp <- rtemp <- rep("<leaf>", n)
ltemp[whichrow] <- lsplit
rtemp[whichrow] <- rsplit

# text.rpart.R — boolean mask initialised to all-TRUE
leaves <- if (all) rep(TRUE, nrow(frame)) else frame$var == "<leaf>"
```

Input: a scalar string or boolean and an integer length.
Return: a character or logical vector of length `n`.

**Python equivalent:**

```python
import numpy as np

# print.rpart — long blank string via join
indent = " " * (spaces * 32)             # Python string repetition, no array needed

# term marker array
term = np.full(len(depth), " ", dtype=object)
term[frame["var"] == "<leaf>"] = "*"

# labels.rpart — label fill-then-overwrite
ltemp = np.full(n, "<leaf>", dtype=object)
rtemp = np.full(n, "<leaf>", dtype=object)
ltemp[whichrow] = lsplit
rtemp[whichrow] = rsplit

# text.rpart — boolean mask
leaves = np.ones(len(frame), dtype=bool) if all_ else (frame["var"] == "<leaf>").values
```

**Explanation:**
- `rep(" ", spaces * 32L)` followed immediately by `paste(..., collapse = "")` collapses the vector into a single string. In Python this is just string multiplication: `" " * (spaces * 32)`.
- For `term` and label arrays that are later indexed and mutated element-wise, `np.full(n, value, dtype=object)` is preferred over a plain list because it supports boolean array indexing on the left-hand side identical to R's vector assignment.
- `rep(TRUE, nrow(frame))` → `np.ones(nrow, dtype=bool)`. The `all` parameter name is shadowed by Python's built-in, so rename it to `all_`.

---

### Pattern D — Recycle an integer sequence to a fixed length (`length.out`)

**Locations:**
- `rpart.R`, `rpart`, line 119: `rep(1L:xval, length.out = nobs)`
- `xpred.rpart.R`, `xpred.rpart`, line 70: `rep(1L:xval, length.out = nobs)`

**Original R context:**

```r
# Both files — create cross-validation fold assignments by wrapping 1:xval
xgroups <- sample(rep(1L:xval, length.out = nobs), nobs, replace = FALSE)
```

`1L:xval` generates an integer sequence `[1, 2, ..., xval]`. `rep(..., length.out = nobs)` cycles through that sequence, truncating or extending to exactly `nobs` elements. The result is then randomly permuted by `sample`.

Input: integer scalar `xval` (number of folds), integer scalar `nobs` (number of observations).
Return: a 1-D integer vector of length `nobs` whose values cycle through `1..xval`.

**Python equivalent:**

```python
import numpy as np

# Replicate the sequence 1..xval recycled to length nobs, then shuffle
seq = np.arange(1, xval + 1, dtype=int)          # [1, 2, ..., xval]
xgroups_ordered = np.resize(seq, nobs)            # recycles to length nobs
xgroups = np.random.choice(xgroups_ordered, size=nobs, replace=False)
```

**Explanation:**
- `1L:xval` → `np.arange(1, xval + 1, dtype=int)`. R sequences are 1-based and inclusive on both ends; numpy's `arange` is exclusive on the upper end, so add 1.
- `rep(..., length.out = nobs)` → `np.resize(seq, nobs)`. `np.resize` wraps the input array cyclically to produce exactly `nobs` elements, which is the precise semantics of `rep` with `length.out`.
- `sample(..., nobs, replace = FALSE)` → `np.random.choice(..., size=nobs, replace=False)`.
- Note: `np.tile` repeats the full sequence a fixed number of times and would overshoot or undershoot when `nobs` is not a multiple of `xval`; `np.resize` is the correct choice.

---

### Pattern E — Per-element replication using a parallel count vector (`times` as a vector)

**Locations:**
- `snip.rpart.R`, `snip.rpart`, line 52: `rep(1L:ff.n, ff$ncompete + ff$nsurrogate + (ff$var != "<leaf>"))`

**Original R context:**

```r
ff <- x$frame
ff.n <- length(id)                   # total number of rows in the frame
# Build a "row-tag" for every entry in x$splits
n.split <- rep(1L:ff.n, ff$ncompete + ff$nsurrogate + (ff$var != "<leaf>"))
split <- x$splits[match(n.split, keepit, 0L) > 0L, , drop = FALSE]
```

Here `rep` is called with a *vector* for `times`: `ff$ncompete + ff$nsurrogate + (ff$var != "<leaf>")` is an integer vector of length `ff.n`, one entry per frame row. Element `i` of `1L:ff.n` is repeated `times[i]` times. This "run-length expansion" maps each frame row index to every split row that belongs to it.

Input: integer sequence `1..ff.n` (length `ff.n`), integer vector `times` (length `ff.n`).
Return: 1-D integer vector whose total length equals `sum(times)`.

**Python equivalent:**

```python
import numpy as np

ff_n = len(id)
times = (ff["ncompete"] + ff["nsurrogate"] + (ff["var"] != "<leaf>")).to_numpy(dtype=int)
n_split = np.repeat(np.arange(1, ff_n + 1, dtype=int), times)
split_mask = np.isin(n_split, keepit)         # equivalent to match(n_split, keepit, 0L) > 0L
split = x_splits[split_mask]
```

**Explanation:**
- When `times` is a vector, `rep(x, times)` → `np.repeat(x, times)`. Both produce an array where `x[i]` appears `times[i]` consecutive times.
- `1L:ff.n` → `np.arange(1, ff_n + 1, dtype=int)` (1-based, inclusive upper bound in R).
- `ff$var != "<leaf>"` is a logical vector; in R it is coerced to integer (0/1) when added to the integer counts. In numpy, boolean arrays are coerced to int automatically in arithmetic expressions, so `.to_numpy(dtype=int)` on the pandas Series or `array.astype(int)` achieves the same.
- `match(n_split, keepit, 0L) > 0L` → `np.isin(n_split, keepit)`.

---

### Pattern F — Repeat a scalar with a `names` argument

**Locations:**
- `pred.rpart.R`, `pred.rpart`, line 7: `rep(1, nrow(x), names = rownames(x))`

**Original R context:**

```r
# Early return for a root-only tree: a named vector of 1s
if (nrow(frame) == 1L)
    return(structure(rep(1, nrow(x), names = rownames(x))))
```

`rep` does not directly accept a `names` argument in standard R; the names are attached via `structure(...)`. The result is a double vector of `1`s of length `nrow(x)`, with each element named by the corresponding row name of the predictor matrix.

Input: double scalar `1`, integer scalar `nrow(x)`, character vector of names.
Return: a named double vector.

**Python equivalent:**

```python
import numpy as np
import pandas as pd

# Return a named Series of 1s indexed by row names
if frame.shape[0] == 1:
    return pd.Series(np.ones(x.shape[0], dtype=float), index=x.index)
```

**Explanation:**
- The `names` attribute in R is the closest equivalent to a pandas `Index`. A `pd.Series` preserves the row labels and supports the named-element access patterns that follow from this return value.
- If downstream code treats the result as a plain numpy array (ignoring names), `np.ones(x.shape[0], dtype=float)` suffices and the index can be stored separately.
- `structure(rep(...), ...)` is a wrapper that attaches attributes; in Python, constructing a `pd.Series` achieves both the data and the label assignment in one step.

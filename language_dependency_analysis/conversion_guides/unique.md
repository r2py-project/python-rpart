# Conversion Guide: `unique` (R to Python)

---

## 1. Overview of `unique` in R

`unique()` is a base R function that returns a vector, data frame, or array with duplicate elements removed. It preserves the order of first occurrence.

**Signature:**
```r
unique(x, incomparables = FALSE, ...)
```

**Key characteristics:**
- Input `x`: any R vector, list, matrix, or data frame.
- Returns an object of the same type as `x`, containing only the first occurrence of each distinct value.
- Order is preserved: elements appear in the order they are first encountered.
- Handles `NA` values: two `NA` entries are considered equal and only one is retained.
- Works element-wise on atomic vectors (integer, double, character, logical), making it directly analogous to set deduplication over ordered sequences.

---

## 2. Contextual Usage Analysis

All eleven call sites in the rpart codebase use `unique` on a **1-D atomic vector** (integer or double). No matrix or data-frame deduplication is performed. Three recurring patterns emerge:

**Pattern A — Deduplicate a subset of a factor/character column (label deduplication)**
- `printcp.R` line 18: deduplicates character-like factor values from a data-frame column after Boolean subsetting.

**Pattern B — Deduplicate an integer group-assignment vector, then count distinct groups**
- `rpart.R` lines 122 and 131: `xval <- length(unique(xgroups))` — deduplicates an integer vector and immediately takes its length to count distinct cross-validation fold IDs.
- `xpred.rpart.R` lines 73 and 82: identical pattern.

**Pattern C — Deduplicate a numeric vector (prior to sorting or downstream computation)**
- `roc.rpart.R` line 12: concatenates fixed sentinel values `0` and `1` with a numeric probability column from a matrix, then deduplicates and sorts.
- `rpart.exp.R` line 32: deduplicates event times filtered by a status mask, then sorts to get ordered unique death times.
- `rpartcallback.R` lines 46 and 76: deduplicates a numeric slice of `xback` to count distinct categorical variable levels.
- `prune.rpart.R` line 10: deduplicates a numeric vector produced by `pmax` to find canonical CP-table rows to keep.
- `snip.rpart.R` line 16: deduplicates an integer node-ID vector passed as an argument.

All usages operate on **1-D numeric or integer vectors of moderate length** (never matrices or data frames), so vectorized NumPy deduplication is the correct target.

---

## 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy.unique`).

**Why NumPy:**
- R's `unique()` on a 1-D atomic vector is structurally equivalent to `numpy.unique()` with `return_index` unused and with `axis=None` (the default).
- NumPy operates on arrays element-by-element, matching R's vectorized semantics.
- All call sites in this codebase involve numeric (float64) or integer arrays, which map directly to NumPy dtypes.

**Critical behavioral difference — sort order:**
- `numpy.unique()` **always returns a sorted array**, whereas R's `unique()` **preserves first-occurrence order** (unsorted).
- When the downstream code explicitly calls `sort()` on the result (Pattern C, `roc.rpart.R` and `rpart.exp.R`), `numpy.unique()` is a drop-in replacement.
- When insertion order must be preserved (Pattern A, B, and some Pattern C sites), use the idiom:

```python
_, idx = np.unique(arr, return_index=True)
result = arr[np.sort(idx)]
```

This retrieves only the first-occurrence indices, sorts them, and indexes back into the original array, reproducing R's order-preserving behaviour.

Alternatively, for purely Pythonic code without a NumPy dependency on the deduplication step, `dict.fromkeys()` preserves insertion order in Python 3.7+:

```python
result = list(dict.fromkeys(arr))
```

However, `numpy.unique` is preferred throughout because all downstream consumers in rpart operate on NumPy arrays.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Pattern A — Deduplicate a character/factor column after Boolean masking

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/printcp.R`, function `printcp`, line 18.

**Original R Context:**

`frame` is an rpart frame data frame. `frame$var` is a factor column of variable names; `<leaf>` marks terminal nodes. The Boolean mask `!leaves` selects non-leaf rows.

```r
# frame$var : factor vector of variable names including "<leaf>"
# leaves    : logical vector, TRUE where var == "<leaf>"
used <- unique(frame$var[!leaves])
# used: character/factor vector of variable names actually used in splits,
#       in order of first appearance, with no duplicates
```

**Python Equivalent:**

```python
import numpy as np

# frame_var : np.ndarray of dtype str (or list of strings)
# leaves    : np.ndarray of dtype bool

non_leaf_vars = frame_var[~leaves]           # boolean-mask subset

# Order-preserving deduplication (matches R's unique behaviour)
_, idx = np.unique(non_leaf_vars, return_index=True)
used = non_leaf_vars[np.sort(idx)]
# used: 1-D str array, unique variable names in first-occurrence order
```

**Explanation:**
- `~leaves` is the NumPy Boolean negation, equivalent to R's `!leaves`.
- `np.unique` alone would sort alphabetically; pairing it with `return_index=True` and re-sorting the indices reproduces R's insertion-order preservation.
- The downstream call `sort(as.character(used))` in `printcp` explicitly sorts afterwards, so in this specific context `np.unique(non_leaf_vars)` (which returns a sorted result) would also be correct.

---

### 4.2 Pattern B — Deduplicate an integer group vector and count distinct values

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, function `rpart`, lines 122 and 131.
- `/groups/jli9/Yufei/python-rpart/rpart/R/xpred.rpart.R`, function `xpred.rpart`, lines 73 and 82.

**Original R Context:**

`xgroups` is an integer vector of fold IDs supplied by the user (one value per observation). `unique` extracts the distinct fold IDs and `length` counts them.

```r
# xgroups : integer vector, length == nobs, values are fold labels
xgroups <- xval          # user-supplied fold assignment vector
xval <- length(unique(xgroups))
# xval: scalar integer — number of distinct cross-validation folds
```

**Python Equivalent:**

```python
import numpy as np

# xgroups : np.ndarray of dtype int, shape (nobs,)
xgroups = xval_array           # user-supplied fold assignment array
xval = len(np.unique(xgroups))
# xval: int — number of distinct cross-validation folds
```

**Explanation:**
- `np.unique` on a 1-D integer array returns all unique values sorted. Wrapping with `len()` reproduces `length(unique(...))`.
- The sort order of the unique values does not matter here because only the count is used.
- No order-preservation workaround is needed.

---

### 4.3 Pattern C1 — Deduplicate then sort a numeric vector built from concatenation with sentinels

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/roc.rpart.R`, function `roc.rpart`, line 12.

**Original R Context:**

`object$frame$yprob[endnodes, 2L]` is a numeric column of class probabilities. Sentinels `0` and `1` are prepended, the whole vector is deduplicated and sorted.

```r
# yprob_col : numeric vector — predicted class 2 probability at leaf nodes
cutoffs <- sort(unique(c(0, 1, yprob_col)))
# cutoffs: sorted numeric vector with guaranteed 0 and 1 endpoints, no duplicates
```

**Python Equivalent:**

```python
import numpy as np

# yprob_col : np.ndarray of dtype float64, shape (n_endnodes,)
combined = np.concatenate([[0.0, 1.0], yprob_col])
cutoffs = np.unique(combined)   # np.unique returns sorted unique values
# cutoffs: sorted float64 array, always includes 0.0 and 1.0
```

**Explanation:**
- `np.concatenate` replaces R's `c()` for joining arrays.
- Because the result is immediately sorted in R (`sort(unique(...))`), `np.unique()` is a direct drop-in: it both deduplicates and sorts in one call.
- No order-preservation workaround is required here.

---

### 4.4 Pattern C2 — Deduplicate event times from a filtered numeric vector, then sort

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`, function `rpart.exp`, line 32.

**Original R Context:**

`time` is a numeric vector of follow-up times. `status` is a binary integer vector (1 = event occurred). The goal is to obtain sorted unique event times.

```r
# time   : numeric vector, length n
# status : integer vector, 0 or 1, length n
dtimes <- sort(unique(time[status == 1]))
# dtimes: sorted numeric vector of unique observed event/death times
```

**Python Equivalent:**

```python
import numpy as np

# time   : np.ndarray of dtype float64, shape (n,)
# status : np.ndarray of dtype int,     shape (n,)
dtimes = np.unique(time[status == 1])
# dtimes: sorted float64 array of unique observed event times
# (np.unique both deduplicates and sorts, matching sort(unique(...)) in R)
```

**Explanation:**
- Boolean indexing `time[status == 1]` is identical in NumPy and R.
- `np.unique` replaces `sort(unique(...))` in one step.
- The sentinel concatenation from Pattern C1 is absent here; this is a pure filter-deduplicate-sort pipeline.

---

### 4.5 Pattern C3 — Deduplicate a numeric slice of a pre-allocated buffer, count distinct levels

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpartcallback.R`, function `rpartcallback`, lines 46 and 76.

**Original R Context:**

Inside a quoted expression that is evaluated by C callback machinery, `xback` is a pre-allocated double vector filled by C code. `n2 = -nback` is the number of observations being processed. `ncat` counts the distinct categorical levels present in the current node.

```r
# xback : numeric vector (pre-allocated buffer, filled by C per callback)
# n2    : integer scalar — number of active observations
ncat <- length(unique(xback[1L:n2]))
# ncat: integer scalar — number of distinct category codes in this node
```

**Python Equivalent:**

```python
import numpy as np

# xback : np.ndarray of dtype float64 (pre-allocated buffer filled by C layer)
# n2    : int — number of active observations
ncat = len(np.unique(xback[:n2]))
# ncat: int — number of distinct category codes in this node
```

**Explanation:**
- R's 1-based slice `xback[1L:n2]` maps to Python's 0-based `xback[:n2]` (equivalent to `xback[0:n2]`).
- `len(np.unique(...))` reproduces `length(unique(...))`.
- Only the count matters; sort order of unique values is irrelevant.

---

### 4.6 Pattern C4 — Deduplicate a numeric vector to identify canonical rows for index lookup

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/prune.rpart.R`, function `prune.rpart`, line 10.

**Original R Context:**

`tree$cptable[, 1L]` is the CP column of the complexity-parameter table (a numeric vector). `pmax(..., cp)` clamps all values to at least `cp`. `unique` finds the distinct clamped values, and `match` maps them back to original positions to select the rows to keep.

```r
# cp_col : numeric vector — first column of the CP table (one entry per row)
# cp     : scalar double — pruning threshold
temp <- pmax(cp_col, cp)         # clamp: replace values below cp with cp
keep <- match(unique(temp), temp)
# keep: integer vector of first-occurrence row indices (1-based) in temp
# These are the row indices of tree$cptable to retain after pruning
```

**Python Equivalent:**

```python
import numpy as np

# cp_col : np.ndarray of dtype float64, shape (n_rows,)
# cp     : float scalar — pruning threshold
temp = np.maximum(cp_col, cp)    # element-wise maximum, equivalent to pmax

# Order-preserving unique: reproduce R's unique() first-occurrence semantics
_, idx = np.unique(temp, return_index=True)
keep = np.sort(idx)              # sorted first-occurrence positions (0-based)

# keep contains 0-based row indices; use keep to slice the cptable
# (In R these are 1-based; subtract 1 when porting index arithmetic)
```

**Explanation:**
- `np.maximum(cp_col, cp)` is the element-wise equivalent of R's `pmax(cp_col, cp)`.
- R's `match(unique(temp), temp)` finds the **first occurrence** index of each unique value. This is precisely what `np.unique(..., return_index=True)` provides via `idx`.
- Sorting `idx` is necessary because `np.unique` returns unique values in ascending order; the corresponding `idx` values must be sorted to restore first-occurrence positional order.
- Adjust for R's 1-based indexing: `keep` in Python is 0-based, whereas R's `keep` is 1-based.

---

### 4.7 Pattern C5 — Deduplicate an integer node-ID vector passed as a function argument

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/snip.rpart.R`, function `snip.rpart`, line 16.

**Original R Context:**

`toss` is an integer vector of node IDs supplied by the caller. Deduplication ensures no node is processed twice before looking up row positions.

```r
# toss : integer vector — node IDs to prune (may contain duplicates)
toss <- unique(toss)
# toss: integer vector, duplicate node IDs removed, order of first occurrence preserved
```

**Python Equivalent:**

```python
import numpy as np

# toss : np.ndarray of dtype int, shape (k,) — node IDs, possibly with duplicates

# Order-preserving deduplication
_, idx = np.unique(toss, return_index=True)
toss = toss[np.sort(idx)]
# toss: 1-D int array, unique node IDs in first-occurrence order
```

**Explanation:**
- First-occurrence order is preserved here because downstream logic processes `toss` sequentially and uses `match(toss, id, 0L)` to look up row positions; changing the order would not alter correctness, but preserving it matches R's behaviour exactly.
- If order does not matter for a given downstream use, `toss = np.unique(toss)` (sorted output) is simpler and equally correct.

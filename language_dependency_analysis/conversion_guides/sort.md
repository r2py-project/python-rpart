# R to Python Conversion Guide: `sort`

---

## 1. Overview of `sort` in R

`sort` is a base R function that returns a sorted copy of its input vector, leaving the original object unchanged. Its signature is:

```r
sort(x, decreasing = FALSE, na.last = NA, ...)
```

Key characteristics:

- **Input (`x`):** An atomic vector — numeric, integer, character, logical, or complex. It does not operate directly on lists, data frames, or matrices.
- **Output:** A new vector of the same type and length as `x` (after `NA` removal, depending on `na.last`), sorted in ascending order by default.
- **`decreasing`:** Logical flag. `FALSE` (default) produces ascending order; `TRUE` produces descending order.
- **`na.last`:** Controls `NA` handling. The default `NA` removes `NA` values from the result. `TRUE` places them at the end; `FALSE` places them at the front.
- **Named vectors:** When `x` is a named numeric vector, `sort` preserves the names alongside their corresponding values, returning a reordered named vector. This is a critical distinction from bare Python lists.
- **Character vectors:** Sorting is locale-sensitive and lexicographic, following the current locale's collation rules.
- `sort` is distinct from `order` (which returns the permutation index) and `rank` (which returns ranks). It is the direct equivalent of an in-place sort, but it always returns a new object.

---

## 2. Contextual Usage Analysis

Across the six call sites in the rpart package, `sort` is applied in three functionally distinct patterns:

**Pattern A — Sorting a named numeric vector in descending order (importance.R, line 40)**

`import` is the output of `tapply(..., sum)`, which produces a named numeric vector mapping variable names to aggregated importance scores. `c(import)` strips the array-like dimension attributes while keeping names, yielding a plain named numeric vector. `sort(..., decreasing = TRUE)` reorders it from largest to smallest and is the direct return value of the `importance()` function. Callers expect a named numeric vector.

**Pattern B — Sorting a character vector for display (printcp.R, line 22)**

`used` is a character vector of variable names extracted from the rpart frame. `as.character(used)` ensures the type is a plain character vector (factor levels are dropped). `sort(as.character(used))` alphabetically sorts the names before printing them to the console. The result is passed directly to `print()` and is not assigned.

**Pattern C — Sorting a deduplicated numeric vector to form an ordered domain (roc.rpart.R line 12, rpart.exp.R line 32, snip.rpart.R lines 65 and 71)**

These four calls all combine `sort` with other operations to build ordered numeric arrays used in downstream indexing or iteration:

- **`roc.rpart.R` line 12:** `sort(unique(c(0, 1, object$frame$yprob[endnodes, 2L])))` — appends the sentinel values 0 and 1 to a numeric vector of predicted class-2 probabilities extracted from end-node rows, deduplicates, then sorts ascending. The result (`cutoffs`) drives a loop over classification thresholds and is used for matrix row selection via `outer()`.
- **`rpart.exp.R` line 32:** `sort(unique(time[status == 1]))` — filters a numeric time vector to death events only, deduplicates, then sorts ascending. The result (`dtimes`) is a strictly increasing sequence of unique death times passed as a `double` array to a `.Call` C function (`C_rpartexp2`).
- **`snip.rpart.R` lines 65 and 71:** `sort(c(keepit, newleaf))` — concatenates two integer index vectors (rows to keep and new leaf rows), then sorts ascending. The result is used directly for integer row-subscripting of `x$frame` (line 65) and for building a mapping via `match()` (line 71). Maintaining ascending order is required for correct parent-child node matching.

**Summary of data types:**

| Call site | Input type | `decreasing` | Output role |
|---|---|---|---|
| importance.R:40 | named numeric vector | `TRUE` | function return value |
| printcp.R:22 | character vector | `FALSE` (default) | passed to `print()` |
| roc.rpart.R:12 | numeric vector (probabilities + sentinels) | `FALSE` (default) | threshold iteration / matrix indexing |
| rpart.exp.R:32 | numeric vector (event times) | `FALSE` (default) | passed to `.Call` C function |
| snip.rpart.R:65 | integer vector (row indices) | `FALSE` (default) | row subscript for data frame |
| snip.rpart.R:71 | integer vector (row indices) | `FALSE` (default) | argument to `match()` |

---

## 3. Python Conversion Strategy

**Primary library: `numpy`**

`numpy.sort` and `numpy.argsort` are the canonical vectorized equivalents of R's `sort`. All numeric uses of `sort` in the rpart codebase involve 1-D arrays of floating-point or integer data, which map directly to `numpy` 1-D arrays (`np.ndarray`). The key reasons for preferring `numpy`:

- R's `sort` on numeric vectors is inherently vectorized; `numpy.sort` matches this exactly and returns a new sorted array without modifying the original.
- `numpy.unique` already returns a sorted array, so `sort(unique(...))` collapses to a single `np.unique(...)` call.
- The `decreasing = TRUE` parameter maps to `[::-1]` (reverse slice) or `np.sort(...)[::-1]`, since `numpy.sort` has no `descending` kwarg in its default axis-based form. Alternatively, `np.flip(np.sort(...))` is idiomatic.
- For the named numeric vector case (Pattern A), `pandas.Series` is the appropriate container: it carries both values and a string index, directly mirroring R's named vector semantics.

**Character vector sorting (Pattern B)** maps to Python's built-in `sorted()` or `list.sort()` on a list of strings, since `numpy` string sorting is less ergonomic for display purposes. `sorted()` is the direct functional equivalent: it returns a new sorted list, leaving the original unchanged, exactly like R's `sort`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Named Numeric Vector, Descending Order

**Locations:** `rpart/R/importance.R`, function `importance`, line 40.

**Original R context:**

`import` is a named numeric vector (names are variable-name strings, values are numeric importance scores) produced by `tapply`. `c(import)` coerces it to a plain named vector. The result is the return value of the function and must preserve name-value pairing in descending score order.

```r
# import: named numeric vector, e.g. c(age=5.2, income=3.1, size=7.8)
result <- sort(c(import), decreasing = TRUE)
# result: named numeric vector sorted high-to-low
# e.g. c(size=7.8, age=5.2, income=3.1)
```

**Python equivalent:**

```python
import pandas as pd

# import_ is a pd.Series with string index (variable names) and float values
# e.g. import_ = pd.Series({'age': 5.2, 'income': 3.1, 'size': 7.8})
result = import_.sort_values(ascending=False)
# result: pd.Series(['size'->7.8, 'age'->5.2, 'income'->3.1])
```

**Explanation:**

`tapply(..., sum)` in R maps directly to a `pandas.Series` (or the result of `groupby(...).sum()`). `pd.Series.sort_values(ascending=False)` is the idiomatic equivalent of `sort(..., decreasing = TRUE)` on a named vector: it returns a new `Series` with values sorted descending while keeping name-value alignment intact. The `c(import)` coercion in R has no Python equivalent needed — a `pd.Series` already has the right structure.

---

### 4.2 Pattern B — Character Vector, Ascending Alphabetical Sort for Display

**Locations:** `rpart/R/printcp.R`, function `printcp`, line 22.

**Original R context:**

`used` is a character vector of variable names that appeared as split variables in the rpart frame. `as.character(used)` ensures it is a plain character vector. The sort result is passed immediately to `print()` for console display. No assignment occurs; the sorted list is not stored.

```r
# used: character vector, e.g. c("income", "age", "size")
print(sort(as.character(used)), quote = FALSE)
# prints: [1] age    income size
```

**Python equivalent:**

```python
# used: list of str, e.g. ['income', 'age', 'size']
print(sorted(used))
# prints: ['age', 'income', 'size']
```

**Explanation:**

Python's built-in `sorted()` is the exact functional equivalent of R's `sort` on a character vector: it accepts any iterable of strings, returns a new sorted list in ascending lexicographic order, and leaves the original unchanged. No `numpy` import is needed here because there are no vectorized numeric operations. The `as.character()` conversion in R is unnecessary in Python if `used` is already a list of strings. If `used` is a `numpy` array of strings or a `pandas` Index, `sorted(used.tolist())` or `used.sort_values().tolist()` can be used instead.

---

### 4.3 Pattern C1 — Deduplication + Sort of a Numeric Vector with Sentinel Values

**Locations:** `rpart/R/roc.rpart.R`, function `roc.rpart`, line 12.

**Original R context:**

`object$frame$yprob[endnodes, 2L]` is a numeric vector of predicted positive-class probabilities at leaf nodes. The sentinels 0 and 1 are appended to ensure the ROC curve spans the full range. `unique` removes duplicates and `sort` returns them in ascending order. The result (`cutoffs`) is used as the row-dimension argument to `outer()` and as threshold values in a loop.

```r
# yprob_col: numeric vector of probabilities, e.g. c(0.3, 0.7, 0.3, 0.9)
cutoffs <- sort(unique(c(0, 1, yprob_col)))
# cutoffs: c(0.0, 0.3, 0.7, 0.9, 1.0)
```

**Python equivalent:**

```python
import numpy as np

# yprob_col: np.ndarray of float, e.g. np.array([0.3, 0.7, 0.3, 0.9])
cutoffs = np.unique(np.concatenate(([0.0, 1.0], yprob_col)))
# cutoffs: np.array([0.0, 0.3, 0.7, 0.9, 1.0])
```

**Explanation:**

`np.unique` returns a sorted, deduplicated array in a single call, making the R idiom `sort(unique(...))` collapse into one function. The sentinels `0` and `1` are prepended via `np.concatenate` (or equivalently `np.insert`). Since `np.unique` always sorts ascending, no additional sort step is needed. The output is a 1-D `float64` ndarray suitable for use with `np.outer` and for iteration.

---

### 4.4 Pattern C2 — Sort of Deduplicated Numeric Event Times (No Sentinels)

**Locations:** `rpart/R/rpart.exp.R`, function `rpart.exp`, line 32.

**Original R context:**

`time` is a numeric vector of observation times extracted from the survival response matrix `y`. `status == 1` is a logical mask selecting death events. `unique` removes duplicate death times; `sort` returns them in strictly increasing order. The result (`dtimes`) is passed as a `double` array to a C function via `.Call`.

```r
# time:   numeric vector, e.g. c(1.5, 2.0, 1.5, 3.1, 2.0, 4.0)
# status: integer vector, e.g. c(1,   1,   0,   1,   0,   1  )
dtimes <- sort(unique(time[status == 1]))
# dtimes: c(1.5, 2.0, 3.1, 4.0)
```

**Python equivalent:**

```python
import numpy as np

# time:   np.ndarray of float64, shape (n,)
# status: np.ndarray of int, shape (n,)
dtimes = np.unique(time[status == 1])
# dtimes: np.array([1.5, 2.0, 3.1, 4.0])
```

**Explanation:**

Boolean indexing `time[status == 1]` in numpy is the direct equivalent of R's `time[status == 1]`. `np.unique` then deduplicates and sorts in one call. The result is a 1-D `float64` ndarray. Because this array is subsequently passed to a C extension (replacing `.Call`), ensuring it is contiguous and `float64` typed (via `np.ascontiguousarray(dtimes, dtype=np.float64)`) is important for ctypes or cffi interop.

---

### 4.5 Pattern C3 — Sort of Concatenated Integer Index Vectors

**Locations:** `rpart/R/snip.rpart.R`, function `snip.rpart`, lines 65 and 71.

**Original R context:**

`keepit` is an integer vector of 1-based row positions to retain; `newleaf` is an integer vector of 1-based row positions of nodes converted to leaves. Both are indices into `ff` (the rpart frame). `c(keepit, newleaf)` concatenates them; `sort` orders them ascending so that the resulting row-subscript is in natural frame order. The same sorted index appears twice: once to subset `x$frame` (line 65) and once to build a node-ID mapping via `match()` (line 71).

```r
# keepit:  integer vector, e.g. c(1L, 3L, 5L)
# newleaf: integer vector, e.g. c(7L, 2L)
sorted_idx <- sort(c(keepit, newleaf))
# sorted_idx: c(1L, 2L, 3L, 5L, 7L)

x$frame <- ff[sorted_idx, ]          # line 65
id3 <- id[sorted_idx]                # line 71
```

**Python equivalent:**

```python
import numpy as np

# keepit:  np.ndarray of int or Python list of int (0-based indices in Python)
# newleaf: np.ndarray of int or Python list of int (0-based indices in Python)
sorted_idx = np.sort(np.concatenate([keepit, newleaf]))

frame = ff.iloc[sorted_idx]          # line 65 equivalent (pandas DataFrame)
id3 = id_arr[sorted_idx]             # line 71 equivalent (numpy array)
```

**Explanation:**

`np.concatenate` replaces R's `c()` for joining arrays. `np.sort` (or `np.ndarray.sort` in-place, though a copy is preferred here to match R semantics) sorts the concatenated integer array ascending. The critical translation concern is **index base**: R uses 1-based indices throughout, so when porting, all `keepit` and `newleaf` values must be decremented by 1 for use with Python's 0-based indexing. For `pandas` DataFrames, `.iloc[sorted_idx]` performs positional row selection matching R's `ff[sorted_idx, ]`. For a `numpy` array `id_arr`, direct integer-array indexing `id_arr[sorted_idx]` is equivalent to R's `id[sorted_idx]`. There is no need for `np.unique` here because `keepit` and `newleaf` are already disjoint sets by construction in the algorithm.

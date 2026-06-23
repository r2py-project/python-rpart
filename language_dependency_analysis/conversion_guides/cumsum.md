# Conversion Guide: `cumsum` (R to Python)

---

## 1. Overview of `cumsum` in R

`cumsum(x)` computes the **cumulative sum** of a numeric vector `x`. It returns a vector of the same length as the input, where each element `i` is the sum of elements `x[1]` through `x[i]`.

- **Input:** A numeric (or logical, which is coerced to integer) vector.
- **Output:** A numeric vector of the same length as the input. `NA` values propagate: once a `NA` is encountered, all subsequent elements in the result are `NA`.
- **Key property:** It is inherently a vectorized, sequential operation with no configurable arguments.

Example:
```r
cumsum(c(1, 2, 3, 4))
# [1]  1  3  6 10
```

---

## 2. Contextual Usage Analysis

Across all seven occurrences in the rpart package, `cumsum` is used exclusively to build **index offset arrays** into flat lookup tables (primarily `fit$splits` or `x$splits`). The rpart tree's frame stores split metadata in a single flat matrix; `cumsum` accumulates row counts (primary split + competing splits + surrogate splits per node) to determine where each node's block of split rows begins.

Two distinct patterns appear:

**Pattern A — Index into the splits matrix (5 occurrences):**
`cumsum` is applied to a vector whose elements represent the number of split rows contributed by each node. The resulting cumulative sum is used directly as a row-index vector into `fit$splits`. The starting seed value (`0` or `1L`) is prepended to shift the result into 1-based R indexing. Files: `importance.R`, `labels.rpart.R`, `pred.rpart.R`, `summary.rpart.R`.

**Pattern B — Cumulative hazard accumulation (3 occurrences):**
`cumsum` is applied to per-interval quantities (`rev(tab1)`, `rev(tab2)`, `rate * diff(itable)`) inside `rpart.exp.R`. Here it acts as a running total to compute cumulative person-years and a piecewise-constant cumulative hazard function. The `rev(cumsum(rev(...)))` idiom specifically computes a suffix sum.

All inputs are numeric or logical vectors (coerced to integer where logical). No matrices or higher-dimensional arrays are passed to `cumsum` in this codebase.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`** via `numpy.cumsum()`.

`numpy.cumsum(a)` operates element-wise on an array in exactly the same way as R's `cumsum`, returning an array of identical shape. It is the correct default because:

1. R vectors correspond naturally to 1-D NumPy arrays.
2. NumPy handles mixed integer/float arithmetic seamlessly and supports the same `NA`-equivalent behavior via `np.nan`.
3. The suffix-sum idiom `rev(cumsum(rev(x)))` maps cleanly to `np.cumsum(x[::-1])[::-1]`.
4. NumPy is already the primary dependency throughout the Python rpart translation.

The standard library `math.fsum` is **not** appropriate here because all inputs are arrays, not scalars.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Prepend-zero offset index (Pattern A — variant 1)

**Locations:** `importance.R` :: `importance` (line 12)

**Original R Context:**

```r
# ff$ncompete and ff$nsurrogate are integer vectors of length = number of non-leaf nodes
# fpri is an integer index vector of non-leaf positions
# Result: integer vector used to index rows of fit$splits
spri <- 1 + cumsum(c(0, 1 + ff$ncompete[fpri] + ff$nsurrogate[fpri]))
spri <- spri[seq_along(fpri)]
```

The prepended `0` makes `spri[1]` equal to `1` (the first row), which is then used to offset into the 1-based `fit$splits` matrix. The final `[seq_along(fpri)]` drops the last element (the "past-the-end" sentinel).

**Python Equivalent:**

```python
import numpy as np

# fpri: 0-based index array of non-leaf node positions (e.g., np.where(ff_var != "<leaf>")[0])
# ff_ncompete, ff_nsurrogate: integer numpy arrays aligned to the full frame

per_node_count = 1 + ff_ncompete[fpri] + ff_nsurrogate[fpri]  # entries per non-leaf node
spri = 1 + np.cumsum(np.concatenate([[0], per_node_count]))    # R: 1 + cumsum(c(0, ...))
spri = spri[:len(fpri)]                                         # drop the trailing sentinel
# spri is now 1-based; subtract 1 for 0-based Python indexing into splits arrays
spri_py = spri - 1
```

**Explanation:**
- `c(0, ...)` in R becomes `np.concatenate([[0], ...])`.
- R's `1 + cumsum(...)` maps directly to `1 + np.cumsum(...)` (scalar broadcast).
- `seq_along(fpri)` (1-based R slice) becomes `[:len(fpri)]` (0-based Python slice).
- Since `fit$splits` in Python will be a 0-based array, subtract 1 from `spri` before using it as an index.

---

### 4.2 Prepend-one offset index (Pattern A — variant 2)

**Locations:**
- `labels.rpart.R` :: `labels.rpart` (line 34)
- `summary.rpart.R` :: `summary.rpart` (line 40)

**Original R Context:**

```r
# ff$ncompete, ff$nsurrogate: integer vectors over all nodes in the frame
# is.leaf: logical vector (TRUE where ff$var == "<leaf>")
# !is.leaf coerces to 0/1 integer
# Result: integer index vector into x$splits, one entry per frame row
index <- cumsum(c(1L, ff$ncompete + ff$nsurrogate + !is.leaf))
```

The leading `1L` seeds the cumsum so the first node maps to row 1 of the splits matrix. Non-leaf nodes each consume `1 + ncompete + nsurrogate` split rows; leaf nodes consume `0` (since `!is.leaf` is 0 for them, but they also have `ncompete == nsurrogate == 0`). The length of `index` is `nrow(frame) + 1`; callers take `index[whichrow]` to address only non-leaf nodes.

**Python Equivalent:**

```python
import numpy as np

# is_leaf: boolean numpy array, True where frame['var'] == '<leaf>'
# ff_ncompete, ff_nsurrogate: integer numpy arrays over the full frame

per_node = ff_ncompete + ff_nsurrogate + (~is_leaf).astype(int)
index = np.cumsum(np.concatenate([[1], per_node]))
# index has length nrow(frame) + 1, matching R behavior
# For 0-based Python indexing into splits: subtract 1
index_py = index - 1
# Select non-leaf entries:
irow_py = index_py[np.concatenate([~is_leaf, [False]])]
```

**Explanation:**
- R's `!is.leaf` on a logical vector produces an integer 0/1 vector; `(~is_leaf).astype(int)` is the NumPy equivalent.
- `c(1L, ...)` becomes `np.concatenate([[1], ...])`.
- The trailing `[False]` mirrors R's `c(whichrow, FALSE)` pattern used by callers to exclude the sentinel.

---

### 4.3 Cumulative count offset without a leading seed (Pattern A — variant 3)

**Locations:** `pred.rpart.R` :: `pred.rpart` (line 10)

**Original R Context:**

```r
# frame$var: character vector; "<leaf>" marks leaf nodes
# nc[[1L]], nc[[2L]]: integer vectors (ncompete, nsurrogate) for all nodes
# The result is trimmed with [-(nrow(frame)+1)] to drop the last sentinel
frame$index <- 1L + c(0L, cumsum((frame$var != "<leaf>") + nc[[1L]] + nc[[2L]]))[-(nrow(frame) + 1L)]
frame$index[frame$var == "<leaf>"] <- 0L
```

Unlike variants 4.1 and 4.2, the leading seed `0L` is placed inside `c(0L, cumsum(...))` rather than inside `c(0, ...)` passed to `cumsum`. This shifts the cumsum values one position to the right, effectively computing an *exclusive* prefix sum; then the last extra element is removed with `[-(nrow(frame)+1)]`.

**Python Equivalent:**

```python
import numpy as np

# frame_var: numpy array of split variable names (strings)
# ncompete, nsurrogate: integer numpy arrays

is_not_leaf = (frame_var != "<leaf>").astype(int)
per_node = is_not_leaf + ncompete + nsurrogate

# Exclusive prefix sum: prepend 0, cumsum, drop last element
index = 1 + np.concatenate([[0], np.cumsum(per_node)])[:-1]
index[frame_var == "<leaf>"] = 0
# index is 1-based; subtract 1 for 0-based Python indexing
index_py = index - 1
index_py[frame_var == "<leaf>"] = -1  # sentinel for leaf (or handle as 0 per caller's logic)
```

**Explanation:**
- `c(0L, cumsum(x))[-(nrow+1)]` is an exclusive prefix sum. The NumPy idiom is `np.concatenate([[0], np.cumsum(x)])[:-1]`, which drops the last element rather than the first.
- The scalar `1L +` outside maps to `1 +` in Python (scalar broadcast on a NumPy array).
- Leaf nodes are zeroed out after the cumsum, preserving the same logic.

---

### 4.4 Suffix sum via `rev(cumsum(rev(...)))` (Pattern B — variant 1)

**Locations:** `rpart.exp.R` :: `drate2` (lines 82 and 87)

**Original R Context:**

```r
# tab1, tab2: integer tables (frequency counts per time interval, from table())
# ngrp: number of intervals
# Used to compute person-years in the piecewise hazard model
temp <- rev(cumsum(rev(tab1)))          # line 82: suffix sums of interval counts
pyears <- ilength * c(temp[-1L], 0) + tapply(itime, index, sum)

temp <- rev(cumsum(rev(tab2)))          # line 87: same pattern for start times
py2 <- ilength * c(0, temp[-ngrp]) + tapply(itime2, index2, sum)
```

`rev(cumsum(rev(x)))` computes the **suffix sum**: element `i` of the result is the sum of `x[i], x[i+1], ..., x[n]`. This gives the number of observations whose follow-up ends in interval `i` or any later interval.

**Python Equivalent:**

```python
import numpy as np

# tab1, tab2: 1-D integer numpy arrays (output of np.bincount or similar)
# ilength: 1-D float numpy array of interval lengths
# itime: 1-D float numpy array of time spent in final interval per observation

# Suffix sum idiom
temp1 = np.cumsum(tab1[::-1])[::-1]    # rev(cumsum(rev(tab1)))
pyears = ilength * np.concatenate([temp1[1:], [0]]) + np.array(
    [itime[index == g].sum() for g in range(ngrp)]
)

temp2 = np.cumsum(tab2[::-1])[::-1]    # rev(cumsum(rev(tab2)))
py2 = ilength * np.concatenate([[0], temp2[:-1]]) + np.array(
    [itime2[index2 == g].sum() for g in range(ngrp)]
)
```

**Explanation:**
- `rev(x)` in R reverses a vector; `x[::-1]` is the NumPy equivalent.
- `rev(cumsum(rev(x)))` therefore becomes `np.cumsum(x[::-1])[::-1]`.
- `temp[-1L]` in R drops the first element (1-based indexing); `temp1[1:]` is the 0-based Python equivalent.
- `c(temp[-1L], 0)` appends a trailing zero; `np.concatenate([temp1[1:], [0]])` mirrors this.
- `c(0, temp[-ngrp])` prepends a zero and drops the last; `np.concatenate([[0], temp2[:-1]])` mirrors this.
- The `tapply(itime, index, sum)` calls map to grouped sums, implementable with `np.bincount` weighted sums or a list comprehension as shown.

---

### 4.5 Cumulative hazard accumulation (Pattern B — variant 2)

**Locations:** `rpart.exp.R` :: `rpart.exp` (line 103)

**Original R Context:**

```r
# rate: numeric vector of per-interval hazard rates (length = ngrp)
# itable: numeric vector of interval boundary times (length = ngrp + 1)
# diff(itable): numeric vector of interval lengths (length = ngrp)
# cumhaz is used as the y-values in approx() (linear interpolation)
cumhaz <- cumsum(c(0, rate * diff(itable)))
newy <- approx(itable, cumhaz, time)$y
```

The prepended `0` ensures `cumhaz[1] == 0` (zero cumulative hazard at time 0), matching `itable[1] == 0`. The result is a piecewise-linear cumulative hazard evaluated at the interval boundaries, passed to `approx()` (linear interpolation) to rescale individual observation times.

**Python Equivalent:**

```python
import numpy as np
from scipy.interpolate import interp1d

# rate: 1-D float numpy array of per-interval hazard rates (length ngrp)
# itable: 1-D float numpy array of interval boundary times (length ngrp + 1)
# time: 1-D float numpy array of individual observation times

interval_lengths = np.diff(itable)                             # diff(itable)
cumhaz = np.cumsum(np.concatenate([[0.0], rate * interval_lengths]))  # cumsum(c(0, rate*diff(itable)))

# approx() with linear interpolation (R default)
interp_fn = interp1d(itable, cumhaz, kind='linear', bounds_error=False, fill_value='extrapolate')
newy = interp_fn(time)
```

**Explanation:**
- `c(0, rate * diff(itable))` becomes `np.concatenate([[0.0], rate * np.diff(itable)])`. NumPy's `*` and `np.diff` are element-wise, matching R's vectorized arithmetic.
- `approx(x, y, xout)` in R performs linear interpolation; `scipy.interpolate.interp1d` with `kind='linear'` is the direct equivalent. Setting `fill_value='extrapolate'` mirrors R's default behavior of extrapolating beyond the data range.
- The `cumhaz` vector has length `ngrp + 1`, aligning one-to-one with `itable` — this invariant must be preserved for the interpolation to be correct.
